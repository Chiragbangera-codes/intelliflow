"""
Tests for Enterprise Integration Framework: credential encryption, provider abstractions, and REST APIs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response

from app.core.encryption import decrypt_json, encrypt_data


class TestIntegrations:
    """Test Integration Framework and credential security."""

    def test_credential_encryption_roundtrip(self) -> None:
        """Verify AES/Fernet encryption encrypts dict to ciphertext string and decrypts losslessly."""
        raw_creds = {"api_key": "xoxb-secret-slack-token-12345", "client_secret": "my-secret"}
        encrypted = encrypt_data(raw_creds)
        assert isinstance(encrypted, str)
        assert "xoxb-secret" not in encrypted

        decrypted = decrypt_json(encrypted)
        assert decrypted == raw_creds

    @pytest.mark.asyncio
    async def test_create_integration_with_encrypted_credentials(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """Verify POST /api/v1/integrations stores encrypted creds and hides them on GET."""
        payload = {
            "name": "DevOps Slack Channel",
            "provider": "slack",
            "description": "Slack webhook integration for DevOps alerts",
            "configuration": {"webhook_url": "https://hooks.slack.com/services/T00/B00/X00"},
            "credentials": {"signing_secret": "my-slack-secret-value"},
        }

        res = await async_client.post(
            "/api/v1/integrations",
            json=payload,
            headers=admin_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "DevOps Slack Channel"
        assert data["provider"] == "slack"
        assert data["has_credentials"] is True
        assert "credentials" not in data
        assert "signing_secret" not in str(data)

        integration_id = data["id"]

        # GET single integration
        get_res = await async_client.get(
            f"/api/v1/integrations/{integration_id}",
            headers=admin_headers,
        )
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["has_credentials"] is True
        assert "credentials" not in get_data

    @pytest.mark.asyncio
    async def test_integration_test_connection_mocked(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """Verify POST /api/v1/integrations/{id}/test tests outbound connection."""
        create_res = await async_client.post(
            "/api/v1/integrations",
            json={
                "name": "Test Webhook Provider",
                "provider": "webhook",
                "configuration": {"url": "https://httpbin.org/post"},
            },
            headers=admin_headers,
        )
        assert create_res.status_code == 201
        integration_id = create_res.json()["id"]

        mock_resp = Response(status_code=200, json={"ok": True}, request=AsyncMock())
        with patch("app.utils.ssrf.safe_http_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            test_res = await async_client.post(
                f"/api/v1/integrations/{integration_id}/test",
                headers=admin_headers,
            )
            assert test_res.status_code == 200
            result = test_res.json()
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_update_and_delete_integration(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """Verify PATCH and DELETE lifecycle for integrations."""
        create_res = await async_client.post(
            "/api/v1/integrations",
            json={
                "name": "Old Name",
                "provider": "generic_http",
                "configuration": {"url": "https://httpbin.org/post"},
            },
            headers=admin_headers,
        )
        integration_id = create_res.json()["id"]

        # Update
        update_res = await async_client.patch(
            f"/api/v1/integrations/{integration_id}",
            json={"name": "New Updated Name", "status": "inactive"},
            headers=admin_headers,
        )
        assert update_res.status_code == 200
        assert update_res.json()["name"] == "New Updated Name"
        assert update_res.json()["status"] == "inactive"

        # Delete
        delete_res = await async_client.delete(
            f"/api/v1/integrations/{integration_id}",
            headers=admin_headers,
        )
        assert delete_res.status_code == 204

        # Verify not found
        get_res = await async_client.get(
            f"/api/v1/integrations/{integration_id}",
            headers=admin_headers,
        )
        assert get_res.status_code == 404
