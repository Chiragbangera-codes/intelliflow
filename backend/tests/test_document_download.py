"""
Milestone 11 — Secure Document Download & Preview Test Suite.
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


@pytest.mark.asyncio
async def test_download_and_preview_document(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Authorized user can download and preview the active document file."""
    content = b"PDF binary stream test data %PDF-1.7"
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("report.pdf", io.BytesIO(content), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    # 1. Download
    dl_res = await async_client.get(f"/api/v1/documents/{doc_id}/download", headers=auth_headers)
    assert dl_res.status_code == 200
    assert dl_res.content == content
    assert "attachment" in dl_res.headers.get("content-disposition", "")

    # 2. Preview
    pv_res = await async_client.get(f"/api/v1/documents/{doc_id}/preview", headers=auth_headers)
    assert pv_res.status_code == 200
    assert pv_res.content == content
    assert "inline" in pv_res.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_unauthorized_download_denied(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Unauthorized user receives 403 on download/preview attempts."""
    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    other_user = User(
        id=uuid.uuid4(),
        email=f"dlother_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Other",
        last_name="User",
        role_id=emp_role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(other_user)
    await db_session.commit()

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("confidential.pdf", io.BytesIO(b"secret"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    token_b = create_access_token(subject=str(other_user.id), role="employee")

    dl_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/download",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert dl_res.status_code == 403

    pv_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/preview",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert pv_res.status_code == 403
