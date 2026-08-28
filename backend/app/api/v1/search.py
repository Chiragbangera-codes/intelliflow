"""
Search API — POST /api/v1/search.

Provides:
  POST /api/v1/search — authenticated semantic document search

Security:
  - Requires a valid JWT bearer token via get_current_user.
  - Ownership enforcement is applied entirely server-side inside
    SearchService (two-layer RBAC).
  - The caller MUST NOT supply owner_id or chunk IDs — authorization is
    derived exclusively from the authenticated token.

Response envelope follows the project-wide convention:
  { "success": true, "message": "...", "data": { ... } }
"""

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.search import SearchRequest, SearchResponse
from app.services.hybrid_search_service import HybridSearchService
from app.services.search_service import SearchService

router = APIRouter(
    prefix="/search",
    tags=["Search"],
)


def _get_service(db: AsyncSession = Depends(get_db)) -> SearchService:
    """Provide a SearchService instance with the injected DB session."""
    return SearchService(db)


def _get_hybrid_service(db: AsyncSession = Depends(get_db)) -> HybridSearchService:
    """Provide a HybridSearchService instance with the injected DB session."""
    return HybridSearchService(db)


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP address for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# =============================================================================
# POST /search — semantic document search
# =============================================================================


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    response_model=SearchResponse,
    summary="Semantic document search",
    description=(
        "Converts the natural-language query to a 384-dimensional embedding "
        "(EmbeddingService), searches FAISS for nearest-neighbour chunks, "
        "enforces document ownership (SearchRepository + SearchService), "
        "and applies an optional similarity threshold. "
        "admin and hr roles receive global access; other roles see only their "
        "own documents. Results are ordered by ascending L2 distance (most "
        "similar first)."
    ),
    responses={
        200: {"description": "Search completed — may return empty results."},
        401: {"description": "Not authenticated."},
        422: {"description": "Invalid request (blank query, top_k out of range, etc.)."},
        500: {"description": "Internal search failure."},
    },
)
async def semantic_search(
    payload: SearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: SearchService = Depends(_get_service),
) -> dict[str, Any]:
    """
    Execute a semantic search over the authenticated user's authorized documents.

    FAISS is used for candidate generation; PostgreSQL enforces document
    ownership and excludes soft-deleted records. FAISS results are NEVER
    trusted as authorization proof.
    """
    search_data = await svc.semantic_search(
        query=payload.query,
        actor=current_user,
        top_k=payload.top_k,
        min_score=payload.min_score,
        ip_address=_get_client_ip(request),
    )

    return {
        "success": True,
        "message": "Search completed successfully.",
        "data": search_data.model_dump(mode="json"),
    }
