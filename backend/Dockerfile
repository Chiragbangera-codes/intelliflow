# =============================================================================
# IntelliFlow AI — Backend Dockerfile
#
# Multi-stage build:
#   base        — shared Python base layer
#   development — hot-reload dev server (used by docker-compose)
#   production  — optimized, non-root production image
#
# Build args:
#   SKIP_TORCH=true   — skip PyTorch/SentenceTransformers installation.
#                       Use this for cloud deployments that use
#                       EMBEDDING_PROVIDER=huggingface and AI_RERANK_ENABLED=false,
#                       saving ~2 GB of image size and memory.
#                       Default: false (install PyTorch for local/full deployments).
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base — shared dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
# (unbuffered output is important so logs appear immediately in Docker)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by psycopg2, asyncpg, and Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Build arg: set SKIP_TORCH=true to skip heavy ML libraries (cloud deployments).
ARG SKIP_TORCH=true

# Install Python dependencies.
# When SKIP_TORCH=true (cloud / HuggingFace embeddings):
#   - PyTorch, torchvision, sentence-transformers are NOT installed.
#   - Saves ~2 GB image size and ~600 MB runtime memory.
#   - EmbeddingService and RerankerService safely lazy-import these; they will
#     raise an ImportError at runtime only if the "local" provider is actually
#     called, which never happens in a correctly-configured cloud deployment.
# When SKIP_TORCH=false (default, local development / full deployment):
#   - CPU-only PyTorch is installed first to prevent pip from pulling the
#     multi-GB CUDA variant via sentence-transformers.
RUN pip install --no-cache-dir --upgrade pip && \
    if [ "$SKIP_TORCH" = "true" ]; then \
        echo "==> SKIP_TORCH=true: skipping PyTorch and sentence-transformers." && \
        pip install --no-cache-dir \
            $(grep -v -E '^(sentence-transformers|torch|torchvision)' requirements.txt | tr '\n' ' '); \
    else \
        echo "==> SKIP_TORCH=false: installing PyTorch (CPU) and sentence-transformers." && \
        pip install --no-cache-dir \
            torch==2.5.1+cpu \
            torchvision==0.20.1+cpu \
            --index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# -----------------------------------------------------------------------------
# Stage 2: Development — hot-reload via uvicorn --reload
# -----------------------------------------------------------------------------
FROM base AS development

# Source is mounted as a volume in docker-compose; we copy it here only
# so the image can be used standalone if needed.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app"]

# -----------------------------------------------------------------------------
# Stage 3: Production — non-root user, no dev tools
# -----------------------------------------------------------------------------
FROM base AS production

# Create a dedicated non-root user for security
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --create-home appuser

COPY --chown=appuser:appgroup . .
RUN chmod +x /app/start.sh

USER appuser

EXPOSE 8000

# Default entrypoint launches both FastAPI and Celery worker in memory-constrained cloud environments.
# (Overridden by docker-compose.prod.yml if running multi-container)
CMD ["/app/start.sh"]
