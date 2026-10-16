# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /home/user/app

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── Hugging Face Spaces: must run as non-root user with UID 1000 ──────────────
RUN useradd -m -u 1000 user

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code (owned by the non-root user)
COPY --chown=user:user app/ ./app/

# Writable directories — HF Spaces only allows writes to /tmp and /home/user
# ChromaDB + ATS SQLite will live here (set via env vars)
RUN mkdir -p /home/user/data && chown -R user:user /home/user/data
RUN mkdir -p /tmp/chroma_db /tmp/uploads

# Point ML caches to /tmp (writable, no quota issues)
ENV TRANSFORMERS_CACHE=/tmp/transformers_cache
ENV HF_HOME=/tmp/hf_home
ENV TORCH_HOME=/tmp/torch_home
ENV HF_HUB_OFFLINE=1

# ChromaDB + ATS paths (can be overridden via HF Space Secrets)
ENV CHROMA_DB_PATH=/home/user/data/chroma_db
ENV ATS_DB_PATH=/home/user/data/ats.db

# Switch to non-root user (required by HF Spaces)
USER user
ENV HOME=/home/user
ENV PATH=/home/user/.local/bin:$PATH

# HF Spaces maps app_port 7860 to the public URL
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/')" || exit 1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
