"""
Milestone 11 — Bulk Document Operations Test Suite.
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
async def test_bulk_archive_and_restore(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """User can bulk archive and restore multiple owned documents."""
    doc_ids = []
    for i in range(3):
        res = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": (f"doc_{i}.pdf", io.BytesIO(b"content"), "application/pdf")},
            headers=auth_headers,
        )
        doc_ids.append(res.json()["data"]["id"])

    # Bulk archive
    arch_res = await async_client.post(
        "/api/v1/documents/bulk/archive",
        json={"document_ids": doc_ids},
        headers=auth_headers,
    )
    assert arch_res.status_code == 200
    arch_data = arch_res.json()
    assert arch_data["succeeded"] == 3
    assert arch_data["failed"] == 0

    # Bulk restore
    rest_res = await async_client.post(
        "/api/v1/documents/bulk/restore",
        json={"document_ids": doc_ids},
        headers=auth_headers,
    )
    assert rest_res.status_code == 200
    rest_data = rest_res.json()
    assert rest_data["succeeded"] == 3
    assert rest_data["failed"] == 0


@pytest.mark.asyncio
async def test_bulk_tagging(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """User can add tags to multiple documents simultaneously."""
    doc_ids = []
    for i in range(2):
        res = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": (f"tagdoc_{i}.pdf", io.BytesIO(b"content"), "application/pdf")},
            headers=auth_headers,
        )
        doc_ids.append(res.json()["data"]["id"])

    tag_res = await async_client.post(
        "/api/v1/documents/bulk/tag",
        json={"document_ids": doc_ids, "tags": ["q3", "finance"], "replace": False},
        headers=auth_headers,
    )
    assert tag_res.status_code == 200
    assert tag_res.json()["succeeded"] == 2


@pytest.mark.asyncio
async def test_bulk_mixed_authorization_results(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Bulk operation on a mix of owned and foreign documents returns itemized results."""
    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    other_user = User(
        id=uuid.uuid4(),
        email=f"bulkother_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Other",
        last_name="User",
        role_id=emp_role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(other_user)
    await db_session.commit()

    # User A uploads doc
    res_a = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc_a.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_a_id = res_a.json()["data"]["id"]

    # User B uploads doc
    token_b = create_access_token(subject=str(other_user.id), role="employee")
    res_b = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc_b.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    doc_b_id = res_b.json()["data"]["id"]

    # User A attempts to bulk archive both doc_a and doc_b
    bulk_res = await async_client.post(
        "/api/v1/documents/bulk/archive",
        json={"document_ids": [doc_a_id, doc_b_id]},
        headers=auth_headers,
    )
    assert bulk_res.status_code == 200
    data = bulk_res.json()
    assert data["succeeded"] == 1
    assert data["failed"] == 1

    results_by_id = {r["document_id"]: r for r in data["results"]}
    assert results_by_id[doc_a_id]["success"] is True
    assert results_by_id[doc_b_id]["success"] is False
    assert "Insufficient permissions" in results_by_id[doc_b_id]["reason"]


@pytest.mark.asyncio
async def test_bulk_limit_enforced(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Requesting more than DOCUMENT_BULK_MAX_ITEMS returns 422."""
    too_many = [str(uuid.uuid4()) for _ in range(101)]
    res = await async_client.post(
        "/api/v1/documents/bulk/archive",
        json={"document_ids": too_many},
        headers=auth_headers,
    )
    assert res.status_code == 422
