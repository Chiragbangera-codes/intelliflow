"""
EmbeddingService — text-to-vector embedding supporting local and cloud providers.

Providers:
  - "local" (default): sentence-transformers/all-MiniLM-L6-v2 running locally.
    True dynamic lazy import: torch and sentence_transformers are ONLY imported
    when the local provider is actually invoked, preventing memory bloat in cloud mode.
  - "huggingface": Hugging Face Router serverless inference API.
    Zero PyTorch/sentence-transformers memory overhead in the container.
    Returns mathematically equivalent 384-dimensional L2-normalized vectors.

Model: sentence-transformers/all-MiniLM-L6-v2
  - Produces 384-dimensional vectors.
  - Vectors are L2-normalized (unit length), so cosine similarity and L2 distance
    produce equivalent rankings in FAISS IndexFlatL2.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Ensure HuggingFace cache directory is writable in non-root or container environments
if not os.environ.get("HF_HOME"):
    for _candidate in ("/app/data/cache/huggingface", "/tmp/huggingface"):
        try:
            Path(_candidate).mkdir(parents=True, exist_ok=True)
            os.environ["HF_HOME"] = _candidate
            break
        except OSError:
            continue

# Defined at module level as None so tests can patch app.services.embedding_service.SentenceTransformer
# without importing torch at module import time.
SentenceTransformer: Any = None

EXPECTED_EMBEDDING_DIM = 384


class EmbeddingError(Exception):
    """Base exception for embedding generation failures."""


class EmbeddingRateLimitError(EmbeddingError):
    """Raised when hosted embedding provider rate limit (HTTP 429) is exceeded."""


class EmbeddingUnavailableError(EmbeddingError):
    """Raised when hosted embedding provider is unreachable or misconfigured."""


# ---------------------------------------------------------------------------
# Module-level lazy initialization for local SentenceTransformer
# ---------------------------------------------------------------------------
_model_lock = threading.Lock()
_model_instance: Any = None


def _get_local_model() -> Any:
    """
    Return the singleton SentenceTransformer model, loading it on first call.

    Thread-safe double-checked locking. Dynamically imports SentenceTransformer
    only when local provider is active.
    """
    global _model_instance, SentenceTransformer  # noqa: PLW0603
    if _model_instance is not None:
        return _model_instance

    with _model_lock:
        if _model_instance is not None:
            return _model_instance

        logger.info(
            "Loading local embedding model '%s' (first call — this may take a moment).",
            settings.EMBEDDING_MODEL,
        )
        if SentenceTransformer is None:
            from sentence_transformers import SentenceTransformer as _ST

            SentenceTransformer = _ST

        _model_instance = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Local embedding model '%s' loaded successfully.", settings.EMBEDDING_MODEL)
        return _model_instance


class EmbeddingService:
    """
    Provides text → float-vector embeddings using local or hosted providers.

    Normalization:
        all-MiniLM-L6-v2 normalizes output vectors to unit length (L2 norm = 1).
        Combined with FAISS IndexFlatL2, the ranking is equivalent to cosine
        similarity ranking.
    """

    def __init__(self) -> None:
        self._provider = settings.EMBEDDING_PROVIDER.lower()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> list[float]:
        """
        Embed a single string and return a 384-dimensional float vector.
        """
        vectors = self.embed_batch([text])
        if not vectors:
            raise EmbeddingError("Failed to generate embedding for text.")
        return vectors[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of strings and return a list of 384-dimensional float vectors.
        """
        if not texts:
            return []

        if settings.EMBEDDING_PROVIDER.lower() == "huggingface":
            return self._embed_batch_huggingface(texts)

        return self._embed_batch_local(texts)

    # ------------------------------------------------------------------
    # Provider: Local SentenceTransformer
    # ------------------------------------------------------------------

    def _embed_batch_local(self, texts: list[str]) -> list[list[float]]:
        model = _get_local_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    # ------------------------------------------------------------------
    # Provider: Hugging Face Router Serverless Inference API
    # ------------------------------------------------------------------

    def _embed_batch_huggingface(self, texts: list[str]) -> list[list[float]]:
        hf_token = settings.HF_TOKEN
        if not hf_token or not hf_token.strip():
            raise EmbeddingUnavailableError(
                "HF_TOKEN is not configured for Hugging Face embeddings."
            )

        endpoint = f"{settings.HF_ROUTER_BASE_URL.rstrip('/')}/{settings.EMBEDDING_MODEL}"
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": texts,
            "options": {"wait_for_model": True},
        }

        max_retries = 3
        timeout_seconds = settings.HF_TIMEOUT_SECONDS

        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(timeout=timeout_seconds) as client:
                    response = client.post(endpoint, json=payload, headers=headers)
            except httpx.ConnectError as exc:
                logger.error("Hugging Face embedding connection error: %s", exc)
                raise EmbeddingUnavailableError("Cannot connect to Hugging Face embedding API.") from exc
            except httpx.TimeoutException as exc:
                logger.error("Hugging Face embedding request timed out after %ds", timeout_seconds)
                raise EmbeddingUnavailableError("Hugging Face embedding request timed out.") from exc
            except httpx.RequestError as exc:
                logger.error("Hugging Face embedding HTTP error: %s", exc)
                raise EmbeddingUnavailableError("Hugging Face embedding request failed.") from exc

            if response.status_code == 200:
                break

            if response.status_code == 429:
                logger.warning("Hugging Face embedding rate limit (429) hit: %s", response.text[:200])
                raise EmbeddingRateLimitError(
                    "Hugging Face embedding rate limit exceeded. Please try again shortly."
                )

            if response.status_code == 503 and attempt < max_retries:
                # Model loading — parse estimated time or use exponential backoff
                wait_time = 5.0 * (2 ** (attempt - 1))
                try:
                    data = response.json()
                    if isinstance(data, dict) and "estimated_time" in data:
                        wait_time = min(float(data["estimated_time"]), 20.0)
                except Exception:  # noqa: BLE001
                    pass

                logger.info(
                    "Hugging Face model loading (503). Retrying in %.1fs (attempt %d/%d)...",
                    wait_time,
                    attempt,
                    max_retries,
                )
                time.sleep(wait_time)
                continue

            # Non-retryable error
            logger.error(
                "Hugging Face embedding API error HTTP %d: %s",
                response.status_code,
                response.text[:200],
            )
            raise EmbeddingError(
                f"Hugging Face embedding API returned status {response.status_code}."
            )

        try:
            result = response.json()
        except Exception as exc:
            logger.error("Malformed JSON response from Hugging Face: %s", exc)
            raise EmbeddingError("Malformed JSON response from Hugging Face embedding API.") from exc

        # Handle shape verification
        # The endpoint returns list of float lists: [[f1, ... f384], ...]
        if not isinstance(result, list):
            raise EmbeddingError(f"Unexpected response type from Hugging Face: {type(result)}")

        # If a single string was passed, some endpoints return [f1, ... f384] directly
        if len(texts) == 1 and result and isinstance(result[0], int | float):
            result = [result]

        if len(result) != len(texts):
            raise EmbeddingError(
                f"Vector count mismatch: sent {len(texts)} texts, received {len(result)} vectors."
            )

        validated_vectors: list[list[float]] = []
        for idx, vec in enumerate(result):
            if not isinstance(vec, list) or len(vec) != EXPECTED_EMBEDDING_DIM:
                dim = len(vec) if isinstance(vec, list) else type(vec)
                raise EmbeddingError(
                    f"Vector dimension mismatch at index {idx}: expected {EXPECTED_EMBEDDING_DIM}, got {dim}."
                )
            validated_vectors.append([float(x) for x in vec])

        return validated_vectors


# ---------------------------------------------------------------------------
# Module-level singleton — import this throughout the application
# ---------------------------------------------------------------------------
embedding_service = EmbeddingService()
