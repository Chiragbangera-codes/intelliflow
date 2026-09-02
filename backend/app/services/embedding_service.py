"""
EmbeddingService — text-to-vector embedding using sentence-transformers.

Model: sentence-transformers/all-MiniLM-L6-v2
  - Produces 384-dimensional vectors.
  - Vectors are L2-normalized by the model internally, so cosine similarity
    and L2 distance produce equivalent rankings. We use IndexFlatL2 in FAISS,
    which is correct for normalized vectors.

Design decisions:
  - Singleton pattern via module-level instance: the SentenceTransformer model
    is loaded once per process (lazy, on first use) and never reloaded.
  - Batch embedding is always used for documents to leverage the model's
    internal batching and GPU/CPU parallelism.
  - This module has NO knowledge of FAISS or PostgreSQL — it is a pure
    text → vector transformer.

Usage:
    from app.services.embedding_service import embedding_service

    vector = embedding_service.embed_text("some text")
    vectors = embedding_service.embed_batch(["text one", "text two"])
"""

from __future__ import annotations

import logging
import threading
from typing import cast

try:
    from sentence_transformers import SentenceTransformer  # noqa: E402
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment, misc]

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level lazy initialization
# ---------------------------------------------------------------------------
_model_lock = threading.Lock()
_model_instance: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """
    Return the singleton SentenceTransformer model, loading it on first call.

    Thread-safe: uses a module-level lock to prevent multiple threads from
    attempting simultaneous model initialization.
    """
    global _model_instance  # noqa: PLW0603
    if _model_instance is None:
        with _model_lock:
            # Double-checked locking: re-test after acquiring the lock.
            if _model_instance is None:
                logger.info(
                    "Loading embedding model '%s' (first call — this may take a moment).",
                    settings.EMBEDDING_MODEL,
                )
                # SentenceTransformer is imported at module level so that
                # unittest.mock.patch("app.services.embedding_service.SentenceTransformer")
                # works correctly. The class is NOT instantiated here at import
                # time — only on this first call (lazy singleton pattern).
                _model_instance = SentenceTransformer(settings.EMBEDDING_MODEL)
                logger.info(
                    "Embedding model '%s' loaded successfully.",
                    settings.EMBEDDING_MODEL,
                )
    return _model_instance


class EmbeddingService:
    """
    Provides text → float-vector embeddings using sentence-transformers.

    The underlying model is a module-level singleton.  Multiple
    EmbeddingService instances all share the same loaded model, so it is
    safe to instantiate this class wherever needed without incurring repeated
    model loading.

    Normalization:
        all-MiniLM-L6-v2 normalizes output vectors to unit length (L2 norm = 1).
        Combined with FAISS IndexFlatL2, the ranking is equivalent to cosine
        similarity ranking.  No additional normalization is applied here.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> list[float]:
        """
        Embed a single string and return a float vector.

        Args:
            text: The text to embed. Empty strings produce a zero-ish vector
                  (model-dependent behaviour); callers should validate input.

        Returns:
            384-dimensional float list (all-MiniLM-L6-v2).
        """
        model = _get_model()
        vector = model.encode(text, normalize_embeddings=True)
        return cast(list[float], vector.tolist())

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of strings and return a list of float vectors.

        Uses the model's internal batching for efficiency — significantly
        faster than calling embed_text() in a loop.

        Args:
            texts: List of strings to embed. Order is preserved.

        Returns:
            List of 384-dimensional float lists, one per input text.
        """
        if not texts:
            return []

        model = _get_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]


# ---------------------------------------------------------------------------
# Module-level singleton — import this throughout the application
# ---------------------------------------------------------------------------
embedding_service = EmbeddingService()
