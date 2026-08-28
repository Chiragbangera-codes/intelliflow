/**
 * Semantic search service — Milestone 7 Phase 2.
 *
 * Provides the API client call for POST /api/v1/search.
 *
 * Uses the shared Axios instance (apiClient) which:
 *   - Attaches the JWT access token automatically via request interceptor.
 *   - Handles 401 with transparent token refresh.
 *
 * No second HTTP client is created here.
 */

import apiClient from "./api";
import type { ApiResponse, SearchData, SearchRequest } from "@/types";

/**
 * Execute a semantic search over the authenticated user's authorized documents.
 *
 * The backend:
 *   1. Embeds the query using the existing EmbeddingService singleton.
 *   2. Searches FAISS for candidate chunks.
 *   3. Resolves candidates through PostgreSQL (single batched query).
 *   4. Enforces document ownership (RBAC) — admin/hr get global access.
 *   5. Returns ranked results ordered by ascending L2 distance.
 *
 * Results only include documents the authenticated user is authorized to see.
 * The existence of inaccessible documents is never revealed.
 *
 * @param request - Search query and optional parameters.
 * @returns ApiResponse wrapping SearchData with ranked results.
 */
export async function semanticSearch(
  request: SearchRequest,
): Promise<ApiResponse<SearchData>> {
  const response = await apiClient.post<ApiResponse<SearchData>>(
    "/search",
    request,
  );
  return response.data;
}
