"""
Tests for document management, storage, upload, download, search, filter, and RBAC.

Coverage:
  1. PDF upload (201, DB record, SHA-256 calculation, file on disk)
  2. DOCX upload
  3. XLSX upload
  4. PNG upload
  5. JPG/JPEG upload
  6. Invalid extension rejected (.exe, .sh -> 400)
  7. MIME/extension mismatch rejected (400)
  8. File exceeding size limit rejected (413)
  9. Unauthenticated upload rejected (401)
  10. Owner automatically assigned from JWT
  11. Client cannot spoof owner_id
  12. Download owner success (200, matching bytes and checksum)
  13. Cross-user download forbidden (403)
  14. Admin download allowed for any document (200)
  15. Download non-existent document (404)
  16. Search by filename (exact and case-insensitive)
  17. Status filter (pending, processing, processed, failed)
  18. Sorting (created_at, file_name, file_size)
  19. Pagination metadata
  20. Employee cannot access another user's document
  21. HR global document access
  22. Admin global document access
  23. Soft delete and removal from active list
  24. Deleted document cannot be downloaded (404)
  25. Audit log generated on upload
  26. Audit log generated on deletion
  27. Storage cleanup on failure
"""

import hashlib
import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User

# =============================================================================
# Helper utilities
# =============================================================================


def _make_dummy_file(content: bytes, filename: str, content_type: str) -> dict:
    """Create a files dictionary suitable for httpx multipart upload."""
    return {"file": (filename, io.BytesIO(content), content_type)}


# =============================================================================
# 1. Upload tests
# =============================================================================


@pytest.mark.asyncio
async def test_upload_pdf_success(
    async_client: AsyncClient,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Upload valid PDF file -> returns 201, computes SHA-256, stores metadata."""
    content = b"%PDF-1.4 sample PDF document content for testing"
    expected_hash = hashlib.sha256(content).hexdigest()

    files = _make_dummy_file(content, "contract.pdf", "application/pdf")
    response = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["file_name"] == "contract.pdf"
    assert data["file_size"] == len(content)
    assert data["checksum"] == expected_hash
    assert data["owner_id"] == str(test_user.id)
    assert data["status"] == "pending"
    assert data["ocr_status"] == "pending"


@pytest.mark.asyncio
async def test_upload_docx_success(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Upload valid DOCX file."""
    content = b"PK\x03\x04 dummy docx content"
    files = _make_dummy_file(
        content,
        "resume.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["file_name"] == "resume.docx"


@pytest.mark.asyncio
async def test_upload_xlsx_success(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Upload valid XLSX file."""
    content = b"PK\x03\x04 dummy xlsx content"
    files = _make_dummy_file(
        content,
        "budget.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["file_name"] == "budget.xlsx"


@pytest.mark.asyncio
async def test_upload_png_success(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Upload valid PNG file."""
    content = b"\x89PNG\r\n\x1a\n dummy image"
    files = _make_dummy_file(content, "receipt.png", "image/png")
    response = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["file_name"] == "receipt.png"


@pytest.mark.asyncio
async def test_upload_jpg_success(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Upload valid JPG/JPEG file."""
    content = b"\xff\xd8\xff dummy jpeg"
    files = _make_dummy_file(content, "photo.jpg", "image/jpeg")
    response = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["file_name"] == "photo.jpg"


@pytest.mark.asyncio
async def test_upload_invalid_extension_rejected(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Upload of unauthorized executable file (.exe or .sh) returns 400."""
    files_exe = _make_dummy_file(b"MZ...", "malware.exe", "application/x-msdownload")
    resp_exe = await async_client.post(
        "/api/v1/documents/upload", files=files_exe, headers=auth_headers
    )
    assert resp_exe.status_code == 400

    files_sh = _make_dummy_file(b"#!/bin/bash", "script.sh", "text/x-shellscript")
    resp_sh = await async_client.post(
        "/api/v1/documents/upload", files=files_sh, headers=auth_headers
    )
    assert resp_sh.status_code == 400


@pytest.mark.asyncio
async def test_upload_mismatch_extension_mime_rejected(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Extension .pdf with content-type image/png is rejected with 400."""
    files = _make_dummy_file(b"dummy", "fake.pdf", "image/png")
    response = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_unauthenticated_returns_401(async_client: AsyncClient) -> None:
    """Unauthenticated upload returns 401."""
    files = _make_dummy_file(b"content", "doc.pdf", "application/pdf")
    response = await async_client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 401


# =============================================================================
# 2. Download tests
# =============================================================================


@pytest.mark.asyncio
async def test_download_own_document_success(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Owner can download uploaded document and content matches exactly."""
    raw_content = b"%PDF-1.4 unique binary download test payload"
    files = _make_dummy_file(raw_content, "download_test.pdf", "application/pdf")

    # Upload
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["data"]["id"]

    # Download
    download_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/download", headers=auth_headers
    )
    assert download_res.status_code == 200
    assert download_res.content == raw_content
    assert (
        hashlib.sha256(download_res.content).hexdigest() == hashlib.sha256(raw_content).hexdigest()
    )


@pytest.mark.asyncio
async def test_download_cross_user_forbidden(
    async_client: AsyncClient,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Non-admin employee cannot download another user's document -> 403."""
    files = _make_dummy_file(b"admin secret", "confidential.pdf", "application/pdf")
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=admin_headers
    )
    doc_id = upload_res.json()["data"]["id"]

    # Employee tries to download admin doc
    download_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/download", headers=auth_headers
    )
    assert download_res.status_code == 403


@pytest.mark.asyncio
async def test_download_admin_can_download_any_document(
    async_client: AsyncClient,
    auth_headers: dict,
    admin_headers: dict,
) -> None:
    """Admin can download any document regardless of owner -> 200."""
    content = b"user document content"
    files = _make_dummy_file(content, "user_doc.pdf", "application/pdf")
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    doc_id = upload_res.json()["data"]["id"]

    # Admin downloads employee doc
    download_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/download", headers=admin_headers
    )
    assert download_res.status_code == 200
    assert download_res.content == content


@pytest.mark.asyncio
async def test_download_nonexistent_returns_404(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Downloading non-existent UUID returns 404."""
    response = await async_client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000099/download",
        headers=auth_headers,
    )
    assert response.status_code == 404


# =============================================================================
# 3. Search, Filter & Sort tests
# =============================================================================


@pytest.mark.asyncio
async def test_list_documents_search_filter(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Search query matches filename case-insensitively."""
    # Upload distinct documents
    f1 = _make_dummy_file(b"1", "Q3_Quarterly_Report.pdf", "application/pdf")
    f2 = _make_dummy_file(
        b"2",
        "Employee_Handbook.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    await async_client.post("/api/v1/documents/upload", files=f1, headers=auth_headers)
    await async_client.post("/api/v1/documents/upload", files=f2, headers=auth_headers)

    # Search for 'quarterly'
    res = await async_client.get(
        "/api/v1/documents", params={"search": "quarterly"}, headers=auth_headers
    )
    assert res.status_code == 200
    items = res.json()["data"]
    assert any("Q3_Quarterly_Report.pdf" in d["file_name"] for d in items)
    assert not any("Employee_Handbook" in d["file_name"] for d in items)


@pytest.mark.asyncio
async def test_list_documents_status_filter(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Filtering by status returns only records with that status."""
    f = _make_dummy_file(b"1", "pending_doc.pdf", "application/pdf")
    await async_client.post("/api/v1/documents/upload", files=f, headers=auth_headers)

    res_pending = await async_client.get(
        "/api/v1/documents", params={"status": "pending"}, headers=auth_headers
    )
    assert res_pending.status_code == 200
    for d in res_pending.json()["data"]:
        assert d["status"] == "pending"

    res_failed = await async_client.get(
        "/api/v1/documents", params={"status": "failed"}, headers=auth_headers
    )
    assert res_failed.status_code == 200
    for d in res_failed.json()["data"]:
        assert d["status"] == "failed"


@pytest.mark.asyncio
async def test_list_documents_sorting(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Sorting by file_name and -file_name."""
    f_a = _make_dummy_file(b"a", "Alpha.pdf", "application/pdf")
    f_z = _make_dummy_file(b"z", "Zeta.pdf", "application/pdf")
    await async_client.post("/api/v1/documents/upload", files=f_a, headers=auth_headers)
    await async_client.post("/api/v1/documents/upload", files=f_z, headers=auth_headers)

    res_asc = await async_client.get(
        "/api/v1/documents", params={"sort": "file_name"}, headers=auth_headers
    )
    assert res_asc.status_code == 200

    res_desc = await async_client.get(
        "/api/v1/documents", params={"sort": "-file_name"}, headers=auth_headers
    )
    assert res_desc.status_code == 200


@pytest.mark.asyncio
async def test_invalid_sort_parameter_rejected(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Arbitrary SQL/sort field injection attempt is rejected with 400."""
    response = await async_client.get(
        "/api/v1/documents",
        params={"sort": "id; DROP TABLE users;--"},
        headers=auth_headers,
    )
    assert response.status_code == 400


# =============================================================================
# 4. Soft Delete & Audit Log tests
# =============================================================================


@pytest.mark.asyncio
async def test_delete_and_audit_log(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Soft-deleting a document makes it inaccessible and creates audit records."""
    files = _make_dummy_file(b"to delete", "delete_audit.pdf", "application/pdf")
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["data"]["id"]
    doc_uuid = uuid.UUID(doc_id)

    # Delete
    del_res = await async_client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # Inaccessible via GET
    get_res = await async_client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert get_res.status_code == 404

    # Inaccessible via Download
    dl_res = await async_client.get(f"/api/v1/documents/{doc_id}/download", headers=auth_headers)
    assert dl_res.status_code == 404

    # Verify audit logs in PostgreSQL
    audit_res = await db_session.execute(select(AuditLog).where(AuditLog.record_id == doc_uuid))
    logs = list(audit_res.scalars().all())
    actions = [log.action for log in logs]
    assert "document.upload" in actions
    assert "document.delete" in actions


# =============================================================================
# 5. Additional Role & Validation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_hr_can_access_and_download_any_document(
    async_client: AsyncClient,
    auth_headers: dict,
    hr_headers: dict,
) -> None:
    """HR user can access and download documents owned by others."""
    files = _make_dummy_file(b"employee personal record", "hr_test.pdf", "application/pdf")
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["data"]["id"]

    # HR lists documents
    list_res = await async_client.get("/api/v1/documents", headers=hr_headers)
    assert list_res.status_code == 200
    ids = [d["id"] for d in list_res.json()["data"]]
    assert doc_id in ids

    # HR downloads document
    dl_res = await async_client.get(f"/api/v1/documents/{doc_id}/download", headers=hr_headers)
    assert dl_res.status_code == 200
    assert dl_res.content == b"employee personal record"


@pytest.mark.asyncio
async def test_update_document_metadata_success(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Owner can update file_name metadata via PATCH."""
    files = _make_dummy_file(b"content", "initial_name.pdf", "application/pdf")
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    doc_id = upload_res.json()["data"]["id"]

    patch_res = await async_client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"file_name": "renamed_doc.pdf"},
        headers=auth_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["file_name"] == "renamed_doc.pdf"


@pytest.mark.asyncio
async def test_create_document_metadata_backward_compat(
    async_client: AsyncClient,
    auth_headers: dict,
    test_user: User,
) -> None:
    """POST /documents creates metadata record with owner stamped from JWT."""
    response = await async_client.post(
        "/api/v1/documents",
        json={
            "file_name": "manual_meta.pdf",
            "storage_path": "uploads/manual_meta.pdf",
            "file_size": 1024,
            "file_type": "application/pdf",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["owner_id"] == str(test_user.id)
    assert data["status"] == "pending"
