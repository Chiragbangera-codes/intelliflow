"""
Milestone 11 — Document Search & Advanced Metadata Filtering Test Suite.
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
async def test_metadata_filtering(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Document list supports filtering by category, document_type, and confidentiality."""
    # Doc 1: Invoice / Financial / Internal
    await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("inv_1.pdf", io.BytesIO(b"content"), "application/pdf")},
        data={"category": "invoice", "document_type": "financial", "confidentiality": "internal"},
        headers=auth_headers,
    )
    # Doc 2: Contract / Legal / Confidential
    await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract_1.pdf", io.BytesIO(b"content"), "application/pdf")},
        data={"category": "contract", "document_type": "legal", "confidentiality": "confidential"},
        headers=auth_headers,
    )

    # Filter by category=invoice
    res1 = await async_client.get("/api/v1/documents?category=invoice", headers=auth_headers)
    assert res1.status_code == 200
    assert len(res1.json()["data"]) == 1
    assert res1.json()["data"][0]["category"] == "invoice"

    # Filter by document_type=legal
    res2 = await async_client.get("/api/v1/documents?document_type=legal", headers=auth_headers)
    assert res2.status_code == 200
    assert len(res2.json()["data"]) == 1
    assert res2.json()["data"][0]["document_type"] == "legal"


@pytest.mark.asyncio
async def test_shared_with_me_filter(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """shared_with_me=true filter returns only documents shared with the caller."""
    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    other_user = User(
        id=uuid.uuid4(),
        email=f"searchother_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Other",
        last_name="User",
        role_id=emp_role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(other_user)
    await db_session.commit()

    # User A uploads doc and shares with User B
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("shared_doc.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        json={"user_id": str(other_user.id), "permission": "view"},
        headers=auth_headers,
    )

    # User B queries shared_with_me=true
    token_b = create_access_token(subject=str(other_user.id), role="employee")
    shared_res = await async_client.get(
        "/api/v1/documents?shared_with_me=true",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert shared_res.status_code == 200
    data = shared_res.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == doc_id
