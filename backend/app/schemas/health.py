"""
Health check response schema.

Defined as a Pydantic model so FastAPI can:
  - Validate the response shape
  - Generate accurate OpenAPI documentation
  - Provide IDE autocompletion

Per API_SPECIFICATION §12, the health endpoint returns:
    {"status": "ok"}
"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for the GET /health endpoint."""

    status: str

    model_config = {
        "json_schema_extra": {
            "examples": [{"status": "ok"}],
        }
    }
