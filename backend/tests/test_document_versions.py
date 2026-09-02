"""
Milestone 11 — Document Versioning Test Suite.
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.role import Role
from app.models.user import User, UserStatus
from app.repositories.document_version_repository import DocumentVersionRepository


@pytest.mark.asyncio
async def test_initial_version_1_created_on_upload(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Uploading a document must automatically generate Version 1 with is_current=True."""
    file_bytes = b"%PDF-1.4 initial content for version 1"
    response = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract_v1.pdf", io.BytesIO(file_bytes), "application/pdf")},
        data={"title": "Contract Document"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    doc_id = uuid.UUID(response.json()["data"]["id"])

    # Check document_versions table
    ver_repo = DocumentVersionRepository(db_session)
    versions = await ver_repo.list_by_document(doc_id)
    assert len(versions) == 1
    v1 = versions[0]
    assert v1.version_number == 1
    assert v1.is_current is True
    assert v1.file_name == "contract_v1.pdf"
    assert v1.created_by == test_user.id


@pytest.mark.asyncio
async def test_upload_new_version_creates_version_2(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Uploading a new version must increment version_number and update current pointer."""
    # 1. Initial upload
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("spec.pdf", io.BytesIO(b"v1 content"), "application/pdf")},
        headers=auth_headers,
    )
    assert up_res.status_code == 201
    doc_id = up_res.json()["data"]["id"]

    # 2. Upload version 2
    v2_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("spec_revised.pdf", io.BytesIO(b"v2 content updated"), "application/pdf")},
        data={"change_summary": "Added Section 4"},
        headers=auth_headers,
    )
    assert v2_res.status_code == 201
    v2_data = v2_res.json()["data"]
    assert v2_data["version_number"] == 2
    assert v2_data["is_current"] is True
    assert v2_data["change_summary"] == "Added Section 4"

    # 3. Verify version list
    list_res = await async_client.get(f"/api/v1/documents/{doc_id}/versions", headers=auth_headers)
    assert list_res.status_code == 200
    versions = list_res.json()["data"]
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[0]["is_current"] is True
    assert versions[1]["version_number"] == 1
    assert versions[1]["is_current"] is False


@pytest.mark.asyncio
async def test_restore_version_creates_new_version(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Restoring Version 1 when at Version 2 must create Version 3 (non-destructive)."""
    # 1. Upload v1
    res1 = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("file.pdf", io.BytesIO(b"version 1"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = res1.json()["data"]["id"]

    # 2. Upload v2
    await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("file.pdf", io.BytesIO(b"version 2"), "application/pdf")},
        headers=auth_headers,
    )

    # 3. Get v1 id
    list_res = await async_client.get(f"/api/v1/documents/{doc_id}/versions", headers=auth_headers)
    v1_id = [v["id"] for v in list_res.json()["data"] if v["version_number"] == 1][0]

    # 4. Restore v1
    restore_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions/{v1_id}/restore",
        headers=auth_headers,
    )
    assert restore_res.status_code == 200
    v3_data = restore_res.json()["data"]
    assert v3_data["version_number"] == 3
    assert v3_data["is_current"] is True
    assert "Restored from Version 1" in v3_data["change_summary"]

    # 5. Check total versions is now 3
    final_list = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions", headers=auth_headers
    )
    assert len(final_list.json()["data"]) == 3


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_upload_version(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """A user without edit/manage permission cannot upload a new version."""
    # User A uploads document
    res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = res.json()["data"]["id"]

    # Create User B
    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    other_user = User(
        id=uuid.uuid4(),
        email=f"other_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Other",
        last_name="User",
        role_id=emp_role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(other_user)
    await db_session.commit()

    token_b = create_access_token(subject=str(other_user.id), role="employee")

    bad_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("doc.pdf", io.BytesIO(b"hacked"), "application/pdf")},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bad_res.status_code == 403


@pytest.mark.asyncio
async def test_download_specific_version(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Users with download permission can download specific historical versions."""
    res1 = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 original text v1"), "application/pdf")},
        headers=auth_headers,
    )
    assert res1.status_code == 201
    doc_id = res1.json()["data"]["id"]

    # Upload v2
    res2 = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("v2.pdf", io.BytesIO(b"%PDF-1.4 second text v2"), "application/pdf")},
        headers=auth_headers,
    )
    assert res2.status_code == 201

    # List versions
    list_res = await async_client.get(f"/api/v1/documents/{doc_id}/versions", headers=auth_headers)
    assert list_res.status_code == 200
    v1_id = [v["id"] for v in list_res.json()["data"] if v["version_number"] == 1][0]

    # Download v1
    dl_v1 = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions/{v1_id}/download",
        headers=auth_headers,
    )
    assert dl_v1.status_code == 200
    assert dl_v1.content == b"%PDF-1.4 original text v1"
