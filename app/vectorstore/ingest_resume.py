import sys
import os

# Allow importing from app/parsers when running this script directly
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.parsers.resume_parser import (
    extract_raw_text,
    split_into_sections,
    chunk_bullets,
    chunk_skills,
    chunk_education,
    chunk_certifications,
)
from app.vectorstore.setup import get_resume_collection, embed_and_store


def build_all_chunks(pdf_path: str) -> list[dict]:
    """Run the full parsing pipeline and return one flat list of every chunk."""
    text = extract_raw_text(pdf_path)
    sections = split_into_sections(text)

    all_chunks = []
    all_chunks += chunk_bullets(sections["professional_experience"], "professional_experience")
    all_chunks += chunk_bullets(sections["projects"], "projects")
    all_chunks += chunk_skills(sections["skills"])
    all_chunks += chunk_education(sections["education"])
    all_chunks += chunk_certifications(sections["certifications"])

    return all_chunks


if __name__ == "__main__":
    pdf_path = "data/resumes/jay_resume_JP.pdf"

    print("Parsing and chunking resume...")
    chunks = build_all_chunks(pdf_path)
    print(f"Total chunks created: {len(chunks)}")

    print("\nEmbedding and storing in Chroma...")
    collection = get_resume_collection()
    embed_and_store(chunks, collection)
    print(f"✅ Stored {len(chunks)} chunks in the 'resume_chunks' collection.")

    print(f"\nCollection now contains {collection.count()} total items.")