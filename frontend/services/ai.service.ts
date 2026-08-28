/**
 * AI Chat service — Milestone 7 Phase 3.
 *
 * Provides the API client call for POST /api/v1/ai/chat.
 *
 * Uses the shared Axios instance (apiClient) which:
 *   - Attaches the JWT access token automatically via request interceptor.
 *   - Handles 401 with transparent token refresh.
 *
 * No second HTTP client is created here.
 *
 * Security note:
 *   Authorization is enforced entirely server-side. The client never supplies
 *   owner_id, chunk_ids, or any RBAC parameter — only the question and
 *   optional retrieval tuning. The JWT determines what documents are accessible.
 */

import apiClient from "./api";
import type { AIChatRequest, AIChatResponseData, ApiResponse } from "@/types";

/**
 * Ask a natural-language question about the authenticated user's documents.
 *
 * The backend pipeline:
 *   1. Embeds the question via EmbeddingService (Phase 2 singleton).
 *   2. Searches FAISS for candidate chunks.
 *   3. Resolves candidates through PostgreSQL (single batched query).
 *   4. Enforces RBAC — only authorized chunks proceed.
 *   5. Assembles a grounded context with ContextBuilder.
 *   6. Generates an answer via Ollama (LLMService).
 *   7. Persists the Q&A exchange in ai_conversations.
 *   8. Returns the answer with cited sources.
 *
 * If no authorized chunks are found, a deterministic fallback is returned
 * without calling the LLM — preventing hallucination on out-of-scope queries.
 *
 * @param request - Chat message and optional retrieval parameters.
 * @returns ApiResponse wrapping AIChatResponseData with answer and sources.
 * @throws AxiosError on 401, 403, 422, 503, or 500.
 */
export async function chat(
  request: AIChatRequest,
): Promise<ApiResponse<AIChatResponseData>> {
  const response = await apiClient.post<ApiResponse<AIChatResponseData>>(
    "/ai/chat",
    request,
    { timeout: 180_000 }, // 180s timeout for RAG retrieval + LLM generation
  );
  return response.data;
}
