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


class CandidateExperience(BaseModel):
    total_years: float = Field(description="Estimated total professional/internship experience in years (e.g. 0.5 for 6 months, 1.0, 2.5). If pure fresher or no experience, return 0.0.")
    summary: str = Field(description="Concise 1-2 sentence summary of candidate experience and titles.")


def extract_candidate_experience_from_text(resume_text: str) -> CandidateExperience:
    """Extract candidate's total years of experience from resume text."""
    if not resume_text or len(resume_text.strip()) < 20:
        return CandidateExperience(total_years=0.0, summary="No prior experience listed (fresher/entry-level)")
    try:
        structured_llm = extraction_llm.with_structured_output(CandidateExperience)
        prompt = f"""Analyze the candidate's resume below and extract their total years of professional/internship experience.

Resume text:
\"\"\"{resume_text[:4000]}\"\"\"

Calculate:
1. total_years: Total duration of work/internship experience as a float (e.g. 0.5 for 6 months, 1.2, 2.0). If entry-level/fresher with no work history, use 0.0.
2. summary: A concise 1-2 sentence summary of their roles and experience level.
"""
        return structured_llm.invoke(prompt)
    except Exception as e:
        print(f"Experience extraction error: {e}")
        return CandidateExperience(total_years=0.0, summary="Entry level / Fresher")


def compare_experience(job_min_years: int, candidate_exp: CandidateExperience) -> dict:
    cand_years = candidate_exp.total_years
    cand_summary = candidate_exp.summary

    if job_min_years <= 0:
        status = "Fresher Friendly"
        is_match = True
        explanation = f"This position is open to entry-level candidates or does not specify minimum years. Your background ({cand_summary}) makes you a strong candidate."
    elif cand_years >= job_min_years:
        status = "Meets Requirement"
        is_match = True
        diff = round(cand_years - job_min_years, 1)
        extra = f" (+{diff} yr surplus)" if diff > 0 else ""
        explanation = f"You meet the experience threshold for this role. The job requires {job_min_years} year(s), and your resume reflects ~{cand_years:.1f} year(s){extra} ({cand_summary})."
    else:
        status = "Experience Gap"
        is_match = False
        gap = round(job_min_years - cand_years, 1)
        explanation = f"The job lists a requirement of {job_min_years}+ years of experience, while your resume shows ~{cand_years:.1f} year(s) ({cand_summary}). Focus on demonstrating production impact and project complexity to bridge the {gap}-year gap."

    return {
        "job_years_required": job_min_years,
        "candidate_years": cand_years,
        "status": status,
        "is_match": is_match,
        "candidate_summary": cand_summary,
        "comparison_text": explanation,
    }


CANDIDATE_YEARS_EXPERIENCE = 0.5  # fallback default


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
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)



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


async def score_skill_overlap_async(requirements: list[str], session_id: str | None = None) -> tuple[float, list[str], list[str]]:
    if not requirements:
        return 0.0, [], []

    report = await build_gap_report_async(job_description="", job_requirements=requirements, session_id=session_id)
    matched = report.matched_skills
    missing = report.missing_skills
    total = len(matched) + len(missing)

    overlap = len(matched) / total if total > 0 else 0.0
    return overlap, matched, missing


def score_seniority_match(min_years_required: int, candidate_years: float = CANDIDATE_YEARS_EXPERIENCE) -> float:
    if min_years_required <= 0:
        return 1.0
    if candidate_years >= min_years_required:
        return 1.0
    return round(candidate_years / min_years_required, 3)


def score_location_match(job_location: str, preferred_locations: list[str]) -> float:
    location_lower = job_location.lower()
    if "remote" in location_lower:
        return 1.0
    for preferred in preferred_locations:
        if preferred.lower() in location_lower:
            return 1.0
    return 0.3


async def score_one_job(job_id: str, job: dict, prefilter_score: float, preferred_locations: list[str], semaphore: asyncio.Semaphore, session_id: str | None = None, candidate_years: float = CANDIDATE_YEARS_EXPERIENCE):
    """Score a single job using the validated two-step pipeline (extraction,
    then hybrid-retrieval-grounded gap analysis). Only called on jobs that
    already passed the cheap embedding pre-filter."""
    async with semaphore:
        print(f"Scoring: {job['title']} @ {job['company']}...")
        extracted = await extract_job_requirements_async(job["description"])

        if not extracted.requirements:
            print(f"  ⚠️  Skipping {job['title']} @ {job['company']} - no requirements could be extracted (likely truncated description)")
            return None

        skill_overlap, matched, missing = await score_skill_overlap_async(extracted.requirements, session_id=session_id)

        seniority = score_seniority_match(extracted.min_years_experience, candidate_years=candidate_years)
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


async def rank_job_list_async(jobs_list: list[dict], preferred_locations: list[str], max_concurrent: int = 3, session_id: str | None = None, candidate_years: float | None = None) -> list[JobScore]:
    """
    Same two-stage scoring as rank_all_jobs_async, but operates on a
    caller-provided list of jobs (e.g. fresh search results) instead of
    pulling from the old, frozen Phase 4 ingested batch in Chroma.
    """
    jobs = {job["job_id"]: job for job in jobs_list}
    resume_text = get_full_resume_text(session_id=session_id)
    if not resume_text:
        return []

    if candidate_years is None:
        cand_exp = extract_candidate_experience_from_text(resume_text)
        candidate_years = cand_exp.total_years

    top_candidates = prefilter_jobs_by_similarity(jobs, resume_text, top_n=len(jobs))

    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [
        score_one_job(job_id, job, prefilter_score, preferred_locations, semaphore, session_id=session_id, candidate_years=candidate_years)
        for prefilter_score, job_id, job in top_candidates
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scored_jobs = []
    for (prefilter_score, job_id, job), result in zip(top_candidates, results):
        if isinstance(result, Exception) or result is None:
            continue
        scored_jobs.append(result)

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