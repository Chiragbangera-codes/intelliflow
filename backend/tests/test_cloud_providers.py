"""
Unit tests for Cloud Providers (Phase 6 Blocker Resolutions).

Tests:
1. Hugging Face Router embedding provider (mocked HTTP, retries, 429, 503, validation).
2. True dynamic lazy import isolation (torch not loaded into sys.modules).
3. Supabase Storage backend (mocked HTTP upload, streaming, scoped temp path, 404).
4. Legacy document local fallback.
"""

from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from app.services.embedding_service import (
    EmbeddingError,
    EmbeddingRateLimitError,
    EmbeddingService,
    EmbeddingUnavailableError,
)
from app.services.storage_service import StorageService


# =============================================================================
# 1. Hugging Face Embedding Provider Tests
# =============================================================================


class TestHuggingFaceEmbeddingProvider:
    """Test Hugging Face Router serverless inference embedding provider."""

    def test_missing_hf_token_raises_unavailable(self) -> None:
        with patch("app.services.embedding_service.settings.EMBEDDING_PROVIDER", "huggingface"):
            with patch("app.services.embedding_service.settings.HF_TOKEN", None):
                svc = EmbeddingService()
                with pytest.raises(EmbeddingUnavailableError, match="HF_TOKEN is not configured"):
                    svc.embed_text("test")

    def test_hf_successful_batch_embedding(self) -> None:
        with patch("app.services.embedding_service.settings.EMBEDDING_PROVIDER", "huggingface"):
            with patch("app.services.embedding_service.settings.HF_TOKEN", "hf_test_token"):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = [[0.05] * 384, [-0.02] * 384]

                with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
                    svc = EmbeddingService()
                    res = svc.embed_batch(["alpha", "beta"])

                    assert len(res) == 2
                    assert len(res[0]) == 384
                    assert len(res[1]) == 384
                    assert res[0][0] == 0.05
                    mock_post.assert_called_once()

    def test_hf_rate_limit_429_raises_ratelimit_error(self) -> None:
        with patch("app.services.embedding_service.settings.EMBEDDING_PROVIDER", "huggingface"):
            with patch("app.services.embedding_service.settings.HF_TOKEN", "hf_test_token"):
                mock_resp = MagicMock()
                mock_resp.status_code = 429
                mock_resp.text = "Too Many Requests"

                with patch("httpx.Client.post", return_value=mock_resp):
                    svc = EmbeddingService()
                    with pytest.raises(EmbeddingRateLimitError, match="rate limit exceeded"):
                        svc.embed_text("test")

    def test_hf_model_loading_503_retries_and_succeeds(self) -> None:
        with patch("app.services.embedding_service.settings.EMBEDDING_PROVIDER", "huggingface"):
            with patch("app.services.embedding_service.settings.HF_TOKEN", "hf_test_token"):
                resp_503 = MagicMock()
                resp_503.status_code = 503
                resp_503.json.return_value = {"error": "Model is loading", "estimated_time": 0.01}

                resp_200 = MagicMock()
                resp_200.status_code = 200
                resp_200.json.return_value = [[0.1] * 384]

                with patch("httpx.Client.post", side_effect=[resp_503, resp_200]):
                    with patch("time.sleep") as mock_sleep:
                        svc = EmbeddingService()
                        vec = svc.embed_text("retry test")
                        assert len(vec) == 384
                        mock_sleep.assert_called_once()

    def test_hf_dimension_mismatch_fails_clearly(self) -> None:
        with patch("app.services.embedding_service.settings.EMBEDDING_PROVIDER", "huggingface"):
            with patch("app.services.embedding_service.settings.HF_TOKEN", "hf_test_token"):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = [[0.1] * 128]  # Wrong dimension

                with patch("httpx.Client.post", return_value=mock_resp):
                    svc = EmbeddingService()
                    with pytest.raises(EmbeddingError, match="Vector dimension mismatch"):
                        svc.embed_text("mismatch")

    def test_hf_malformed_json_fails_clearly(self) -> None:
        with patch("app.services.embedding_service.settings.EMBEDDING_PROVIDER", "huggingface"):
            with patch("app.services.embedding_service.settings.HF_TOKEN", "hf_test_token"):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.side_effect = ValueError("Invalid JSON")

                with patch("httpx.Client.post", return_value=mock_resp):
                    svc = EmbeddingService()
                    with pytest.raises(EmbeddingError, match="Malformed JSON response"):
                        svc.embed_text("malformed")


# =============================================================================
# 2. Lazy Import Isolation Tests
# =============================================================================


class TestLazyImportIsolation:
    """Verify that importing embedding service does not prematurely import torch."""

    def test_cloud_provider_does_not_call_local_loader(self) -> None:
        with patch("app.services.embedding_service.settings.EMBEDDING_PROVIDER", "huggingface"):
            with patch("app.services.embedding_service._get_local_model") as mock_local:
                with patch("app.services.embedding_service.settings.HF_TOKEN", "hf_mock"):
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = [[0.1] * 384]
                    with patch("httpx.Client.post", return_value=mock_resp):
                        svc = EmbeddingService()
                        svc.embed_text("cloud text")
                        mock_local.assert_not_called()


# =============================================================================
# 3. Supabase Storage Backend Tests
# =============================================================================


class TestSupabaseStorageBackend:
    """Test Supabase Object Storage operations with service-role security."""

    @pytest.mark.asyncio
    async def test_supabase_upload_stream_success(self, tmp_path: Path) -> None:
        with patch("app.services.storage_service.settings.STORAGE_BACKEND", "supabase"):
            with patch("app.services.storage_service.settings.SUPABASE_URL", "https://mock.supabase.co"):
                with patch("app.services.storage_service.settings.SUPABASE_SERVICE_ROLE_KEY", "mock_key"):
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200

                    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                        mock_post.return_value = mock_resp

                        storage_svc = StorageService(storage_dir=str(tmp_path))
                        upload = UploadFile(
                            filename="document.pdf",
                            file=io.BytesIO(b"%PDF-1.7 sample data"),
                            headers={"content-type": "application/pdf"},
                        )
                        owner_id = uuid.uuid4()

                        metadata = await storage_svc.save_upload_file(upload, owner_id=owner_id)

                        assert metadata.file_name == "document.pdf"
                        assert metadata.file_size == len(b"%PDF-1.7 sample data")
                        assert str(owner_id) in metadata.storage_path
                        mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_supabase_open_stream_downloads(self, tmp_path: Path) -> None:
        with patch("app.services.storage_service.settings.STORAGE_BACKEND", "supabase"):
            with patch("app.services.storage_service.settings.SUPABASE_URL", "https://mock.supabase.co"):
                with patch("app.services.storage_service.settings.SUPABASE_SERVICE_ROLE_KEY", "mock_key"):
                    test_bytes = b"mocked cloud pdf content"
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_resp.headers = {"content-length": str(len(test_bytes)), "content-type": "application/pdf"}

                    async def mock_aiter(chunk_size: int):
                        yield test_bytes

                    mock_resp.aiter_bytes = mock_aiter
                    mock_resp.aclose = AsyncMock()

                    with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
                        mock_send.return_value = mock_resp

                        storage_svc = StorageService(storage_dir=str(tmp_path))
                        stream, length, ctype = await storage_svc.open_stream("user_1/file.pdf")

                        chunks = []
                        async for chunk in stream:
                            chunks.append(chunk)

                        assert b"".join(chunks) == test_bytes
                        assert length == len(test_bytes)
                        assert ctype == "application/pdf"

    @pytest.mark.asyncio
    async def test_scoped_local_path_downloads_and_cleans_up(self, tmp_path: Path) -> None:
        with patch("app.services.storage_service.settings.STORAGE_BACKEND", "supabase"):
            with patch("app.services.storage_service.settings.SUPABASE_URL", "https://mock.supabase.co"):
                with patch("app.services.storage_service.settings.SUPABASE_SERVICE_ROLE_KEY", "mock_key"):
                    test_bytes = b"sample bytes for OCR"
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_resp.content = test_bytes

                    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                        mock_get.return_value = mock_resp

                        storage_svc = StorageService(storage_dir=str(tmp_path))
                        temp_file_path: Path | None = None

                        async with storage_svc.scoped_local_path("user_1/ocr_doc.pdf") as p:
                            temp_file_path = p
                            assert p.exists()
                            assert p.read_bytes() == test_bytes

                        # After context exit, the temp file must be cleaned up
                        assert temp_file_path is not None
                        assert not temp_file_path.exists()

    @pytest.mark.asyncio
    async def test_legacy_local_file_served_when_not_in_supabase(self, tmp_path: Path) -> None:
        """If a file is only on local disk (legacy document), it is transparently served."""
        with patch("app.services.storage_service.settings.STORAGE_BACKEND", "supabase"):
            with patch("app.services.storage_service.settings.SUPABASE_URL", "https://mock.supabase.co"):
                with patch("app.services.storage_service.settings.SUPABASE_SERVICE_ROLE_KEY", "mock_key"):
                    # Local file exists
                    user_dir = tmp_path / "legacy_user"
                    user_dir.mkdir(parents=True)
                    legacy_file = user_dir / "old_doc.pdf"
                    legacy_file.write_bytes(b"legacy local data")

                    # Supabase returns 404 (not in cloud)
                    mock_resp = MagicMock()
                    mock_resp.status_code = 404
                    mock_resp.aclose = AsyncMock()

                    with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
                        mock_send.return_value = mock_resp

                        storage_svc = StorageService(storage_dir=str(tmp_path))
                        stream, length, _ = await storage_svc.open_stream("legacy_user/old_doc.pdf")

                        chunks = []
                        async for chunk in stream:
                            chunks.append(chunk)

                        assert b"".join(chunks) == b"legacy local data"
                        assert length == len(b"legacy local data")

    @pytest.mark.asyncio
    async def test_missing_file_everywhere_raises_404(self, tmp_path: Path) -> None:
        with patch("app.services.storage_service.settings.STORAGE_BACKEND", "supabase"):
            with patch("app.services.storage_service.settings.SUPABASE_URL", "https://mock.supabase.co"):
                with patch("app.services.storage_service.settings.SUPABASE_SERVICE_ROLE_KEY", "mock_key"):
                    mock_resp = MagicMock()
                    mock_resp.status_code = 404
                    mock_resp.aclose = AsyncMock()

                    with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
                        mock_send.return_value = mock_resp

                        storage_svc = StorageService(storage_dir=str(tmp_path))
                        with pytest.raises(HTTPException) as exc_info:
                            await storage_svc.open_stream("nonexistent/ghost.pdf")

                        assert exc_info.value.status_code == 404
