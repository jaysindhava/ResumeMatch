# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System deps needed for chromadb / sentence-transformers native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install Python deps into a prefix we can copy across stages
RUN pip install --no-cache-dir --prefix=/install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Runtime system deps only (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/

# ChromaDB persistent directory — this path will be mounted as EFS in AWS
RUN mkdir -p ./chroma_db

# Resume uploads directory — files are stored in S3 in production;
# this fallback dir is used for local testing only
RUN mkdir -p ./data/resumes

# Expose FastAPI port
EXPOSE 8000

# Health-check so ECS knows when the container is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
