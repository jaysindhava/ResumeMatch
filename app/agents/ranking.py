import sys
import os
import asyncio
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from groq import RateLimitError as GroqRateLimitError

from app.agents.llm_config import extraction_llm
from app.vectorstore.setup import get_job_collection, embed_text
from app.agents.gap_analysis import build_gap_report_async, get_full_resume_text


class ExtractedRequirements(BaseModel):
    requirements: list[str] = Field(description="A clean list of specific skills, tools, or technologies required by this job, each as a short phrase")
    min_years_experience: int = Field(description="Minimum years of experience required, as a number. Use 0 if not specified or if it's an entry-level/fresher role.")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(GroqRateLimitError),
)
async def extract_job_requirements_async(job_description: str) -> ExtractedRequirements:
    """Extracts a clean requirements list + experience level from a raw job
    description. This is the validated, higher-quality two-step approach
    (as opposed to a single combined call, which we tested and found both
    slower AND lower quality - see project notes)."""
    structured_llm = extraction_llm.with_structured_output(ExtractedRequirements)

    prompt = f"""Extract structured information from this job description.

Job description:
\"\"\"{job_description}\"\"\"

Extract:
1. A clean list of specific required skills/tools/technologies (short phrases). Do NOT include company names, taglines, industry-domain words (e.g. "healthcare", "finance"), or soft-skill fluff unless clearly emphasized as a core requirement.
2. The minimum years of experience required as a number (0 if entry-level/fresher/not specified).
"""

    return await structured_llm.ainvoke(prompt)


def get_all_jobs() -> dict:
    """Reconstruct one entry per unique job from the job_chunks collection."""
    collection = get_job_collection()
    data = collection.get()

    jobs = {}
    for doc, meta in zip(data["documents"], data["metadatas"]):
        job_id = meta["job_id"]
        if job_id not in jobs:
            jobs[job_id] = {
                "job_id": job_id,
                "title": meta["title"],
                "company": meta["company"],
                "location": meta["location"],
                "url": meta["url"],
                "description": "",
            }
        jobs[job_id]["description"] += " " + doc

    return jobs


CANDIDATE_YEARS_EXPERIENCE = 0.5  # ~6 months combined internship experience


class JobScore(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    url: str
    prefilter_similarity: float
    skill_overlap: float
    seniority_match: float
    location_match: float
    final_score: float
    matched_skills: list[str]
    missing_skills: list[str]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a = np.array(vec_a)
    b = np.array(vec_b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def prefilter_jobs_by_similarity(jobs: dict, resume_text: str, top_n: int = 12) -> list[tuple]:
    """
    Cheap, LOCAL, zero-LLM-call pre-filter: ranks all jobs by embedding
    similarity between the resume and each job's title+description, using
    the same local sentence-transformers model from Phase 2. This narrows
    a large job list down to genuine candidates BEFORE spending any LLM
    calls, which is the real fix for TPM rate-limit pressure - fewer,
    more relevant jobs get the expensive treatment instead of all of them.
    Returns a list of (similarity_score, job_id, job) tuples, sorted best-first.
    """
    resume_vec = embed_text(resume_text)

    scored = []
    for job_id, job in jobs.items():
        job_text = f"{job['title']} {job['description']}"
        job_vec = embed_text(job_text)
        similarity = cosine_similarity(resume_vec, job_vec)
        scored.append((similarity, job_id, job))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


async def score_skill_overlap_async(requirements: list[str]) -> tuple[float, list[str], list[str]]:
    if not requirements:
        return 0.0, [], []

    report = await build_gap_report_async(job_description="", job_requirements=requirements)
    matched = report.matched_skills
    missing = report.missing_skills
    total = len(matched) + len(missing)

    overlap = len(matched) / total if total > 0 else 0.0
    return overlap, matched, missing


def score_seniority_match(min_years_required: int) -> float:
    if min_years_required <= 0:
        return 1.0
    if CANDIDATE_YEARS_EXPERIENCE >= min_years_required:
        return 1.0
    return round(CANDIDATE_YEARS_EXPERIENCE / min_years_required, 3)


def score_location_match(job_location: str, preferred_locations: list[str]) -> float:
    location_lower = job_location.lower()
    if "remote" in location_lower:
        return 1.0
    for preferred in preferred_locations:
        if preferred.lower() in location_lower:
            return 1.0
    return 0.3


async def score_one_job(job_id: str, job: dict, prefilter_score: float, preferred_locations: list[str], semaphore: asyncio.Semaphore):
    """Score a single job using the validated two-step pipeline (extraction,
    then hybrid-retrieval-grounded gap analysis). Only called on jobs that
    already passed the cheap embedding pre-filter."""
    async with semaphore:
        print(f"Scoring: {job['title']} @ {job['company']}...")
        extracted = await extract_job_requirements_async(job["description"])

        if not extracted.requirements:
            print(f"  ⚠️  Skipping {job['title']} @ {job['company']} - no requirements could be extracted (likely truncated description)")
            return None

        skill_overlap, matched, missing = await score_skill_overlap_async(extracted.requirements)

        seniority = score_seniority_match(extracted.min_years_experience)
        location = score_location_match(job["location"], preferred_locations)
        final_score = (0.5 * skill_overlap) + (0.3 * seniority) + (0.2 * location)

        return JobScore(
            job_id=job_id,
            title=job["title"],
            company=job["company"],
            location=job["location"],
            url=job["url"],
            prefilter_similarity=round(prefilter_score, 4),
            skill_overlap=round(skill_overlap, 3),
            seniority_match=round(seniority, 3),
            location_match=round(location, 3),
            final_score=round(final_score, 3),
            matched_skills=matched,
            missing_skills=missing,
        )


async def rank_all_jobs_async(preferred_locations: list[str], top_n_prefilter: int = 12, max_concurrent: int = 4) -> list[JobScore]:
    """
    Two-stage ranking:
    1. Cheap, local, zero-LLM-call embedding pre-filter narrows the full job
       list down to the top_n_prefilter most promising candidates.
    2. Only those go through the expensive, validated two-step LLM pipeline
       (extraction + hybrid-retrieval gap analysis), run concurrently.
    """
    jobs = get_all_jobs()
    resume_text = get_full_resume_text()

    print(f"Pre-filtering {len(jobs)} jobs by embedding similarity (no LLM calls, fast)...")
    top_candidates = prefilter_jobs_by_similarity(jobs, resume_text, top_n=top_n_prefilter)
    print(f"Selected top {len(top_candidates)} candidates for deep LLM scoring.\n")

    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [
        score_one_job(job_id, job, prefilter_score, preferred_locations, semaphore)
        for prefilter_score, job_id, job in top_candidates
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scored_jobs = []
    failed_count = 0
    excluded_count = 0

    for (prefilter_score, job_id, job), result in zip(top_candidates, results):
        if isinstance(result, Exception):
            failed_count += 1
            print(f"  ⚠️  Failed to score {job['title']}: {result}")
        elif result is None:
            excluded_count += 1
        else:
            scored_jobs.append(result)

    if failed_count:
        print(f"\n{failed_count} job(s) failed to score due to errors and were skipped.")
    if excluded_count:
        print(f"{excluded_count} job(s) excluded due to insufficient description data.")

    scored_jobs.sort(key=lambda x: x.final_score, reverse=True)
    return scored_jobs


if __name__ == "__main__":
    import time

    print("=== RANKING (pre-filter + async deep scoring) ===\n")

    start = time.time()
    ranked = asyncio.run(rank_all_jobs_async(
        preferred_locations=["Pune", "Nashik", "Mumbai", "Bangalore", "Hyderabad", "Remote"],
        top_n_prefilter=12,
        max_concurrent=3,
    ))
    elapsed = time.time() - start

    print(f"\nCompleted in {elapsed:.1f} seconds\n")
    print("=" * 70)
    print("RANKED RESULTS")
    print("=" * 70)
    for i, job in enumerate(ranked, 1):
        print(f"\n#{i} [{job.final_score}] {job.title} @ {job.company} ({job.location})")
        print(f"   prefilter_similarity={job.prefilter_similarity}, skill_overlap={job.skill_overlap}, seniority={job.seniority_match}, location={job.location_match}")
        print(f"   Matched: {job.matched_skills}")
        print(f"   Missing: {job.missing_skills}")