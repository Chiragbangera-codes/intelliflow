"""
RerankerService — optional cross-encoder re-ranking of retrieval candidates
(Milestone 7 Phase 5).

Hybrid retrieval (semantic + lexical + doc-aware → RRF) gives a strong,
*cheap* ordering. A cross-encoder re-ranker can sharpen the top of that list by
scoring each (query, chunk) pair jointly instead of comparing independent
embeddings — but it is heavier, so it is strictly OPTIONAL and OFF by default.

Design constraints (verbatim intent — Phase 5 / 22):
  - Behind a flag. settings.AI_RERANK_ENABLED defaults to False. When disabled,
    rerank() is a pure pass-through and the model is NEVER loaded. The whole
    system stays fully functional with reranking off — this class only ever
    *reorders* an already-authorized, already-ranked list.
  - Small model only. The default cross-encoder is ms-marco-MiniLM-L-6-v2
    (~22M params, ~80 MB) which fits comfortably inside the ~3.75 GiB RAM
    budget alongside the embedding model and Torch (already resident). No large
    cross-encoder is installed or loaded blindly.
  - CPU only. device="cpu" is forced — no CUDA.
  - Lazy, process-local singleton. The model loads on the first *enabled*
    rerank() call and only in the process that serves search/chat (the API).
    Background workers (OCR/embedding) never call rerank(), so they never pay
    the memory cost.
  - Never weakens security or breaks retrieval. Reordering only touches a list
    of already-authorized SearchResult objects; it fetches nothing and reveals
    nothing new. If the model fails to load or score, we log and return the
    original RRF order — a degraded rank is always preferable to a broken query.

Testing:
  - CrossEncoder is imported at module level so tests can patch
    app.services.reranker_service.CrossEncoder with no real download. The class
    is only *instantiated* on first enabled use (lazy), never at import time.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import settings
from app.schemas.search import SearchResult

logger = logging.getLogger(__name__)

# Defined at module level as None so tests can patch app.services.reranker_service.CrossEncoder
# without importing torch at module import time.
CrossEncoder: Any = None

# ---------------------------------------------------------------------------
# Module-level lazy initialization (mirrors embedding_service)
# ---------------------------------------------------------------------------
_model_lock = threading.Lock()
_model_instance: Any = None


def _get_reranker() -> Any:
    """
    Return the singleton CrossEncoder, loading it on first call.

    Thread-safe double-checked locking, identical in shape to the embedding
    model loader. Forced onto CPU (no CUDA) and bounded to a sane max sequence
    length so a pathologically long chunk cannot blow up tokenisation cost.
    """
    global _model_instance, CrossEncoder  # noqa: PLW0603
    if _model_instance is None:
        with _model_lock:
            if _model_instance is None:
                logger.info(
                    "Loading reranker model '%s' (first call — this may take a moment).",
                    settings.AI_RERANK_MODEL,
                )
                if CrossEncoder is None:
                    from sentence_transformers import CrossEncoder as _CE

                    CrossEncoder = _CE

                _model_instance = CrossEncoder(
                    settings.AI_RERANK_MODEL,
                    max_length=512,
                    device="cpu",
                )
                logger.info("Reranker model '%s' loaded successfully.", settings.AI_RERANK_MODEL)
    return _model_instance


class RerankerService:
    """Optional cross-encoder re-ranking over authorized retrieval results."""

    def rerank(
        self,
        *,
        query: str,
        results: list[SearchResult],
        top_n: int,
    ) -> list[SearchResult]:
        """
        Re-score and reorder the leading `top_n` results with the cross-encoder.

        Only the first `top_n` results are re-scored (the expensive part). Each
        reranked result gets a fresh copy whose `score` is the cross-encoder
        relevance (honouring the SearchResult.score contract: "RRF, or
        cross-encoder when reranking is enabled"); the head is then ordered by
        that score, descending. Any tail beyond top_n keeps its original RRF
        score and order and always stays *after* the reranked head. Inputs are
        never mutated in place — copies are returned via model_copy.

        Pass-through (returns `results` unchanged, model NOT loaded) when:
          - reranking is disabled (settings.AI_RERANK_ENABLED is False),
          - there are fewer than 2 results (nothing to reorder), or
          - top_n < 1.

        On any model/scoring error the original list is returned unchanged:
        reranking is a best-effort enhancement, never a hard dependency.

        Args:
            query:   The user's natural-language query.
            results: Authorized, RRF-ranked results (RBAC already enforced).
            top_n:   How many leading results to re-score (AI_RERANK_TOP_N).
        """
        if not settings.AI_RERANK_ENABLED or len(results) < 2 or top_n < 1:
            return results

        head = results[:top_n]
        tail = results[top_n:]

        try:
            model = _get_reranker()
            pairs = [(query, r.content) for r in head]
            scores = model.predict(pairs)
        except Exception:
            # Never let an optional reranker break retrieval — fall back to RRF.
            logger.exception("Reranking failed; falling back to RRF order.")
            return results

        # Attach cross-encoder scores and sort by score desc; the original
        # position breaks ties so the ordering is fully deterministic.
        scored = [
            (float(scores[i]), i, head[i].model_copy(update={"score": float(scores[i])}))
            for i in range(len(head))
        ]
        scored.sort(key=lambda t: (-t[0], t[1]))
        reranked_head = [item for _score, _idx, item in scored]

        logger.info(
            "Reranked %d/%d results (query_len=%d, tail_kept=%d).",
            len(reranked_head),
            len(results),
            len(query),
            len(tail),
        )
        return reranked_head + tail


# ---------------------------------------------------------------------------
# Module-level singleton — import this throughout the application
# ---------------------------------------------------------------------------
reranker_service = RerankerService()
