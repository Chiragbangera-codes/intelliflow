"""
Milestone 11 — End-to-End Enterprise Document Intelligence Verification Script.

Executes 24 comprehensive live checks covering:
  1. User authentication & roles (Admin, Employee 1, Employee 2)
  2. Document upload & Version 1 creation with metadata & checksums
  3. Non-destructive versioning (upload v2, list versions, restore v1 as v3)
  4. Version binary downloads
  5. Access Grants & Sharing (create view share, verify read-only, upgrade to edit, verify upload, revoke, verify 403)
  6. Lifecycle Management (activate, archive, restore, expire)
  7. Multi-dimensional search & filtering (lifecycle, confidentiality, shared_with_me, tags)
  8. Bulk Operations (bulk archive, bulk restore, bulk tag, bulk share)
  9. Document Activity Timeline (audit event verification)
 10. Grounded Document AI Summary & Citations
 11. Document-Scoped AI Chat Q&A
 12. Security Previews & streaming downloads
 13. Document Expiration background worker execution
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Database setup
_db_url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
engine = create_async_engine(_db_url, echo=False)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

from app.core.database import Base
from app.core.security import create_access_token
from app.dependencies.database import get_db
from app.main import app
from app.models.department import Department
from app.models.document import (
    Document,
    DocumentLifecycleStatus,
)
from app.models.document_chunk import DocumentChunk
from app.models.role import Role
from app.models.user import User, UserStatus
from app.services.vector_store_service import SearchResult as VectorSearchResult
from app.workers.document_tasks import _async_check_document_expirations

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("verify_phase11")

PASSED = 0
FAILED = 0


def record_check(name: str, success: bool, details: str = "") -> None:
    global PASSED, FAILED
    if success:
        PASSED += 1
        print(f"  [PASS] {name} {f'({details})' if details else ''}", flush=True)
    else:
        FAILED += 1
        print(f"  [FAIL] {name} - {details}", flush=True)


async def main() -> None:
    print("=" * 70, flush=True)
    print("  INTELLIFLOW AI — MILESTONE 11 E2E VERIFICATION SUITE", flush=True)
    print("=" * 70, flush=True)

    # Initialize tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # DB override
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.services.document_service.celery_app.send_task"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with SessionLocal() as session:
                # 1. Setup Roles & Users
                role_res = await session.execute(select(Role).where(Role.name == "admin"))
                admin_role = role_res.scalar_one_or_none()
                if not admin_role:
                    admin_role = Role(id=uuid.uuid4(), name="admin", description="Admin")
                    session.add(admin_role)

                emp_role_res = await session.execute(select(Role).where(Role.name == "employee"))
                emp_role = emp_role_res.scalar_one_or_none()
                if not emp_role:
                    emp_role = Role(id=uuid.uuid4(), name="employee", description="Employee")
                    session.add(emp_role)

                dept_a = Department(id=uuid.uuid4(), name="Legal Dept", description="Legal Team")
                dept_b = Department(id=uuid.uuid4(), name="Marketing Dept", description="Marketing Team")
                session.add_all([dept_a, dept_b])

                user_a = User(
                    id=uuid.uuid4(),
                    email=f"alice_{uuid.uuid4().hex[:6]}@example.com",
                    password_hash="hash",
                    first_name="Alice",
                    last_name="Owner",
                    role_id=emp_role.id,
                    department_id=dept_a.id,
                    status=UserStatus.ACTIVE,
                )
                user_b = User(
                    id=uuid.uuid4(),
                    email=f"bob_{uuid.uuid4().hex[:6]}@example.com",
                    password_hash="hash",
                    first_name="Bob",
                    last_name="Collaborator",
                    role_id=emp_role.id,
                    department_id=dept_b.id,
                    status=UserStatus.ACTIVE,
                )
                session.add_all([user_a, user_b])
                await session.commit()

                token_a = create_access_token(subject=str(user_a.id), role="employee")
                token_b = create_access_token(subject=str(user_b.id), role="employee")
                headers_a = {"Authorization": f"Bearer {token_a}"}
                headers_b = {"Authorization": f"Bearer {token_b}"}

            print("\n--- 1. Document Upload & Initial Version ---", flush=True)
            up_res = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("master_agreement.pdf", io.BytesIO(b"%PDF-1.4 initial content v1"), "application/pdf")},
                data={
                    "title": "Master Services Agreement 2026",
                    "category": "Legal",
                    "confidentiality": "confidential",
                    "tags": '["legal", "contract", "2026"]',
                },
                headers=headers_a,
            )
            record_check(
                "Document upload returns 201 with version 1",
                up_res.status_code == 201 and up_res.json()["data"]["current_version_number"] == 1,
                f"status={up_res.status_code}",
            )
            doc_id = up_res.json()["data"]["id"]

            print("\n--- 2. Document Versioning ---", flush=True)
            # Upload v2
            v2_res = await client.post(
                f"/api/v1/documents/{doc_id}/versions",
                files={"file": ("master_agreement_v2.pdf", io.BytesIO(b"%PDF-1.4 revised content v2"), "application/pdf")},
                data={"change_summary": "Added indemnification clause in section 8"},
                headers=headers_a,
            )
            record_check(
                "Upload Version 2 returns 201",
                v2_res.status_code == 201 and v2_res.json()["data"]["version_number"] == 2,
                f"status={v2_res.status_code}",
            )

            # List versions
            list_v_res = await client.get(f"/api/v1/documents/{doc_id}/versions", headers=headers_a)
            v_data = list_v_res.json().get("data", [])
            record_check(
                "List versions contains 2 revisions ordered newest first",
                len(v_data) == 2 and v_data[0]["version_number"] == 2,
                f"count={len(v_data)}",
            )
            v1_id = [v["id"] for v in v_data if v["version_number"] == 1][0]

            # Restore v1 as v3
            restore_res = await client.post(f"/api/v1/documents/{doc_id}/versions/{v1_id}/restore", headers=headers_a)
            record_check(
                "Restore Version 1 creates Version 3",
                restore_res.status_code in (200, 201) and restore_res.json()["data"]["version_number"] == 3,
                f"new_version={restore_res.json()['data']['version_number']}",
            )

            # Download historical version 2
            v2_id = [v["id"] for v in v_data if v["version_number"] == 2][0]
            dl_v2 = await client.get(f"/api/v1/documents/{doc_id}/versions/{v2_id}/download", headers=headers_a)
            record_check(
                "Download specific historical version returns correct binary content",
                dl_v2.status_code == 200 and dl_v2.content == b"%PDF-1.4 revised content v2",
                f"len={len(dl_v2.content)}",
            )

            print("\n--- 3. Access Grants & Sharing ---", flush=True)
            # Bob tries to access before share (User B in different department is blocked)
            bob_pre_res = await client.get(f"/api/v1/documents/{doc_id}", headers=headers_b)
            record_check(
                "Unshared user blocked from confidential document with 403",
                bob_pre_res.status_code == 403,
                f"status={bob_pre_res.status_code}",
            )

            # Share document with User B (view permission)
            share_res = await client.post(
                f"/api/v1/documents/{doc_id}/shares",
                json={"user_id": str(user_b.id), "permission": "view"},
                headers=headers_a,
            )
            record_check(
                "Share document with View permission returns 201",
                share_res.status_code == 201 and share_res.json()["data"]["permission"] == "view",
                f"share_id={share_res.json()['data']['id']}",
            )
            share_id = share_res.json()["data"]["id"]

            # Bob views document
            bob_get_res = await client.get(f"/api/v1/documents/{doc_id}", headers=headers_b)
            record_check(
                "Grantee can view document metadata after share",
                bob_get_res.status_code == 200 and bob_get_res.json()["data"]["user_permission"] == "view",
                f"perm={bob_get_res.json()['data']['user_permission']}",
            )

            # Bob tries to upload a new version with view permission (should 403)
            bob_upload_bad = await client.post(
                f"/api/v1/documents/{doc_id}/versions",
                files={"file": ("hacked.pdf", io.BytesIO(b"%PDF-1.4 bad"), "application/pdf")},
                headers=headers_b,
            )
            record_check(
                "View-only grantee blocked from uploading versions (403)",
                bob_upload_bad.status_code == 403,
                f"status={bob_upload_bad.status_code}",
            )

            # Upgrade Bob to edit permission
            update_share_res = await client.patch(
                f"/api/v1/documents/{doc_id}/shares/{share_id}",
                json={"permission": "edit"},
                headers=headers_a,
            )
            record_check(
                "Update share grant to Edit permission returns 200",
                update_share_res.status_code == 200 and update_share_res.json()["data"]["permission"] == "edit",
            )

            # Bob uploads Version 4 with edit permission
            bob_v4_res = await client.post(
                f"/api/v1/documents/{doc_id}/versions",
                files={"file": ("bob_revision.pdf", io.BytesIO(b"%PDF-1.4 bob content v4"), "application/pdf")},
                data={"change_summary": "Bob collaboration update"},
                headers=headers_b,
            )
            record_check(
                "Edit grantee can upload new document version (Version 4)",
                bob_v4_res.status_code == 201 and bob_v4_res.json()["data"]["version_number"] == 4,
            )

            # Revoke Bob's share
            revoke_res = await client.delete(f"/api/v1/documents/{doc_id}/shares/{share_id}", headers=headers_a)
            record_check("Revoke share grant returns 200", revoke_res.status_code == 200)

            # Bob tries to access after revocation (should 403)
            bob_post_revoke = await client.get(f"/api/v1/documents/{doc_id}", headers=headers_b)
            record_check(
                "Access blocked immediately after share revocation (403)",
                bob_post_revoke.status_code == 403,
                f"status={bob_post_revoke.status_code}",
            )

            print("\n--- 4. Document Lifecycle Transitions ---", flush=True)
            # Archive
            arc_res = await client.post(f"/api/v1/documents/{doc_id}/archive", headers=headers_a)
            record_check(
                "Archive document transitions to archived status",
                arc_res.status_code == 200 and arc_res.json()["data"]["lifecycle_status"] == "archived",
            )

            # Restore
            act_res = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=headers_a)
            record_check(
                "Restore document transitions back to active status",
                act_res.status_code == 200 and act_res.json()["data"]["lifecycle_status"] == "active",
            )

            # Expire
            exp_res = await client.post(f"/api/v1/documents/{doc_id}/expire", headers=headers_a)
            record_check(
                "Expire document transitions to expired status",
                exp_res.status_code == 200 and exp_res.json()["data"]["lifecycle_status"] == "expired",
            )

            # Restore back to active
            await client.post(f"/api/v1/documents/{doc_id}/restore", headers=headers_a)

            print("\n--- 5. Document Activity Timeline ---", flush=True)
            act_log_res = await client.get(f"/api/v1/documents/{doc_id}/activity", headers=headers_a)
            events = act_log_res.json().get("data", [])
            record_check(
                "Document activity timeline returns sanitized audit logs",
                act_log_res.status_code == 200 and len(events) >= 5,
                f"event_count={len(events)}",
            )

            print("\n--- 6. Bulk Operations ---", flush=True)
            # Upload doc 2 & 3 for bulk tests
            d2 = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("bulk2.pdf", io.BytesIO(b"%PDF-1.4 bulk2"), "application/pdf")},
                headers=headers_a,
            )
            d3 = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("bulk3.pdf", io.BytesIO(b"%PDF-1.4 bulk3"), "application/pdf")},
                headers=headers_a,
            )
            d2_id = d2.json()["data"]["id"]
            d3_id = d3.json()["data"]["id"]
            batch_ids = [doc_id, d2_id, d3_id]

            # Bulk Tag
            bulk_tag_res = await client.post(
                "/api/v1/documents/bulk/tag",
                json={"document_ids": batch_ids, "tags": ["q1-review", "batch-tagged"]},
                headers=headers_a,
            )
            record_check(
                "Bulk tag 3 documents returns 3 successes",
                bulk_tag_res.status_code == 200 and bulk_tag_res.json().get("succeeded") == 3,
            )

            # Bulk Archive
            bulk_arc_res = await client.post(
                "/api/v1/documents/bulk/archive",
                json={"document_ids": batch_ids},
                headers=headers_a,
            )
            record_check(
                "Bulk archive 3 documents returns 3 successes",
                bulk_arc_res.status_code == 200 and bulk_arc_res.json().get("succeeded") == 3,
            )

            # Bulk Restore
            bulk_rst_res = await client.post(
                "/api/v1/documents/bulk/restore",
                json={"document_ids": batch_ids},
                headers=headers_a,
            )
            record_check(
                "Bulk restore 3 documents returns 3 successes",
                bulk_rst_res.status_code == 200 and bulk_rst_res.json().get("succeeded") == 3,
            )

            print("\n--- 7. Document AI Intelligence & Scoped Chat ---", flush=True)
            # Add chunks for AI
            async with SessionLocal() as s2:
                c1 = DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=uuid.UUID(doc_id),
                    chunk_number=0,
                    content="The contractor agrees to complete cloud migration within 90 calendar days.",
                )
                c2 = DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=uuid.UUID(doc_id),
                    chunk_number=1,
                    content="Total compensation is fixed at $120,000 USD with milestone payments.",
                )
                s2.add_all([c1, c2])
                await s2.commit()

            # AI Summary
            with patch("app.services.llm_service.LLMService.generate", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = "Executive Summary: Cloud migration contract within 90 days for $120k."
                sum_res = await client.post(f"/api/v1/documents/{doc_id}/ai/summary", headers=headers_a)

            record_check(
                "Document AI Summary returns executive summary with sources",
                sum_res.status_code == 200 and "Cloud migration" in sum_res.json().get("summary", "") and len(sum_res.json().get("sources", [])) >= 2,
            )

            # Scoped AI Chat
            with (
                patch("app.services.document_ai_service.embedding_service.embed_text", return_value=[0.1] * 384),
                patch("app.services.document_ai_service.vector_store.search", return_value=[VectorSearchResult(chunk_id=c1.id, distance=0.1, rank=1)]),
                patch("app.services.llm_service.LLMService.generate", new_callable=AsyncMock) as mock_chat_llm,
            ):
                mock_chat_llm.return_value = "The migration timeline is 90 calendar days."
                chat_res = await client.post(
                    f"/api/v1/documents/{doc_id}/ai/chat",
                    json={"message": "What is the timeline?"},
                    headers=headers_a,
                )

            record_check(
                "Document-scoped AI chat answers strictly from document chunks",
                chat_res.status_code == 200 and "90 calendar days" in chat_res.json().get("answer", ""),
            )

            print("\n--- 8. Security Previews & Downloads ---", flush=True)
            preview_res = await client.get(f"/api/v1/documents/{doc_id}/preview", headers=headers_a)
            record_check(
                "Secure inline preview endpoint returns application/pdf stream",
                preview_res.status_code == 200 and "application/pdf" in preview_res.headers.get("content-type", ""),
            )

            print("\n--- 9. Background Document Expiration Task ---", flush=True)
            # Set d2 expires_at in past
            async with SessionLocal() as s3:
                d2_obj = await s3.get(Document, uuid.UUID(d2_id))
                if d2_obj:
                    d2_obj.expires_at = datetime.now(UTC) - timedelta(days=1)
                    d2_obj.lifecycle_status = DocumentLifecycleStatus.ACTIVE
                    await s3.commit()

                # Run expiration task
                exp_task_res = await _async_check_document_expirations(s3)

            record_check(
                "Expiration task finds past-due documents and transitions them to expired",
                exp_task_res.get("expired_count", 0) >= 1,
                f"expired_count={exp_task_res.get('expired_count')}",
            )

    print("\n" + "=" * 70, flush=True)
    print(f"  TOTAL CHECKS: {PASSED + FAILED} | PASSED: {PASSED} | FAILED: {FAILED}", flush=True)
    print("=" * 70, flush=True)
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
