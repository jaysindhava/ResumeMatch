import sys
import os

# Allow importing from app/ when running this script directly
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.vectorstore.setup import get_resume_collection, embed_text

collection = get_resume_collection()


def search(query: str, n_results: int = 3):
    query_embedding = embed_text(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
    )

    print(f"\nQuery: \"{query}\"")
    print("-" * 60)
    for i in range(len(results["ids"][0])):
        chunk_id = results["ids"][0][i]
        text = results["documents"][0][i]
        distance = results["distances"][0][i]
        section = results["metadatas"][0][i]["section"]
        print(f"{i+1}. [{chunk_id}] (section: {section}, distance: {distance:.4f})")
        print(f"   {text}")
    print()


if __name__ == "__main__":
    search("backend development experience with APIs")
    search("machine learning and predictive modeling")
    search("frontend development with React")
    search("leadership and team collaboration")
    search("academic background and degree")