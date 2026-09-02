"""
Application configuration.

All settings are loaded from environment variables via pydantic-settings.
Never call os.getenv() directly in the codebase — import `settings` from here.

Usage:
    from app.core.config import settings

    db_url = settings.DATABASE_URL
"""

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object for IntelliFlow AI.

    Fields map directly to environment variables (case-insensitive).
    Validation is enforced by Pydantic at startup — misconfigured environments
    fail fast rather than causing cryptic runtime errors.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars instead of raising
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    APP_NAME: str = "IntelliFlow AI"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_VERSION: str = "1.0.0"

    # -------------------------------------------------------------------------
    # Backend server
    # -------------------------------------------------------------------------
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # CORS — comma-separated string parsed into a list
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list of strings."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://intelliflow_user:change_this_strong_password@postgres:5432/intelliflow"
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://intelliflow_user:change_this_strong_password@postgres:5432/intelliflow"

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    REDIS_URL: str = "redis://redis:6379/0"

    # -------------------------------------------------------------------------
    # Celery
    # -------------------------------------------------------------------------
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    # -------------------------------------------------------------------------
    # JWT Authentication (Milestone 2)
    # -------------------------------------------------------------------------
    # SECURITY: Change this in production. Generate with: openssl rand -hex 32
    JWT_SECRET_KEY: str = "CHANGE_ME_insecure_dev_key_min_32_characters_replace_now"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -------------------------------------------------------------------------
    # Cookie Security (Milestone 2) — for future HttpOnly cookie strategy
    # -------------------------------------------------------------------------
    COOKIE_SECURE: bool = False  # Set True in production (HTTPS required)
    COOKIE_SAMESITE: str = "lax"  # Use "strict" in production

    # -------------------------------------------------------------------------
    # Storage & Uploads (Milestone 5, 6.1 & 11)
    # -------------------------------------------------------------------------
    STORAGE_DIR: str = "/app/storage/documents"
    MAX_UPLOAD_SIZE_MB: int = 25
    MAX_UPLOAD_SIZE_BYTES: int = (
        25 * 1024 * 1024
    )  # 25 MB default, overridden if MAX_UPLOAD_SIZE_MB is provided
    DOCUMENT_BULK_MAX_ITEMS: int = 100
    DOCUMENT_EXPIRATION_BATCH_SIZE: int = 500

    # -------------------------------------------------------------------------
    # AI Assistant — Ollama LLM (Milestone 7)
    # -------------------------------------------------------------------------
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.2:1b"
    OLLAMA_TIMEOUT_SECONDS: int = 180

    # -------------------------------------------------------------------------
    # AI Assistant — Embeddings (Milestone 7)
    # -------------------------------------------------------------------------
    # sentence-transformers model used for text embedding.
    # all-MiniLM-L6-v2 produces 384-dimensional L2-normalized vectors.
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # -------------------------------------------------------------------------
    # AI Assistant — FAISS Vector Store (Milestone 7)
    # -------------------------------------------------------------------------
    # Absolute path to the persisted FAISS index file inside the container.
    # The directory must be mounted as a Docker volume to survive restarts.
    FAISS_INDEX_PATH: str = "/app/data/faiss/index.faiss"

    # -------------------------------------------------------------------------
    # AI Assistant — RAG Retrieval Tuning (Milestone 7)
    # -------------------------------------------------------------------------
    # Number of nearest-neighbour chunks returned per query.
    RAG_TOP_K: int = 5
    # Maximum total characters from retrieved chunks injected into the prompt.
    RAG_MAX_CONTEXT_CHARS: int = 4000

    # -------------------------------------------------------------------------
    # AI Assistant — RAG Generation (Milestone 7 Phase 3)
    # -------------------------------------------------------------------------
    # Maximum number of authorized chunks passed to the context builder.
    AI_MAX_CONTEXT_CHUNKS: int = 3
    # Maximum total characters allowed in the assembled context string.
    AI_MAX_CONTEXT_CHARACTERS: int = 2500
    # Maximum tokens the LLM may generate in its response (optimized for CPU speed).
    AI_MAX_RESPONSE_TOKENS: int = 200
    # Sampling temperature for LLM generation (lower = more deterministic).
    AI_TEMPERATURE: float = 0.2
    # Minimum retrieval similarity (1/(1+L2), range (0,1]) a chunk must reach to
    # be used as context. Applied when a request does not specify its own
    # min_score. None = disabled (no threshold) — preserves legacy behaviour.
    # Set conservatively: too high reintroduces the "no answer" fallback for
    # genuinely-relevant but low-scoring chunks (observed relevant matches
    # scored ~0.38–0.54 with all-MiniLM-L6-v2 + the 1/(1+L2) transform).
    AI_MIN_RETRIEVAL_SCORE: float | None = None

    # -------------------------------------------------------------------------
    # AI Assistant — Hybrid Retrieval (Milestone 7 Phase 3)
    # -------------------------------------------------------------------------
    # Master switch for hybrid (semantic + lexical → RRF fusion) retrieval.
    # When False the pipeline falls back to semantic-only retrieval, which is
    # exactly the pre-Phase-3 behaviour. Kept as a kill-switch so the richer
    # path can be disabled instantly in production without a code change.
    AI_HYBRID_ENABLED: bool = True
    # Reciprocal Rank Fusion constant k in RRF_score(d) = Σ 1/(k + rank).
    # The canonical value from the RRF paper (Cormack et al., 2009). Larger k
    # flattens the contribution of top ranks; 60 is the widely-used default.
    AI_RRF_K: int = 60
    # Semantic candidate over-sampling: fetch top_k * this many FAISS neighbours
    # before authorization filtering, so RBAC removals do not starve the final
    # result set. Mirrors the historical _FAISS_OVERSAMPLE_FACTOR.
    AI_SEMANTIC_CANDIDATE_MULTIPLIER: int = 3
    # Hard ceiling on semantic candidates pulled from FAISS per query, applied
    # after the multiplier. Bounds work and memory regardless of top_k.
    AI_MAX_RETRIEVAL_CANDIDATES: int = 60
    # Hard ceiling on lexical candidates pulled from PostgreSQL per query.
    # Bounds the lexical branch independently of the semantic one.
    AI_LEXICAL_CANDIDATES: int = 30

    # -------------------------------------------------------------------------
    # AI Assistant — Document-aware Query Handling (Milestone 7 Phase 4)
    # -------------------------------------------------------------------------
    # Detect filename/title/"about document X" style queries and boost chunks
    # from the matched document(s). Generic — never keyed to specific files.
    AI_DOC_AWARE_ENABLED: bool = True
    # When a document-aware query matches a document, how many of that
    # document's chunks to pull as additional candidates (bounded per doc).
    AI_DOC_AWARE_CHUNKS_PER_DOC: int = 3

    # -------------------------------------------------------------------------
    # AI Assistant — Reranking (Milestone 7 Phase 5)
    # -------------------------------------------------------------------------
    # Cross-encoder reranking of fused candidates. DEFAULT OFF: the ~3.75 GiB
    # RAM budget is already committed to the embedding model + Ollama, so the
    # reranker model is only loaded (lazily, in the API process) when this flag
    # is explicitly enabled. The system is fully functional with it off — RRF
    # remains the final ranker in that case.
    AI_RERANK_ENABLED: bool = False
    # How many top fused candidates to hand to the reranker when enabled.
    AI_RERANK_TOP_N: int = 20
    # Cross-encoder model used only when AI_RERANK_ENABLED is True. Small by
    # design; sentence-transformers ships CrossEncoder so no new dependency.
    AI_RERANK_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # -------------------------------------------------------------------------
    # AI Assistant — Timing / Observability (Milestone 7 Phase 10)
    # -------------------------------------------------------------------------
    # Emit structured AI_TIMING logs (embedding/semantic/lexical/fusion/context/
    # llm/total durations). Metadata only — never logs queries, answers, or
    # document contents.
    AI_TIMING_ENABLED: bool = True

    # -------------------------------------------------------------------------
    # Workflow Engine (Milestone 8)
    # -------------------------------------------------------------------------
    # SMTP settings for the `send_email` workflow step.
    # When SMTP_HOST is empty the step records a controlled failure rather
    # than crashing the Celery worker.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@intelliflow.ai"
    SMTP_USE_TLS: bool = True

    # Maximum number of steps a single workflow may contain.
    WORKFLOW_MAX_STEPS: int = 20
    # Maximum delay in seconds for a `delay` step (5 minutes by default).
    WORKFLOW_MAX_DELAY_SECONDS: int = 300
    # How long (seconds) an approve step waits before timing out.
    WORKFLOW_APPROVE_TIMEOUT_SECONDS: int = 86400  # 24 hours

    # -------------------------------------------------------------------------
    # AI Assistant — Conversation History (Milestone 7 Phase 11)
    # -------------------------------------------------------------------------
    # Maximum number of prior Q&A exchanges to fold into a follow-up query's
    # context. Bounded so history cannot grow the prompt without limit.
    AI_MAX_HISTORY_EXCHANGES: int = 3
    # Maximum total characters of conversation history injected into a prompt.
    # A hard cap independent of the exchange count.
    AI_MAX_HISTORY_CHARS: int = 1500

    # -------------------------------------------------------------------------
    # Rate Limiting & API Security (Milestone 12)
    # -------------------------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_LOGIN: int = 5  # 5 requests / min per IP
    RATE_LIMIT_AUTH_REFRESH: int = 30  # 30 requests / min per IP
    RATE_LIMIT_AI_CHAT: int = 20  # 20 requests / min per user/IP
    RATE_LIMIT_DOCUMENT_UPLOAD: int = 30  # 30 requests / min per user/IP
    RATE_LIMIT_REPORTS: int = 20  # 20 requests / min per user/IP
    RATE_LIMIT_WORKFLOWS: int = 20  # 20 requests / min per user/IP
    RATE_LIMIT_DEFAULT: int = 120  # 120 requests / min default
    SECURITY_HEADERS_ENABLED: bool = True
    HSTS_MAX_AGE_SECONDS: int = 31536000

    # -------------------------------------------------------------------------
    # Enterprise Integrations, Event Bus & Webhooks (Milestone 13)
    # -------------------------------------------------------------------------
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_MAX_RETRIES: int = 5
    WEBHOOK_RETRY_BACKOFF_FACTOR: float = 2.0
    WEBHOOK_MAX_DELIVERY_HISTORY_DAYS: int = 30
    OUTBOX_POLL_INTERVAL_SECONDS: int = 5
    OUTBOX_BATCH_SIZE: int = 50

    # Fernet key for encrypting integration credentials in the database.
    # In production this MUST be set to a unique value (openssl rand -base64 32).
    # In development it falls back to JWT_SECRET_KEY — NOT acceptable in production.
    INTEGRATION_ENCRYPTION_KEY: str = ""

    # Webhook HMAC signing secret — used to generate X-IntelliFlow-Signature headers.
    # In production this MUST be set to a unique value separate from other secrets.
    WEBHOOK_SIGNING_SECRET: str = ""

    # -------------------------------------------------------------------------
    # Field validators
    # -------------------------------------------------------------------------
    @field_validator(
        "AI_RRF_K",
        "AI_SEMANTIC_CANDIDATE_MULTIPLIER",
        "AI_MAX_RETRIEVAL_CANDIDATES",
        "AI_LEXICAL_CANDIDATES",
        "AI_DOC_AWARE_CHUNKS_PER_DOC",
        "AI_RERANK_TOP_N",
        "AI_MAX_HISTORY_EXCHANGES",
        "AI_MAX_CONTEXT_CHUNKS",
        "AI_MAX_CONTEXT_CHARACTERS",
        "AI_MAX_RESPONSE_TOKENS",
        "AI_MAX_HISTORY_CHARS",
    )
    @classmethod
    def validate_positive_int(cls, value: int, info: object) -> int:
        """Reject non-positive retrieval/context bounds — fail fast on misconfig."""
        field_name = getattr(info, "field_name", "value")
        if value < 1:
            raise ValueError(f"{field_name} must be >= 1, got {value}")
        return value

    @field_validator("AI_MIN_RETRIEVAL_SCORE")
    @classmethod
    def validate_min_retrieval_score(cls, value: float | None) -> float | None:
        """Similarity threshold, when set, must lie in the (0, 1] range."""
        if value is not None and not (0.0 < value <= 1.0):
            raise ValueError(f"AI_MIN_RETRIEVAL_SCORE must be in (0, 1], got {value}")
        return value

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Ensure LOG_LEVEL is a valid Python logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalised = value.upper()
        if normalised not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}, got '{value}'")
        return normalised

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        """Ensure APP_ENV is one of the expected deployment environments."""
        valid_envs = {"development", "staging", "production"}
        normalised = value.lower()
        if normalised not in valid_envs:
            raise ValueError(f"APP_ENV must be one of {valid_envs}, got '{value}'")
        return normalised

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_length(cls, value: str) -> str:
        """Ensure the JWT secret is long enough to be cryptographically safe."""
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Reject insecure defaults in production environments."""
        if self.APP_ENV == "production":
            insecure_key = "CHANGE_ME_insecure_dev_key_min_32_characters_replace_now"
            if self.JWT_SECRET_KEY == insecure_key:
                raise ValueError(
                    "JWT_SECRET_KEY must be changed from the default value in production. "
                    "Generate a secure key with: openssl rand -hex 32"
                )

            # Require dedicated encryption key — never fall back to JWT secret in production
            if not self.INTEGRATION_ENCRYPTION_KEY.strip():
                raise ValueError(
                    "INTEGRATION_ENCRYPTION_KEY must be set in production. "
                    "Generate with: openssl rand -base64 32"
                )

            # Require dedicated webhook signing secret
            if not self.WEBHOOK_SIGNING_SECRET.strip():
                raise ValueError(
                    "WEBHOOK_SIGNING_SECRET must be set in production. "
                    "Generate with: openssl rand -hex 32"
                )

            # Cookies must be secure in production (requires HTTPS)
            if not self.COOKIE_SECURE:
                raise ValueError(
                    "COOKIE_SECURE must be true in production. HTTPS is required."
                )

            # CORS must not allow localhost in production
            origins = self.cors_origins_list
            suspicious = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
            if suspicious:
                raise ValueError(
                    f"CORS_ORIGINS contains localhost/127.0.0.1 in production: {suspicious}. "
                    "Set CORS_ORIGINS to your production domain(s) only."
                )

        return self

    # -------------------------------------------------------------------------
    # Derived helpers
    # -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        """Return True when running in the production environment."""
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        """Return True when running in the development environment."""
        return self.APP_ENV == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.

    lru_cache ensures the .env file is read only once per process,
    making this safe and efficient to call from anywhere.
    """
    return Settings()


# Module-level singleton — import this throughout the application
settings: Settings = get_settings()


def validate_runtime_configuration(cfg: Settings | None = None) -> list[str]:
    """
    Validate system settings at startup and return non-fatal configuration warnings.

    In production mode, raises ValueError for any critical security violations.
    """
    target = cfg or settings
    warnings: list[str] = []

    # 1. JWT Secret check
    insecure_default = "CHANGE_ME_insecure_dev_key_min_32_characters_replace_now"
    if target.JWT_SECRET_KEY == insecure_default:
        msg = "JWT_SECRET_KEY is using the insecure development default."
        if target.is_production:
            raise ValueError(f"FATAL SECURITY CONFIGURATION: {msg}")
        warnings.append(msg)

    # 2. Database URL validation
    if not target.DATABASE_URL:
        raise ValueError("DATABASE_URL must not be empty.")

    # 3. CORS Origins check
    if "*" in target.cors_origins_list:
        msg = "CORS_ORIGINS contains wildcard '*' while allow_credentials is enabled."
        if target.is_production:
            raise ValueError(f"FATAL SECURITY CONFIGURATION: {msg}")
        warnings.append(msg)

    # 4. Storage Directory validation
    if not target.STORAGE_DIR:
        warnings.append("STORAGE_DIR is not configured.")

    # 5. Token expiry bounds
    if target.ACCESS_TOKEN_EXPIRE_MINUTES > 1440:  # > 24 hours
        warnings.append("ACCESS_TOKEN_EXPIRE_MINUTES is unusually high (> 24 hours).")

    # 6. Integration encryption key — warn if not set (fatal in production via model_validator)
    if not target.INTEGRATION_ENCRYPTION_KEY.strip():
        msg = "INTEGRATION_ENCRYPTION_KEY is not set — falling back to JWT_SECRET_KEY for Fernet encryption."
        warnings.append(msg)

    # 7. Webhook signing secret — warn if not set
    if not target.WEBHOOK_SIGNING_SECRET.strip():
        msg = "WEBHOOK_SIGNING_SECRET is not set — webhooks will use a derived key."
        warnings.append(msg)

    return warnings
