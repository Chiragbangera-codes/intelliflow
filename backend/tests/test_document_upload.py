"""
Comprehensive unit and integration tests for Milestone 6.1: Secure Document Upload & Storage Integration.

Coverage:
  1. PDF upload succeeds.
  2. DOCX upload succeeds.
  3. XLSX upload succeeds.
  4. PNG/JPG upload succeeds.
  5. Unsupported file type rejected (400).
  6. Empty file rejected (400).
  7. Oversized file rejected (413).
  8. Actual SHA-256 is calculated correctly on server.
  9. Actual file size is recorded.
  10. Owner is taken strictly from authenticated JWT user.
  11. Client cannot override owner_id.
  12. Storage path is generated server-side.
  13. Path traversal filename is safely normalized.
  14. Database document record is created.
  15. Audit log is generated (document.upload).
  16. Uploaded file exists physically on disk.
  17. OCR can subsequently process the uploaded file.
  18. Cross-user access remains forbidden (403).
"""

import hashlib
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.user import User
from app.services.storage_service import StorageService

# =============================================================================
# Helper Payload Generators
# =============================================================================


def _make_dummy_pdf(content: str = "Test PDF document for IntelliFlow AI upload.") -> bytes:
    return f"%PDF-1.4\n1 0 obj\n<< /Title (Test) >>\nendobj\n{content}\n%%EOF".encode()


def _make_dummy_docx() -> bytes:
    # Minimal zip-compatible payload or mock docx bytes
    return b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + (b"A" * 100)


def _make_dummy_xlsx() -> bytes:
    return b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + (b"B" * 100)


def _make_dummy_png() -> bytes:
    # Valid 1x1 transparent PNG binary header
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _make_dummy_jpg() -> bytes:
    # Valid minimal JPEG binary header
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        + (b"\x00" * 40)
        + b"\xff\xd9"
    )


# =============================================================================
# 1. Format-Specific Upload Tests
# =============================================================================


@pytest.mark.asyncio
async def test_upload_pdf_success(async_client: AsyncClient, auth_headers: dict) -> None:
    """PDF upload succeeds and registers metadata with pending OCR status."""
    pdf_bytes = _make_dummy_pdf("IntelliFlow PDF content")
    files = {"file": ("report_q3.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    res = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == 201
    body = res.json()
    assert body["success"] is True
    assert body["data"]["file_name"] == "report_q3.pdf"
    assert body["data"]["file_type"] == "application/pdf"
    assert body["data"]["file_size"] == len(pdf_bytes)
    assert body["data"]["checksum"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert body["data"]["ocr_status"] == "pending"
    assert body["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_upload_docx_success(async_client: AsyncClient, auth_headers: dict) -> None:
    """DOCX upload succeeds with correct MIME type."""
    docx_bytes = _make_dummy_docx()
    files = {
        "file": (
            "proposal.docx",
            io.BytesIO(docx_bytes),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    res = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == 201
    assert res.json()["data"]["file_name"] == "proposal.docx"


@pytest.mark.asyncio
async def test_upload_xlsx_success(async_client: AsyncClient, auth_headers: dict) -> None:
    """XLSX upload succeeds with correct MIME type."""
    xlsx_bytes = _make_dummy_xlsx()
    files = {
        "file": (
            "financials.xlsx",
            io.BytesIO(xlsx_bytes),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    res = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == 201
    assert res.json()["data"]["file_name"] == "financials.xlsx"


@pytest.mark.asyncio
async def test_upload_png_and_jpg_success(async_client: AsyncClient, auth_headers: dict) -> None:
    """PNG and JPG image uploads succeed."""
    png_bytes = _make_dummy_png()
    files_png = {"file": ("receipt.png", io.BytesIO(png_bytes), "image/png")}
    res_png = await async_client.post(
        "/api/v1/documents/upload", files=files_png, headers=auth_headers
    )
    assert res_png.status_code == 201
    assert res_png.json()["data"]["file_type"] == "image/png"

    jpg_bytes = _make_dummy_jpg()
    files_jpg = {"file": ("scan.jpg", io.BytesIO(jpg_bytes), "image/jpeg")}
    res_jpg = await async_client.post(
        "/api/v1/documents/upload", files=files_jpg, headers=auth_headers
    )
    assert res_jpg.status_code == 201
    assert res_jpg.json()["data"]["file_type"] == "image/jpeg"


# =============================================================================
# 2. Validation & Security Rejections
# =============================================================================


@pytest.mark.asyncio
async def test_unsupported_file_type_rejected(
    async_client: AsyncClient, auth_headers: dict
) -> None:
    """Unsupported extensions (.exe, .sh, .txt, .bin) are rejected with 400 Bad Request."""
    bad_file = {
        "file": ("malicious.exe", io.BytesIO(b"MZ\x90\x00executable"), "application/x-msdownload")
    }
    res = await async_client.post("/api/v1/documents/upload", files=bad_file, headers=auth_headers)
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


@pytest.mark.asyncio
async def test_empty_file_rejected(async_client: AsyncClient, auth_headers: dict) -> None:
    """Zero-byte empty files are rejected with 400 Bad Request."""
    empty_file = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    res = await async_client.post(
        "/api/v1/documents/upload", files=empty_file, headers=auth_headers
    )
    assert res.status_code == 400
    assert "empty file" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oversized_file_rejected(async_client: AsyncClient, auth_headers: dict) -> None:
    """Files exceeding maximum allowed size are aborted with 413 Payload Too Large."""
    # Temporarily patch max size to 1 KB for testing
    with patch("app.services.storage_service.settings.MAX_UPLOAD_SIZE_BYTES", 1024):
        large_bytes = b"%PDF-1.4" + (b"X" * 2048)
        large_file = {"file": ("oversized.pdf", io.BytesIO(large_bytes), "application/pdf")}
        res = await async_client.post(
            "/api/v1/documents/upload", files=large_file, headers=auth_headers
        )
        assert res.status_code == 413
        assert "exceeds the maximum allowed size" in res.json()["detail"].lower()


# =============================================================================
# 3. Server-Side Integrity, RBAC & Storage Guarantees
# =============================================================================


@pytest.mark.asyncio
async def test_sha256_and_filesize_server_calculated(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """SHA-256 checksum and file_size are computed by backend from actual stream."""
    test_content = b"%PDF-1.4 cryptographic verification payload"
    expected_sha256 = hashlib.sha256(test_content).hexdigest()
    expected_size = len(test_content)

    files = {"file": ("crypto_check.pdf", io.BytesIO(test_content), "application/pdf")}
    res = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert res.status_code == 201

    data = res.json()["data"]
    assert data["checksum"] == expected_sha256
    assert data["file_size"] == expected_size


@pytest.mark.asyncio
async def test_owner_derived_from_jwt_cannot_be_forged(
    async_client: AsyncClient,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Owner is strictly set to authenticated JWT user and ignores client forging attempts."""
    forged_owner_id = uuid.uuid4()
    pdf_bytes = _make_dummy_pdf()

    files = {"file": ("owner_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    # Even if client sends owner_id in form fields, backend ignores it
    res = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        data={"owner_id": str(forged_owner_id)},
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["data"]["owner_id"] == str(test_user.id)
    assert res.json()["data"]["owner_id"] != str(forged_owner_id)


@pytest.mark.asyncio
async def test_path_traversal_filename_sanitized(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Path traversal filename (../../etc/passwd.pdf) is safely stripped to basename."""
    pdf_bytes = _make_dummy_pdf()
    files = {"file": ("../../etc/passwd.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    res = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert res.status_code == 201

    sanitized = res.json()["data"]["file_name"]
    assert ".." not in sanitized
    assert "/" not in sanitized
    assert "\\" not in sanitized
    assert sanitized == "passwd.pdf"


@pytest.mark.asyncio
async def test_uploaded_file_persisted_to_disk_and_database(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Document record in database corresponds to an actual file on physical disk."""
    pdf_bytes = _make_dummy_pdf("Persistent disk test")
    files = {"file": ("disk_check.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    res = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert res.status_code == 201

    doc_id = uuid.UUID(res.json()["data"]["id"])
    doc = await db_session.get(Document, doc_id)
    assert doc is not None

    storage_svc = StorageService()
    physical_path = storage_svc.resolve_path(doc.storage_path)
    assert physical_path.exists()
    assert physical_path.is_file()
    assert physical_path.read_bytes() == pdf_bytes


@pytest.mark.asyncio
async def test_upload_creates_audit_log(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Upload triggers 'document.upload' audit log entry."""
    pdf_bytes = _make_dummy_pdf("Audit test")
    files = {"file": ("audit_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    res = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert res.status_code == 201
    doc_id = uuid.UUID(res.json()["data"]["id"])

    audit_res = await db_session.execute(select(AuditLog).where(AuditLog.record_id == doc_id))
    logs = list(audit_res.scalars().all())
    assert len(logs) >= 1
    assert any(log.action == "document.upload" for log in logs)


@pytest.mark.asyncio
async def test_cross_user_access_forbidden(
    async_client: AsyncClient,
    auth_headers: dict,
    admin_headers: dict,
) -> None:
    """Non-admin cannot download or inspect another user's uploaded document."""
    # User 1 uploads document
    files = {"file": ("user1_private.pdf", io.BytesIO(_make_dummy_pdf()), "application/pdf")}
    res1 = await async_client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    doc_id = res1.json()["data"]["id"]

    # Register User 2
    user2_email = f"user2_{uuid.uuid4().hex[:6]}@example.com"
    reg2_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "User",
            "last_name": "Two",
            "email": user2_email,
            "password": "StrongPassword123!",
        },
    )
    assert reg2_res.status_code == 201

    login2_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user2_email, "password": "StrongPassword123!"},
    )
    assert login2_res.status_code == 200
    token2 = login2_res.json()["data"]["access_token"]
    user2_headers = {"Authorization": f"Bearer {token2}"}

    # User 2 tries to download User 1's document -> 403 Forbidden
    download_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/download", headers=user2_headers
    )
    assert download_res.status_code == 403

    # User 2 tries to get text of User 1's document -> 403 Forbidden
    text_res = await async_client.get(f"/api/v1/documents/{doc_id}/text", headers=user2_headers)
    assert text_res.status_code == 403

    # Admin can download User 1's document -> 200 OK
    admin_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/download", headers=admin_headers
    )
    assert admin_res.status_code == 200


@pytest.mark.asyncio
async def test_ocr_can_process_uploaded_file(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Uploaded document can be immediately queued for OCR via POST /documents/{id}/ocr."""
    pdf_bytes = _make_dummy_pdf("Ready for OCR extraction")
    files = {"file": ("ocr_target.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["data"]["id"]

    with patch("app.services.ocr_service.process_document_ocr.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "celery-job-upload-ocr"
        mock_delay.return_value = mock_task

        ocr_res = await async_client.post(f"/api/v1/documents/{doc_id}/ocr", headers=auth_headers)
        assert ocr_res.status_code == 202
        assert ocr_res.json()["data"]["job_id"] == "celery-job-upload-ocr"
        assert ocr_res.json()["data"]["status"] == "PROCESSING"
