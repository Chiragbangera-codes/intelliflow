"""
Milestone 11 — Document Lifecycle Management Test Suite.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_archive_and_restore_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Document transitions between active -> archived -> restored."""
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("policy.pdf", io.BytesIO(b"policy content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    # 1. Archive
    arch_res = await async_client.post(f"/api/v1/documents/{doc_id}/archive", headers=auth_headers)
    assert arch_res.status_code == 200
    assert arch_res.json()["data"]["lifecycle_status"] == "archived"

    # 2. Restore
    rest_res = await async_client.post(f"/api/v1/documents/{doc_id}/restore", headers=auth_headers)
    assert rest_res.status_code == 200
    assert rest_res.json()["data"]["lifecycle_status"] == "active"


@pytest.mark.asyncio
async def test_manual_expiration(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Document transitions from active -> expired."""
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("memo.pdf", io.BytesIO(b"memo content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    exp_res = await async_client.post(f"/api/v1/documents/{doc_id}/expire", headers=auth_headers)
    assert exp_res.status_code == 200
    assert exp_res.json()["data"]["lifecycle_status"] == "expired"
