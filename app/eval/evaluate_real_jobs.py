import sys
import os
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.ranking import get_all_jobs, extract_job_requirements_async
from app.agents.tailoring_graph import tailoring_app
from app.agents.gap_analysis import tokenize, get_full_resume_text, get_all_resume_chunks


def ats_keyword_match_score(resume_text: str, requirements: list[str]) -> float:
    resume_tokens = set(tokenize(resume_text))
    matched = 0
    for req in requirements:
        req_tokens = tokenize(req)
        if req_tokens and all(tok in resume_tokens for tok in req_tokens):
            matched += 1
    return matched / len(requirements) if requirements else 0.0


def build_resume_text_with_overrides(overrides: dict[str, str]) -> str:
    chunks = get_all_resume_chunks()
    texts = []
    for chunk_id, original_text in zip(chunks["ids"], chunks["documents"]):
        texts.append(overrides.get(chunk_id, original_text))
    return " ".join(texts)


async def evaluate_one_job(job: dict):
    print(f"\n{'=' * 70}")
    print(f"JOB: {job['title']} @ {job['company']}")
    print(f"{'=' * 70}")

    extracted = await extract_job_requirements_async(job["description"])
    print(f"Extracted requirements ({len(extracted.requirements)}): {extracted.requirements}\n")

    if not extracted.requirements:
        print("No requirements extracted, skipping.")
        return None

    initial_state = {
        "job_requirements": extracted.requirements,
        "gap_report": None,
        "rewritten_bullets": [],
        "flagged_for_review": [],
    }
    final_state = tailoring_app.invoke(initial_state)

    print(f"Matched: {final_state['gap_report'].matched_skills}")
    print(f"Missing: {final_state['gap_report'].missing_skills}")
    print(f"Weak phrasing found: {[w.requirement for w in final_state['gap_report'].weak_phrasing]}")
    print(f"Safe rewrites applied: {len(final_state['rewritten_bullets'])}")
    print(f"Flagged (not applied): {len(final_state['flagged_for_review'])}")

    overrides = {item["chunk_id"]: item["rewritten"] for item in final_state["rewritten_bullets"]}

    before_text = build_resume_text_with_overrides({})
    after_text = build_resume_text_with_overrides(overrides)

    before_score = ats_keyword_match_score(before_text, extracted.requirements)
    after_score = ats_keyword_match_score(after_text, extracted.requirements)

    print(f"\nBEFORE: {before_score:.1%}  |  AFTER: {after_score:.1%}  |  Change: {(after_score - before_score):+.1%}")

    return before_score, after_score


async def main():
    jobs = get_all_jobs()
    # Test against 3 real, diverse jobs
    sample_jobs = list(jobs.values())[:3]

    results = []
    for job in sample_jobs:
        result = await evaluate_one_job(job)
        if result:
            results.append(result)

    if results:
        avg_before = sum(r[0] for r in results) / len(results)
        avg_after = sum(r[1] for r in results) / len(results)
        print(f"\n{'=' * 70}")
        print(f"OVERALL: avg BEFORE = {avg_before:.1%}, avg AFTER = {avg_after:.1%}, avg improvement = {(avg_after - avg_before):+.1%}")
        print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())