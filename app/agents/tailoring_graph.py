import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from typing import TypedDict
from langgraph.graph import StateGraph, END

from app.agents.gap_analysis import build_gap_report,build_gap_report_isolated, GapReport
from app.agents.tailoring import rewrite_bullet, full_validation


class TailoringState(TypedDict):
    job_requirements: list[str]
    gap_report: GapReport
    rewritten_bullets: list[dict]
    flagged_for_review: list[dict]


def analyze_gap_node(state: TailoringState) -> TailoringState:
    """Step 1: Run gap analysis against the job requirements.
    Uses the isolated, per-requirement version for higher accuracy, since
    this is the single-job path a user directly acts on."""
    print("  [node: analyze_gap] Running gap analysis (isolated per-requirement)...")
    report = build_gap_report_isolated(
        job_description="",
        job_requirements=state["job_requirements"],
    )
    return {**state, "gap_report": report}


def rewrite_node(state: TailoringState) -> TailoringState:
    """Step 2: For each weak-phrasing item, attempt a rewrite."""
    print(f"  [node: rewrite] Rewriting {len(state['gap_report'].weak_phrasing)} weak-phrasing bullets...")
    rewritten = []
    for item in state["gap_report"].weak_phrasing:
        result = rewrite_bullet(
            original_bullet=item.resume_text,
            requirement=item.requirement,
            suggestion_hint=item.suggestion,
        )
        rewritten.append({
            "chunk_id": item.resume_chunk_id,
            "requirement": item.requirement,
            "original": result.original_text,
            "rewritten": result.rewritten_text,
            "reasoning": result.reasoning,
        })
    return {**state, "rewritten_bullets": rewritten}


def validate_node(state: TailoringState) -> TailoringState:
    """Step 3: Run full (keyword + LLM fact-check) validation; split safe vs flagged."""
    print(f"  [node: validate] Validating {len(state['rewritten_bullets'])} rewrites...")
    flagged = []
    safe = []
    for item in state["rewritten_bullets"]:
        validation = full_validation(item["original"], item["rewritten"])
        item["validation"] = validation
        if validation["is_safe"]:
            safe.append(item)
        else:
            flagged.append(item)
    return {**state, "rewritten_bullets": safe, "flagged_for_review": flagged}


# Build the graph
graph = StateGraph(TailoringState)
graph.add_node("analyze_gap", analyze_gap_node)
graph.add_node("rewrite", rewrite_node)
graph.add_node("validate", validate_node)

graph.set_entry_point("analyze_gap")
graph.add_edge("analyze_gap", "rewrite")
graph.add_edge("rewrite", "validate")
graph.add_edge("validate", END)

tailoring_app = graph.compile()


if __name__ == "__main__":
    print("=== TAILORING AGENT (LangGraph) TEST ===\n")

    initial_state = {
        "job_requirements": [
            "React frontend development",
            "ETL pipeline development",
            "AWS cloud experience",
            "Python and machine learning",
        ],
        "gap_report": None,
        "rewritten_bullets": [],
        "flagged_for_review": [],
    }

    final_state = tailoring_app.invoke(initial_state)

    print("\n=== GAP REPORT ===")
    print(f"Matched: {final_state['gap_report'].matched_skills}")
    print(f"Missing: {final_state['gap_report'].missing_skills}")

    print("\n=== SAFE REWRITES ===")
    for item in final_state["rewritten_bullets"]:
        print(f"[{item['chunk_id']}] for '{item['requirement']}'")
        print(f"  Original:  {item['original']}")
        print(f"  Rewritten: {item['rewritten']}")
        print()

    print("=== FLAGGED FOR HUMAN REVIEW ===")
    for item in final_state["flagged_for_review"]:
        print(f"[{item['chunk_id']}] for '{item['requirement']}'")
        print(f"  Original:  {item['original']}")
        print(f"  Rewritten: {item['rewritten']}")
        if item['validation']['fact_check']['has_unsupported_claim']:
            print(f"  Fact-check flagged: {item['validation']['fact_check']['unsupported_claims']}")
        if not item['validation']['keyword_check']['is_safe']:
            print(f"  Keyword check flagged: {item['validation']['keyword_check']['new_keywords_introduced']}")
        print()