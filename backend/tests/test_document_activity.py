"""
Milestone 11 — Document Activity Timeline Test Suite.
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
async def test_document_activity_timeline(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Document operations generate visible, sanitized activity timeline entries."""
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("project.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    # Perform actions
    await async_client.post(f"/api/v1/documents/{doc_id}/archive", headers=auth_headers)
    await async_client.post(f"/api/v1/documents/{doc_id}/restore", headers=auth_headers)

    # Fetch activity
    act_res = await async_client.get(f"/api/v1/documents/{doc_id}/activity", headers=auth_headers)
    assert act_res.status_code == 200
    act_data = act_res.json()
    assert act_data["document_id"] == doc_id
    assert len(act_data["data"]) >= 3

    actions = [item["action"] for item in act_data["data"]]
    assert "document.upload" in actions
    assert "document.archived" in actions
    assert "document.restored" in actions


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_view_activity(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """A user with no access to a document cannot view its activity timeline."""
    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    other_user = User(
        id=uuid.uuid4(),
        email=f"actother_{uuid.uuid4().hex[:6]}@example.com",
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
        files={"file": ("secret_project.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    token_b = create_access_token(subject=str(other_user.id), role="employee")
    act_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/activity",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert act_res.status_code == 403
