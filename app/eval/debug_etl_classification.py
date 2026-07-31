import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.gap_analysis import build_gap_report, hybrid_search

if __name__ == "__main__":
    print("=== ISOLATED ETL CLASSIFICATION TEST ===\n")

    # Show exactly what evidence gets retrieved for this requirement,
    # so we can see precisely what the LLM is being shown
    evidence = hybrid_search("ETL pipeline development", n_results=3)
    print("Retrieved evidence for 'ETL pipeline development':")
    for e in evidence:
        print(f"  [{e['id']}] {e['text']}")

    print("\nRunning gap report on JUST this one requirement...")
    report = build_gap_report(
        job_description="",
        job_requirements=["ETL pipeline development"],
    )

    print(f"\nMatched: {report.matched_skills}")
    print(f"Missing: {report.missing_skills}")
    print(f"Weak phrasing: {[(w.requirement, w.resume_text) for w in report.weak_phrasing]}")