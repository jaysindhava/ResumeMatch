import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.tailoring_graph import tailoring_app
from app.agents.gap_analysis import tokenize, get_all_resume_chunks, get_full_resume_text


def ats_keyword_match_score(resume_text: str, requirements: list[str]) -> float:
    """Simple ATS-style keyword match: % of requirements whose stemmed
    tokens ALL appear somewhere in the resume text."""
    resume_tokens = set(tokenize(resume_text))

    matched = 0
    for req in requirements:
        req_tokens = tokenize(req)
        if req_tokens and all(tok in resume_tokens for tok in req_tokens):
            matched += 1

    return matched / len(requirements) if requirements else 0.0


def build_resume_text(overrides: dict[str, str] = None) -> str:
    """
    Reconstructs the full resume as one block of text, chunk by chunk.
    If overrides is given (chunk_id -> new_text), those chunks use the
    override text instead of the original - this lets us build the
    "after tailoring" version by swapping in only the safely rewritten bullets.
    """
    overrides = overrides or {}
    chunks = get_all_resume_chunks()
    texts = []
    for chunk_id, original_text in zip(chunks["ids"], chunks["documents"]):
        texts.append(overrides.get(chunk_id, original_text))
    return " ".join(texts)


if __name__ == "__main__":
    print("=== ATS KEYWORD-MATCH: DIRECT DEMONSTRATION ===\n")
    print("(Using a manually-verified safe rewrite from Phase 6 testing,")
    print(" since the full pipeline's strict guardrails rarely trigger a")
    print(" natural weak_phrasing case - see project notes for why.)\n")

    test_requirements = ["ETL pipeline development", "React frontend development"]

    # Before: original resume text
    before_text = get_full_resume_text()

    # After: swap in the SAFE rewrite we validated in Step 6.1 (rephrased,
    # not fabricated - same facts, different word order/framing)
    original_bullet = "Processed and analyzed 3K+ records for data preprocessing, exploratory data analysis (EDA), reporting, and model development."
    safe_rewrite = "Processed 3K+ records through data preprocessing and analysis for exploratory data analysis (EDA), reporting, and model development."
    after_text = before_text.replace(original_bullet, safe_rewrite)

    before_score = ats_keyword_match_score(before_text, test_requirements)
    after_score = ats_keyword_match_score(after_text, test_requirements)

    print(f"BEFORE tailoring: {before_score:.1%} keyword match")
    print(f"AFTER tailoring:  {after_score:.1%} keyword match")
    print(f"Improvement: {(after_score - before_score):+.1%}")