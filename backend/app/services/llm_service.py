"""
LLMService — Ollama HTTP client for text generation.

Responsibilities:
  - Communicate with the Ollama REST API (POST /api/generate).
  - Apply configured model, temperature, timeout, and max tokens.
  - Handle connection failures gracefully.
  - Handle malformed / empty responses gracefully.
  - Return only the generated text string.

Security contract:
  - NEVER performs authorization.
  - NEVER accesses PostgreSQL directly.
  - Receives fully-assembled prompts from the RAG service.
  - The caller (RAGService) is responsible for ensuring only authorized
    content reaches this service.

Ollama API used:
  POST {OLLAMA_BASE_URL}/api/generate
  {
    "model":  "<configured model>",
    "system": "<system prompt>",
    "prompt": "<user prompt>",
    "stream": false,
    "options": {
      "temperature": <AI_TEMPERATURE>,
      "num_predict": <AI_MAX_RESPONSE_TOKENS>
    }
  }

  Response: { "response": "...", "done": true, ... }

Error handling:
  - Connection / DNS failures  → LLMUnavailableError
  - Timeout                    → LLMUnavailableError
  - Non-2xx HTTP status        → LLMUnavailableError
  - Missing / empty response   → LLMUnavailableError
  - All errors are logged internally; callers receive only LLMUnavailableError.

Usage:
    from app.services.llm_service import LLMService, LLMUnavailableError

    svc = LLMService()
    try:
        text = await svc.generate(system_prompt="...", user_prompt="...")
    except LLMUnavailableError:
        # Return 503 to caller
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Custom exception
# =============================================================================


class LLMUnavailableError(Exception):
    """
    Raised when the LLM provider is unreachable, times out, or returns
    an unusable response.

    Callers must catch this and return HTTP 503 to clients.
    Internal details (URLs, stack traces) must never be forwarded to clients.
    """


# =============================================================================
# LLM Service
# =============================================================================


class LLMService:
    """
    Thin async wrapper around the Ollama /api/generate endpoint.

    One instance per request is acceptable; the underlying httpx.AsyncClient
    is created fresh per generate() call to avoid connection pool issues in
    a multi-worker environment. For high-concurrency scenarios a shared client
    with connection pooling should be considered (future improvement).
    """

    def __init__(self) -> None:
        self._base_url: str = settings.OLLAMA_BASE_URL.rstrip("/")
        self._model: str = settings.OLLAMA_MODEL
        self._timeout: int = settings.OLLAMA_TIMEOUT_SECONDS
        self._temperature: float = settings.AI_TEMPERATURE
        self._max_tokens: int = settings.AI_MAX_RESPONSE_TOKENS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Generate a text completion using the configured Ollama model.

        Args:
            system_prompt: Instructions for the LLM (anti-hallucination rules,
                           context framing). This is always higher priority than
                           the user prompt and document content.
            user_prompt:   The user's question. Document context is embedded in
                           the system_prompt, NOT here, so the LLM treats it as
                           data rather than instructions.

        Returns:
            The generated text string. Never empty (raises on empty response).

        Raises:
            LLMUnavailableError: On any connectivity, timeout, or parsing issue.
        """
        endpoint = f"{self._base_url}/api/generate"
        payload: dict[str, object] = {
            "model": self._model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "keep_alive": "24h",
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_tokens,
            },
        }

        logger.debug(
            "Sending generate request to Ollama: model=%s prompt_len=%d system_len=%d",
            self._model,
            len(user_prompt),
            len(system_prompt),
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(endpoint, json=payload)
        except httpx.ConnectError as exc:
            logger.error("Ollama connection failed: %s", exc)
            raise LLMUnavailableError("Cannot connect to the LLM provider.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Ollama request timed out after %ds.", self._timeout)
            raise LLMUnavailableError("LLM provider request timed out.") from exc
        except httpx.RequestError as exc:
            logger.error("Ollama HTTP request error: %s", exc)
            raise LLMUnavailableError("LLM provider request error.") from exc

        if response.status_code >= 400:
            logger.error(
                "Ollama returned HTTP %d: %s",
                response.status_code,
                response.text[:200],
            )
            raise LLMUnavailableError(
                f"LLM provider returned unexpected status {response.status_code}."
            )

        try:
            data = response.json()
        except Exception as exc:
            logger.error("Ollama response is not valid JSON: %s", response.text[:200])
            raise LLMUnavailableError("LLM provider returned a malformed response.") from exc

        generated_text: str | None = data.get("response")
        if not generated_text or not generated_text.strip():
            logger.warning("Ollama returned an empty or blank response body.")
            raise LLMUnavailableError("LLM provider returned an empty response.")

        logger.debug(
            "Ollama generation complete: model=%s response_len=%d",
            self._model,
            len(generated_text),
        )

        return generated_text
