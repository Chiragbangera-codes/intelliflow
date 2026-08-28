# =============================================================================
# IntelliFlow AI — Backend Dockerfile
#
# Multi-stage build:
#   base        — shared Python base layer
#   development — hot-reload dev server (used by docker-compose)
#   production  — optimized, non-root production image
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

# Copy and install Python dependencies before copying source
# (Cached by Docker layer unless requirements.txt changes)
COPY requirements.txt .
# Install CPU-only PyTorch FIRST so sentence-transformers does not pull the
# multi-GB CUDA variant.  The --extra-index-url is only used for torch/torchvision.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        torch==2.5.1+cpu \
        torchvision==0.20.1+cpu \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

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
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 8000

# Use multiple workers in production; adjust based on available CPUs
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
