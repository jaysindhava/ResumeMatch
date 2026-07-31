import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.gap_analysis import hybrid_search, bm25_search, vector_search
from app.eval.golden_dataset import RETRIEVAL_GOLDEN_SET


def hit_rate_at_k(search_fn, golden_set: list[dict], k: int = 3) -> dict:
    """
    For each golden test case, checks whether ANY of the correct chunk_ids
    appear within the top-k results returned by search_fn.
    Returns the overall hit rate plus per-query pass/fail details.
    """
    hits = 0
    details = []

    for case in golden_set:
        results = search_fn(case["query"], n_results=k)
        retrieved_ids = [r["id"] for r in results]

        is_hit = any(correct_id in retrieved_ids for correct_id in case["correct_chunk_ids"])
        if is_hit:
            hits += 1

        details.append({
            "query": case["query"],
            "correct_ids": case["correct_chunk_ids"],
            "retrieved_ids": retrieved_ids,
            "hit": is_hit,
        })

    hit_rate = hits / len(golden_set)
    return {"hit_rate": hit_rate, "hits": hits, "total": len(golden_set), "details": details}


if __name__ == "__main__":
    print("=== RETRIEVAL EVALUATION ===\n")

    methods = {
        "BM25 only": bm25_search,
        "Vector only": vector_search,
        "Hybrid (BM25 + Vector, RRF fused)": hybrid_search,
    }

    for k in [1, 3]:
        print(f"--- hit-rate@{k} ---")
        for method_name, method_fn in methods.items():
            result = hit_rate_at_k(method_fn, RETRIEVAL_GOLDEN_SET, k=k)
            print(f"{method_name}: {result['hits']}/{result['total']} = {result['hit_rate']:.1%}")
        print()

    print("=== DETAILED BREAKDOWN (Hybrid @ k=1) ===\n")
    hybrid_result = hit_rate_at_k(hybrid_search, RETRIEVAL_GOLDEN_SET, k=1)
    for d in hybrid_result["details"]:
        status = "✅" if d["hit"] else "❌"
        print(f"{status} \"{d['query']}\"")
        print(f"   Expected: {d['correct_ids']}")
        print(f"   Got:      {d['retrieved_ids']}")
        print()