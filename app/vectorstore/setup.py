import os
import chromadb
from sentence_transformers import SentenceTransformer

# ── ChromaDB path ──────────────────────────────────────────────────────────────
# In production (ECS + EFS) set CHROMA_DB_PATH to the EFS mount path.
# Locally defaults to ./chroma_db (relative to CWD, i.e. project root).
_CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
os.makedirs(_CHROMA_PATH, exist_ok=True)

# Persistent client -> data survives between restarts (backed by EFS in prod)
_client = chromadb.PersistentClient(path=_CHROMA_PATH)

# Loaded once and reused everywhere (loading it repeatedly is slow)
_embedding_model = None

def _get_embedding_model():
    """Lazily loads the embedding model on first actual use, instead of
    blocking at import time - this lets FastAPI bind to its port
    immediately on startup, rather than waiting for a slow model download
    on platforms like Render's free tier."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model

import re


def get_resume_collection(session_id: str | None = None):
    """Collection for resume chunks. When session_id is provided,
    isolates the collection per session so each device starts clean."""
    if not session_id or session_id in ("default", "global"):
        col_name = "resume_chunks"
    else:
        clean = re.sub(r"[^a-zA-Z0-9_-]", "_", str(session_id).strip()).strip("_")
        if not clean:
            clean = "default"
        col_name = f"res_{clean}"[:60]
        if not col_name[-1].isalnum():
            col_name = col_name[:-1] + "0"

    return _client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"},
    )


def get_job_collection():
    """Single collection for all job posting chunks (used later in Phase 4)."""
    return _client.get_or_create_collection(
        name="job_chunks",
        metadata={"hnsw:space": "cosine"},
    )


def embed_text(text: str) -> list[float]:
    """Turn a piece of text into a vector using the local embedding model."""
    model = _get_embedding_model()
    vector = model.encode(text)
    return vector.tolist()

def embed_and_store(chunks: list[dict], collection):
    """
    Embed a list of chunk dicts and store them in the given Chroma collection.
    Every key in a chunk dict except 'id' and 'text' is stored as metadata,
    so this works for both resume chunks (section, context) and job chunks
    (section, job_id, title, company, location, url) without changes.
    """
    if not chunks:
        return
    ids = [chunk["id"] for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    embeddings = [embed_text(chunk["text"]) for chunk in chunks]

    metadatas = []
    for chunk in chunks:
        meta = {k: v for k, v in chunk.items() if k not in ("id", "text")}
        # Chroma requires metadata values to be str/int/float/bool, never None
        meta = {k: (v if v is not None else "") for k, v in meta.items()}
        metadatas.append(meta)

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )