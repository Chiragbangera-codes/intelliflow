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
    Async client for LLM text generation supporting both local Ollama and hosted Groq.

    Provider selection:
      - settings.LLM_PROVIDER == "groq"   → Groq Cloud API (chat/completions)
      - settings.LLM_PROVIDER == "ollama" → Local Ollama (/api/generate)
    """

    def __init__(self) -> None:
        self._provider: str = settings.LLM_PROVIDER.lower()

        # Local Ollama settings
        self._ollama_base_url: str = settings.OLLAMA_BASE_URL.rstrip("/")
        self._ollama_model: str = settings.OLLAMA_MODEL
        self._ollama_timeout: int = settings.OLLAMA_TIMEOUT_SECONDS

        # Hosted Groq Cloud API settings
        self._groq_base_url: str = settings.GROQ_BASE_URL.rstrip("/")
        self._groq_model: str = settings.GROQ_MODEL
        self._groq_api_key: str | None = settings.GROQ_API_KEY
        self._groq_timeout: int = settings.GROQ_TIMEOUT_SECONDS

        # Common generation parameters
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
        Generate a text completion using the configured LLM provider.

        Args:
            system_prompt: Instructions for the LLM (anti-hallucination rules, context).
            user_prompt:   The user's query or instruction.

        Returns:
            The generated text string. Never empty (raises on empty response).

        Raises:
            LLMUnavailableError: On any connectivity, timeout, rate-limit, or parsing issue.
        """
        if self._provider == "groq":
            return await self._generate_groq(system_prompt, user_prompt)
        return await self._generate_ollama(system_prompt, user_prompt)

    # ------------------------------------------------------------------
    # Hosted Groq Provider
    # ------------------------------------------------------------------

    async def _generate_groq(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if not self._groq_api_key:
            logger.error("Groq API key is not configured.")
            raise LLMUnavailableError("Hosted LLM API key is not configured.")

        endpoint = f"{self._groq_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._groq_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, object] = {
            "model": self._groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        logger.debug(
            "Sending generate request to Groq: model=%s prompt_len=%d system_len=%d",
            self._groq_model,
            len(user_prompt),
            len(system_prompt),
        )

        try:
            async with httpx.AsyncClient(timeout=self._groq_timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
        except httpx.ConnectError as exc:
            logger.error("Groq connection failed: %s", exc)
            raise LLMUnavailableError("Cannot connect to the LLM provider.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Groq request timed out after %ds.", self._groq_timeout)
            raise LLMUnavailableError("LLM provider request timed out.") from exc
        except httpx.RequestError as exc:
            logger.error("Groq HTTP request error: %s", exc)
            raise LLMUnavailableError("LLM provider request error.") from exc

        if response.status_code == 429:
            logger.warning("Groq rate limit exceeded (HTTP 429): %s", response.text[:200])
            raise LLMUnavailableError("LLM provider rate limit exceeded. Please try again shortly.")

        if response.status_code >= 400:
            logger.error(
                "Groq returned HTTP %d: %s",
                response.status_code,
                response.text[:200],
            )
            raise LLMUnavailableError(
                f"LLM provider returned unexpected status {response.status_code}."
            )

        try:
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("No choices in Groq response.")
            generated_text: str | None = choices[0].get("message", {}).get("content")
        except Exception as exc:
            logger.error("Groq response parsing error: %s", exc)
            raise LLMUnavailableError("LLM provider returned a malformed response.") from exc

        if not generated_text or not generated_text.strip():
            logger.warning("Groq returned an empty response.")
            raise LLMUnavailableError("LLM provider returned an empty response.")

        logger.debug(
            "Groq generation complete: model=%s response_len=%d",
            self._groq_model,
            len(generated_text),
        )
        return generated_text

    # ------------------------------------------------------------------
    # Local Ollama Provider
    # ------------------------------------------------------------------

    async def _generate_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        endpoint = f"{self._ollama_base_url}/api/generate"
        payload: dict[str, object] = {
            "model": self._ollama_model,
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
            self._ollama_model,
            len(user_prompt),
            len(system_prompt),
        )

        try:
            async with httpx.AsyncClient(timeout=self._ollama_timeout) as client:
                response = await client.post(endpoint, json=payload)
        except httpx.ConnectError as exc:
            logger.error("Ollama connection failed: %s", exc)
            raise LLMUnavailableError("Cannot connect to the LLM provider.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Ollama request timed out after %ds.", self._ollama_timeout)
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
            self._ollama_model,
            len(generated_text),
        )
        return generated_text
