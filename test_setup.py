import langchain
import langgraph
import llama_index
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import os

load_dotenv()

print("✅ Core packages imported successfully")
print("Google API key loaded:", bool(os.getenv("GOOGLE_API_KEY")))
print("Adzuna App ID loaded:", bool(os.getenv("ADZUNA_APP_ID")))
print("LangSmith key loaded:", bool(os.getenv("LANGCHAIN_API_KEY")))

# This will download a small embedding model the first time (~90MB) - only happens once
print("\nLoading local embedding model (first run downloads ~90MB, be patient)...")
model = SentenceTransformer("all-MiniLM-L6-v2")
test_embedding = model.encode("This is a test sentence.")
print(f"✅ Embedding model works. Vector dimension: {len(test_embedding)}")