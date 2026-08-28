"""
Tests for the GET /health endpoint.

Covers:
  - Happy path: 200 OK with correct response body
  - Response format matches API_SPECIFICATION §12
  - Content-Type is application/json
  - No authentication required (public endpoint)
"""

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Test suite for the health check endpoint."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Health endpoint must return HTTP 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_body(self, client: TestClient) -> None:
        """Health endpoint must return {"status": "ok"} per API specification."""
        response = client.get("/health")
        body = response.json()
        assert body == {"status": "ok"}

    def test_health_status_field_is_ok(self, client: TestClient) -> None:
        """The `status` field must equal the string "ok"."""
        response = client.get("/health")
        assert response.json()["status"] == "ok"

    def test_health_content_type_is_json(self, client: TestClient) -> None:
        """Response Content-Type must be application/json."""
        response = client.get("/health")
        assert "application/json" in response.headers["content-type"]

    def test_health_requires_no_authentication(self, client: TestClient) -> None:
        """Health endpoint must be accessible without any Authorization header."""
        # Explicitly send a request with no headers to confirm it's public
        response = client.get("/health", headers={})
        assert response.status_code == 200

    def test_health_does_not_accept_post(self, client: TestClient) -> None:
        """Health endpoint only supports GET — POST must return 405 Method Not Allowed."""
        response = client.post("/health")
        assert response.status_code == 405
