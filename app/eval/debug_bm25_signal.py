import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.gap_analysis import get_all_resume_chunks, build_bm25_index, tokenize

FAILING_QUERIES = [
    "React frontend development",
    "machine learning model development",
    "RESTful API development",
    "PostgreSQL database experience",  # also failing, worth checking too
]


def inspect_bm25_scores(query: str):
    chunks = get_all_resume_chunks()
    bm25 = build_bm25_index(chunks["documents"])
    tokenized_query = tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    print(f"\nQuery: \"{query}\"")
    print(f"Tokenized query: {tokenized_query}")

    nonzero_count = sum(1 for s in scores if s > 0)
    zero_count = len(scores) - nonzero_count
    print(f"Chunks with NONZERO BM25 score: {nonzero_count} / {len(scores)}")
    print(f"Chunks with ZERO BM25 score:    {zero_count} / {len(scores)}")

    # Show top 5 by BM25 score, so we can see if the "top" results are
    # meaningfully separated or all clustered near zero
    scored = list(zip(chunks["ids"], scores))
    scored.sort(key=lambda x: x[1], reverse=True)
    print("Top 5 BM25 scores:")
    for chunk_id, score in scored[:5]:
        print(f"  {chunk_id}: {score:.4f}")


if __name__ == "__main__":
    print("=== BM25 SIGNAL STRENGTH INVESTIGATION ===")
    for query in FAILING_QUERIES:
        inspect_bm25_scores(query)