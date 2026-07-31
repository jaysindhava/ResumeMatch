import sys
import os
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.ranking import get_all_jobs, extract_job_requirements_async

TARGET_COMPANIES = ["Danaher", "Biddano", "Qrata"]


async def main():
    jobs = get_all_jobs()

    for job_id, job in jobs.items():
        if job["company"] in TARGET_COMPANIES:
            print(f"\n{'=' * 70}")
            print(f"Job: {job['title']} @ {job['company']}")
            print(f"{'=' * 70}")
            print(f"Description length: {len(job['description'])} characters")
            print(f"Description text:\n{job['description']}\n")

            try:
                extracted = await extract_job_requirements_async(job["description"])
                print(f"Extracted min_years_experience: {extracted.min_years_experience}")
                print(f"Extracted requirements: {extracted.requirements}")
            except Exception as e:
                print(f"EXTRACTION FAILED WITH ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(main())