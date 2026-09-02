"""
Milestone 11 — Document Sharing & Access Grants Test Suite.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.role import Role
from app.models.user import User, UserStatus


@pytest.mark.asyncio
async def test_share_document_with_view_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Owner shares document with other user with VIEW permission."""
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

    # 1. Upload doc
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("report.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    # 2. Share with other_user
    share_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        json={"user_id": str(other_user.id), "permission": "view"},
        headers=auth_headers,
    )
    assert share_res.status_code == 201
    share_data = share_res.json()["data"]
    assert share_data["permission"] == "view"
    assert share_data["user_id"] == str(other_user.id)

    # 3. Other user can now GET document metadata
    token_other = create_access_token(subject=str(other_user.id), role="employee")
    get_res = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == doc_id

    # 4. Other user CANNOT delete the document (only VIEW granted)
    del_res = await async_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert del_res.status_code == 403


@pytest.mark.asyncio
async def test_share_with_edit_permission_allows_updates(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Grantee with EDIT permission can update metadata and upload versions."""
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

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("plan.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    # Share with EDIT
    await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        json={"user_id": str(other_user.id), "permission": "edit"},
        headers=auth_headers,
    )

    token_other = create_access_token(subject=str(other_user.id), role="employee")
    patch_res = await async_client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Updated by Collaborator"},
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["title"] == "Updated by Collaborator"


@pytest.mark.asyncio
async def test_revoking_share_blocks_access(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Revoking access grant removes all access immediately."""
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

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("secret.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    # Share
    sh_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        json={"user_id": str(other_user.id), "permission": "view"},
        headers=auth_headers,
    )
    share_id = sh_res.json()["data"]["id"]

    token_other = create_access_token(subject=str(other_user.id), role="employee")

    # Verify access works
    res_before = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert res_before.status_code == 200

    # Revoke share
    rev_res = await async_client.delete(
        f"/api/v1/documents/{doc_id}/shares/{share_id}",
        headers=auth_headers,
    )
    assert rev_res.status_code == 200

    # Verify access is now denied
    res_after = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert res_after.status_code == 403


@pytest.mark.asyncio
async def test_expired_share_is_denied(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """An access grant with expires_at in the past is treated as expired (403)."""
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

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("temp.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    # Share with expiration in the past
    past_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        json={"user_id": str(other_user.id), "permission": "view", "expires_at": past_time},
        headers=auth_headers,
    )

    token_other = create_access_token(subject=str(other_user.id), role="employee")
    res = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_other}"},
    )
    assert res.status_code == 403
