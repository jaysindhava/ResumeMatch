def chunk_job_description(
    text: str,
    job_id: str,
    title: str,
    company: str,
    location: str,
    url: str,
    chunk_size: int = 200,
    overlap: int = 50,
) -> list[dict]:
    """
    Split a job description into fixed-size, overlapping word chunks.
    Overlap ensures we don't lose meaning at chunk boundaries (e.g. a
    requirement sentence that gets cut mid-way isn't lost entirely -
    it also appears at the start of the next chunk).
    """
    if not text:
        return []

    words = text.split()
    chunks = []
    start = 0
    idx = 0

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        idx += 1

        chunks.append({
            "id": f"job_{job_id}_chunk_{idx:03d}",
            "section": "job_description",
            "job_id": job_id,
            "title": title or "",
            "company": company or "",
            "location": location or "",
            "url": url or "",
            "text": chunk_text,
        })

        if end >= len(words):
            break
        # Move the window forward, but step back by `overlap` words
        # so consecutive chunks share context at the boundary
        start = end - overlap

    return chunks