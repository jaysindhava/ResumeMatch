import re
from pypdf import PdfReader


def extract_raw_text(pdf_path: str) -> str:
    """Extract all raw text from a PDF resume."""
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"
    return full_text


# Maps a canonical section name to every known real-world wording variant
# we've encountered. Add more aliases here as new resume formats surface.
SECTION_HEADER_ALIASES = {
    "professional_experience": ["Professional Experience", "Work Experience", "Experience"],
    "projects": ["Projects", "Key Projects", "Personal Projects"],
    "education": ["Education"],
    "certifications": ["Certifications", "Certificates"],
    "skills": ["Skills", "Technical Skills"],
    "extracurriculars": ["Extracurriculars", "Extra-Curricular Activities", "Extracurricular Activities"],
}


def _normalize_for_matching(text: str) -> str:
    """
    Strips ALL whitespace and lowercases, so header matching survives PDF
    kerning artifacts like "Educa tion" (stray space) matching "Education".
    """
    return re.sub(r"\s+", "", text).lower()


def split_into_sections(text: str) -> dict:
    """
    Split raw resume text into a dict of {canonical_section_name: text}.
    Matches headers against a list of known aliases per section (not just
    one exact string), and tolerates PDF-extraction spacing artifacts by
    comparing whitespace-stripped, lowercased versions of each line.
    """
    lines = text.split("\n")

    # Build a lookup: normalized alias text -> canonical section name
    alias_lookup = {}
    for canonical, aliases in SECTION_HEADER_ALIASES.items():
        for alias in aliases:
            alias_lookup[_normalize_for_matching(alias)] = canonical

    sections = {}
    current_section = "header"
    current_lines = []

    for line in lines:
        stripped = line.strip()
        normalized = _normalize_for_matching(stripped)

        if normalized in alias_lookup:
            # Save whatever we've accumulated for the previous section
            sections[current_section] = "\n".join(current_lines).strip()
            current_section = alias_lookup[normalized]
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_section] = "\n".join(current_lines).strip()
    return sections

# Matches date-range patterns like "Feb'26 - Apr'26" or "May '25 – July '25",
# accepting both a regular hyphen (-) and an en-dash (–), and the odd spacing
# PDF extraction sometimes introduces (e.g. "F eb'26")
DATE_RANGE_PATTERN = re.compile(r"['’]\d{2}\s*[-–]\s*\S*\s*['’]?\d{2}")

# Matches a line ending in a 4-digit year (2026) or a year range (2020-22),
# used to detect the start of a new institution entry in Education
YEAR_END_PATTERN = re.compile(r"(\d{4}|\d{4}-\d{2})\s*$")


def chunk_bullets(section_text: str, section_name: str) -> list[dict]:
    """
    Split a section's text into individual bullet-point chunks, correctly
    grouped under the right job/project sub-header.

    Logic, line by line:
    - A line containing a date range (e.g. "Feb'26 - Apr'26") starts a NEW
      sub-header block (new job/project) -> resets the current context.
    - A line starting with "•" starts a new bullet.
    - Any other line is either a continuation of the wrapped bullet text
      (if we're mid-bullet) or extra context info like company name / tech
      stack (if we're not mid-bullet).
    """
    # Some PDFs place two bullets on the same physical line with no newline
    # between them (e.g. "...recommendations.• Built scalable..."). Force a
    # newline before every • so each bullet always starts its own line.
    # Support multiple bullet character styles across different resume
    # formats/PDF exports (•, ◦, ▪, ‣), normalizing them all to • internally
    BULLET_CHARS = ["•", "◦", "▪", "‣"]
    normalized_text = section_text
    for bullet_char in BULLET_CHARS:
        normalized_text = normalized_text.replace(bullet_char, "•")
    normalized_text = re.sub(r"•", "\n•", normalized_text)
    lines = normalized_text.split("\n")

    chunks = []
    current_context = ""
    current_bullet_lines = []
    bullet_idx = 0

    def flush_bullet():
        nonlocal current_bullet_lines, bullet_idx
        if current_bullet_lines:
            text = " ".join(current_bullet_lines).strip()
            text = text.lstrip("•").strip()
            if text:
                bullet_idx += 1
                chunks.append({
                    "id": f"{section_name}_{bullet_idx:03d}",
                    "section": section_name,
                    "context": current_context.strip(),
                    "text": text,
                })
            current_bullet_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if DATE_RANGE_PATTERN.search(stripped) and not stripped.startswith("•"):
            flush_bullet()
            current_context = stripped
        elif stripped.startswith("•"):
            flush_bullet()
            current_bullet_lines = [stripped]
        else:
            if current_bullet_lines:
                current_bullet_lines.append(stripped)
            else:
                current_context += " " + stripped

    flush_bullet()
    return chunks


def chunk_skills(section_text: str) -> list[dict]:
    """
    Split the Skills section into one chunk per category line
    (e.g. 'Languages: C/C++, Python, SQL...').
    Lines that don't start a new category (no early colon) are treated
    as a wrapped continuation of the previous category line.
    """
    lines = [l.strip() for l in section_text.split("\n") if l.strip()]
    chunks = []
    current_label = None
    current_text = ""
    idx = 0

    def flush():
        nonlocal current_label, current_text, idx
        if current_label:
            idx += 1
            chunks.append({
                "id": f"skills_{idx:03d}",
                "section": "skills",
                "context": current_label,
                "text": current_text.strip(),
            })

    for line in lines:
        # A "label" line has a colon within roughly the first 40 characters
        colon_pos = line.find(":")
        if 0 < colon_pos < 40:
            flush()
            current_label = line[:colon_pos].strip()
            current_text = line[colon_pos + 1:].strip()
        else:
            current_text += " " + line

    flush()
    return chunks


def chunk_education(section_text: str) -> list[dict]:
    """
    Split the Education section into one chunk per institution.
    A new institution starts whenever a line ends with a year or year range.
    """
    lines = [l.strip() for l in section_text.split("\n") if l.strip()]
    chunks = []
    current_lines = []
    idx = 0

    def flush():
        nonlocal current_lines, idx
        if current_lines:
            idx += 1
            chunks.append({
                "id": f"education_{idx:03d}",
                "section": "education",
                "context": "",
                "text": " ".join(current_lines).strip(),
            })
        current_lines = []

    for line in lines:
        if YEAR_END_PATTERN.search(line) and current_lines:
            # A new institution line appeared while we already have content
            # buffered -> the previous institution's block is complete
            flush()
        current_lines.append(line)

    flush()
    return chunks


def chunk_certifications(section_text: str) -> list[dict]:
    """Certifications follow the same title+date+bullet structure as
    Experience/Projects, so we reuse chunk_bullets."""
    return chunk_bullets(section_text, "certifications")


if __name__ == "__main__":
    text = extract_raw_text("data/resumes/jay_resume_JP.pdf")

    print("=== FULL RAW EXTRACTED TEXT ===\n")
    print(text)
    print(f"\nTotal characters extracted: {len(text)}")

    sections = split_into_sections(text)

    print("\n\n=== SECTIONS FOUND ===\n")
    for name, content in sections.items():
        print(f"--- {name.upper()} ---")
        print(content)
        print()

    print("\n=== BULLET CHUNKS: PROFESSIONAL EXPERIENCE ===\n")
    exp_chunks = chunk_bullets(sections["professional_experience"], "professional_experience")
    for chunk in exp_chunks:
        print(f"[{chunk['id']}] (context: {chunk['context']})")
        print(f"  → {chunk['text']}")
        print()

    print("\n=== BULLET CHUNKS: PROJECTS ===\n")
    proj_chunks = chunk_bullets(sections["projects"], "projects")
    for chunk in proj_chunks:
        print(f"[{chunk['id']}] (context: {chunk['context']})")
        print(f"  → {chunk['text']}")
        print()

    print("\n=== CHUNKS: SKILLS ===\n")
    skill_chunks = chunk_skills(sections["skills"])
    for chunk in skill_chunks:
        print(f"[{chunk['id']}] {chunk['context']}: {chunk['text']}")

    print("\n=== CHUNKS: EDUCATION ===\n")
    edu_chunks = chunk_education(sections["education"])
    for chunk in edu_chunks:
        print(f"[{chunk['id']}] {chunk['text']}")

    print("\n=== CHUNKS: CERTIFICATIONS ===\n")
    cert_chunks = chunk_certifications(sections["certifications"])
    for chunk in cert_chunks:
        print(f"[{chunk['id']}] (context: {chunk['context']})")
        print(f"  → {chunk['text']}")