"""
Milestone 11 — Document Access & Department Authorization Test Suite.
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.department import Department
from app.models.role import Role
from app.models.user import User, UserStatus


@pytest.mark.asyncio
async def test_department_member_can_view_department_document(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Users in the same department can access internal departmental documents."""
    dept = Department(id=uuid.uuid4(), name=f"Eng_{uuid.uuid4().hex[:6]}")
    db_session.add(dept)

    test_user.department_id = dept.id

    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    colleague = User(
        id=uuid.uuid4(),
        email=f"colleague_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Colleague",
        last_name="Eng",
        role_id=emp_role.id,
        department_id=dept.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(colleague)
    await db_session.commit()

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("architecture.pdf", io.BytesIO(b"eng content"), "application/pdf")},
        data={"department_id": str(dept.id), "confidentiality": "internal"},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    colleague_token = create_access_token(subject=str(colleague.id), role="employee")
    get_res = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {colleague_token}"},
    )
    assert get_res.status_code == 200


@pytest.mark.asyncio
async def test_foreign_department_member_denied(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Users in a different department cannot access internal departmental documents."""
    dept1 = Department(id=uuid.uuid4(), name=f"Finance_{uuid.uuid4().hex[:6]}")
    dept2 = Department(id=uuid.uuid4(), name=f"Sales_{uuid.uuid4().hex[:6]}")
    db_session.add_all([dept1, dept2])

    test_user.department_id = dept1.id

    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    sales_user = User(
        id=uuid.uuid4(),
        email=f"sales_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Sales",
        last_name="Rep",
        role_id=emp_role.id,
        department_id=dept2.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(sales_user)
    await db_session.commit()

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("budget.pdf", io.BytesIO(b"finance content"), "application/pdf")},
        data={"department_id": str(dept1.id), "confidentiality": "internal"},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    sales_token = create_access_token(subject=str(sales_user.id), role="employee")
    res = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {sales_token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_restricted_confidentiality_blocks_department_access(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Restricted confidentiality restricts access strictly to owner and direct grants."""
    dept = Department(id=uuid.uuid4(), name=f"Legal_{uuid.uuid4().hex[:6]}")
    db_session.add(dept)

    test_user.department_id = dept.id

    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    colleague = User(
        id=uuid.uuid4(),
        email=f"peer_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Legal",
        last_name="Peer",
        role_id=emp_role.id,
        department_id=dept.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(colleague)
    await db_session.commit()

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("lawsuit.pdf", io.BytesIO(b"highly restricted"), "application/pdf")},
        data={"department_id": str(dept.id), "confidentiality": "restricted"},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    colleague_token = create_access_token(subject=str(colleague.id), role="employee")
    res = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {colleague_token}"},
    )
    assert res.status_code == 403
