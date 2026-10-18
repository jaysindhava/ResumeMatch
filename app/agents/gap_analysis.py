import sys
import os
import re

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from rank_bm25 import BM25Okapi
from pydantic import BaseModel, Field
from snowballstemmer import stemmer as snowball_stemmer

from app.vectorstore.setup import get_resume_collection, embed_text
from app.agents.llm_config import extraction_llm as gap_llm

_stemmer = snowball_stemmer("english")


def get_all_resume_chunks() -> dict:
    """
    Pull every chunk currently stored in the resume_chunks collection,
    along with its text and metadata, so we can build a BM25 index over them.
    """
    collection = get_resume_collection()
    data = collection.get()

    return {
        "ids": data["ids"],
        "documents": data["documents"],
        "metadatas": data["metadatas"],
    }


def get_full_resume_text() -> str:
    """
    Concatenates all resume chunks into one block of text, for use in
    prompts that need the whole resume at once rather than per-requirement
    retrieved evidence.
    """
    chunks = get_all_resume_chunks()
    return "\n".join(chunks["documents"])


def tokenize(text: str) -> list[str]:
    """
    Tokenize text into alphanumeric word chunks, lowercased and stemmed.
    Stemming reduces words to their root form (e.g. "developed", "developing",
    "development" all become "develop"), so BM25 can match across word
    variants instead of treating them as unrelated tokens - this measurably
    improved retrieval hit-rate@1 from 50% to 75% in evaluation (see Phase 9).
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    return _stemmer.stemWords(words)


def build_bm25_index(documents: list[str]) -> BM25Okapi | None:
    """BM25 needs documents pre-tokenized into lists of words."""
    if not documents:
        return None
    tokenized = [tokenize(doc) for doc in documents if doc and doc.strip()]
    if not tokenized or not any(tokenized):
        return None
    return BM25Okapi(tokenized)


def bm25_search(query: str, n_results: int = 5) -> list[dict]:
    """Search resume chunks using pure keyword (BM25) matching."""
    chunks = get_all_resume_chunks()
    if not chunks.get("documents"):
        return []
    bm25 = build_bm25_index(chunks["documents"])
    if bm25 is None:
        return []

    tokenized_query = tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    scored_chunks = list(zip(chunks["ids"], chunks["documents"], chunks["metadatas"], scores))
    scored_chunks.sort(key=lambda x: x[3], reverse=True)

    results = []
    for chunk_id, text, metadata, score in scored_chunks[:n_results]:
        results.append({
            "id": chunk_id,
            "text": text,
            "section": metadata.get("section"),
            "bm25_score": round(float(score), 4),
        })
    return results


def vector_search(query: str, n_results: int = 5) -> list[dict]:
    """Search resume chunks using pure semantic (vector) similarity."""
    collection = get_resume_collection()
    if collection.count() == 0:
        return []

    query_embedding = embed_text(query)
    actual_k = min(n_results, collection.count())
    if actual_k <= 0:
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=actual_k,
    )

    output = []
    for i in range(len(results["ids"][0])):
        output.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "section": results["metadatas"][0][i].get("section"),
            "distance": results["distances"][0][i],
        })
    return output


def reciprocal_rank_fusion(bm25_results: list[dict], vector_results: list[dict], k: int = 60) -> list[dict]:
    """
    Combine two ranked result lists into one fused ranking.
    RRF score = sum of 1 / (k + rank) across every list a chunk appears in.
    k=60 is a standard damping constant from the original RRF paper.
    """
    scores = {}
    chunk_data = {}

    for rank, result in enumerate(bm25_results, start=1):
        cid = result["id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank)
        chunk_data[cid] = result

    for rank, result in enumerate(vector_results, start=1):
        cid = result["id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank)
        chunk_data[cid] = result

    fused = []
    for cid, score in scores.items():
        entry = dict(chunk_data[cid])
        entry["rrf_score"] = round(score, 5)
        fused.append(entry)

    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused


def hybrid_search(query: str, n_results: int = 5) -> list[dict]:
    """The main retrieval function: fuses BM25 + vector search results."""
    bm25_results = bm25_search(query, n_results=10)
    vector_results = vector_search(query, n_results=10)
    fused = reciprocal_rank_fusion(bm25_results, vector_results)
    return fused[:n_results]


class WeakPhrasingItem(BaseModel):
    resume_chunk_id: str = Field(description="The id of the resume chunk with weak phrasing")
    resume_text: str = Field(description="The original resume bullet text")
    requirement: str = Field(description="The job requirement this relates to")
    suggestion: str = Field(description="A brief suggestion for how to rephrase it")


class GapReport(BaseModel):
    matched_skills: list[str] = Field(description="Skills/requirements the resume genuinely demonstrates, with real evidence")
    missing_skills: list[str] = Field(description="Skills/requirements with NO real evidence anywhere in the resume")
    weak_phrasing: list[WeakPhrasingItem] = Field(description="Bullets that relate to a requirement but don't use matching keywords/phrasing")


def enforce_category_exclusivity(report: GapReport) -> GapReport:
    """
    Post-processing safety net: if the LLM's response put the same skill in
    more than one category (matched_skills, missing_skills, weak_phrasing),
    resolve the conflict by keeping only the STRICTEST category it appeared
    in, since a self-contradictory response should never be treated as a
    confident match. Priority (strictest first): missing > weak_phrasing > matched.
    """
    weak_phrasing_reqs = {w.requirement for w in report.weak_phrasing}
    missing_set = set(report.missing_skills)

    clean_matched = [
        s for s in report.matched_skills
        if s not in missing_set and s not in weak_phrasing_reqs
    ]

    clean_weak_phrasing = [
        w for w in report.weak_phrasing
        if w.requirement not in missing_set
    ]

    return GapReport(
        matched_skills=clean_matched,
        missing_skills=report.missing_skills,
        weak_phrasing=clean_weak_phrasing,
    )


GAP_REPORT_PROMPT_TEMPLATE = """You are analyzing how well a resume matches a job's requirements.

For each requirement below, candidate resume chunks were retrieved by a search system.
Some retrieved chunks may NOT actually be relevant (the search system isn't perfect) -
you must judge relevance yourself based on the actual text, not assume every retrieved chunk is a match.

Job requirements and retrieved candidate evidence:
{evidence_text}

Classify each requirement into exactly one of:
- matched_skills: the resume contains EXPLICIT, CONCRETE evidence (the exact skill/tool/technology is actually named in a chunk)
- missing_skills: no chunk explicitly names this skill/tool/technology - this includes cases where a chunk is topically related but does NOT explicitly mention it
- weak_phrasing: a chunk DOES contain the actual skill/evidence, but uses different wording than the requirement (e.g. resume says "ETL" and requirement says "extract transform load" - same specific fact, different phrasing)

CRITICAL RULES:
- Each requirement belongs to EXACTLY ONE category. Never place the same requirement in more than one list.
- NEVER suggest a rephrasing that introduces a fact not already stated in the resume (e.g. do NOT suggest "if you used AWS, mention it" - if AWS is not explicitly mentioned anywhere, that is missing_skills, not weak_phrasing)
- A generic/related chunk (e.g. a bullet about "deployment" with no named cloud provider) does NOT count as evidence for a SPECIFIC named technology (e.g. AWS) unless that exact technology is mentioned
- If the requirement names a SPECIFIC term/methodology (e.g. "ETL", "AWS", "Kafka") and the resume only contains a MORE GENERAL term (e.g. "data pipelines", "cloud", "streaming"), this is NOT a match and NOT weak_phrasing - it is missing_skills, because the specific term itself is an unverified claim, even if it seems like a reasonable inference
- weak_phrasing applies ONLY when the resume states the SAME level of specificity as the requirement, just with different words - NOT when the resume is more general than the requirement
- When in doubt between missing_skills and weak_phrasing, choose missing_skills - it is safer to under-claim than to risk suggesting a fabricated or unverified claim
"""


def _build_evidence_text(job_requirements: list[str]) -> str:
    """Shared helper: retrieves evidence per requirement and formats it into
    the prompt text used by both the sync and async gap report functions."""
    evidence_per_requirement = {}
    for req in job_requirements:
        candidates = hybrid_search(req, n_results=3)
        evidence_per_requirement[req] = candidates

    evidence_text = ""
    for req, candidates in evidence_per_requirement.items():
        evidence_text += f"\nRequirement: {req}\n"
        for c in candidates:
            evidence_text += f"  - Candidate resume chunk [{c['id']}]: \"{c['text']}\"\n"

    return evidence_text


def build_gap_report(job_description: str, job_requirements: list[str]) -> GapReport:
    """
    For each requirement, retrieve candidate resume chunks via hybrid search,
    then let the LLM judge whether they constitute real evidence, weak/partial
    evidence, or no evidence at all - rather than trusting a raw score cutoff.
    """
    evidence_text = _build_evidence_text(job_requirements)
    structured_llm = gap_llm.with_structured_output(GapReport)
    prompt = GAP_REPORT_PROMPT_TEMPLATE.format(evidence_text=evidence_text)
    result = structured_llm.invoke(prompt)
    return enforce_category_exclusivity(result)


async def build_gap_report_async(job_description: str, job_requirements: list[str]) -> GapReport:
    """Async version of build_gap_report - used for BULK ranking (Phase 7),
    where all requirements are judged together in ONE call for efficiency.
    Testing showed this batching can occasionally misclassify individual
    items (see build_gap_report_isolated for the higher-accuracy alternative
    used in single-job tailoring, Phase 6)."""
    evidence_text = _build_evidence_text(job_requirements)
    structured_llm = gap_llm.with_structured_output(GapReport)
    prompt = GAP_REPORT_PROMPT_TEMPLATE.format(evidence_text=evidence_text)
    result = await structured_llm.ainvoke(prompt)
    return enforce_category_exclusivity(result)


def build_gap_report_isolated(job_description: str, job_requirements: list[str]) -> GapReport:
    """
    Judges EACH requirement in its own separate LLM call, then combines the
    results into one GapReport. Slower and more expensive than the batched
    build_gap_report (N calls instead of 1), but more accurate per-item -
    testing showed batched judgments can misclassify individual items when
    several are judged together in one call.

    Used specifically for single-job tailoring (Phase 6), where a user acts
    directly on the result, so correctness matters more than call efficiency.
    Bulk ranking (Phase 7) continues using the batched version, where the
    consequence of an occasional misclassification is just a minor rank shift.
    """
    all_matched = []
    all_missing = []
    all_weak_phrasing = []

    for requirement in job_requirements:
        single_report = build_gap_report(job_description="", job_requirements=[requirement])
        all_matched.extend(single_report.matched_skills)
        all_missing.extend(single_report.missing_skills)
        all_weak_phrasing.extend(single_report.weak_phrasing)

    combined = GapReport(
        matched_skills=all_matched,
        missing_skills=all_missing,
        weak_phrasing=all_weak_phrasing,
    )
    return enforce_category_exclusivity(combined)


if __name__ == "__main__":
    print("=== GAP REPORT TEST (batched - see build_gap_report_isolated for the higher-accuracy alternative used in Phase 6) ===\n")

    test_requirements = [
        "React frontend development",
        "Docker containerization",
        "Python and machine learning",
        "AWS cloud experience",
        "REST API development",
    ]

    report = build_gap_report(
        job_description="Sample job requiring the above skills",
        job_requirements=test_requirements,
    )

    print("MATCHED SKILLS:")
    for s in report.matched_skills:
        print(f"  ✅ {s}")

    print("\nMISSING SKILLS:")
    for s in report.missing_skills:
        print(f"  ❌ {s}")

    print("\nWEAK PHRASING (related but not explicit):")
    for w in report.weak_phrasing:
        print(f"  ⚠️  [{w.resume_chunk_id}] \"{w.resume_text}\"")
        print(f"      → For requirement: {w.requirement}")
        print(f"      → Suggestion: {w.suggestion}")