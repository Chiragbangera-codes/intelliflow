"""
audit_diagnostics.py — Database and FAISS diagnostics for Milestone 7 Acceptance Audit.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, "/app")

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models.ai_embedding import AIEmbedding
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.role import Role
from app.models.user import User
from app.services.vector_store_service import vector_store


async def main() -> None:
    print("=" * 60)
    print("INTELLIFLOW AI — MILESTONE 7 PRODUCTION AUDIT DIAGNOSTICS")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # 1. User summary
        users_count = (await db.execute(select(func.count(User.id)))).scalar_one()
        roles_rows = (
            await db.execute(
                select(Role.name, func.count(User.id))
                .join(User, User.role_id == Role.id)
                .group_by(Role.name)
            )
        ).all()
        print(f"\n[1] USERS ({users_count} total):")
        for rname, cnt in roles_rows:
            print(f"    - Role '{rname}': {cnt} users")

        # 2. Document summary
        docs_total = (await db.execute(select(func.count(Document.id)))).scalar_one()
        docs_active = (
            await db.execute(select(func.count(Document.id)).where(Document.deleted_at.is_(None)))
        ).scalar_one()
        docs_deleted = docs_total - docs_active
        print(
            f"\n[2] DOCUMENTS: {docs_total} total ({docs_active} active, {docs_deleted} soft-deleted)"
        )

        # 3. Chunks summary
        chunks_total = (await db.execute(select(func.count(DocumentChunk.id)))).scalar_one()
        chunks_active = (
            await db.execute(
                select(func.count(DocumentChunk.id))
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(Document.deleted_at.is_(None))
            )
        ).scalar_one()
        print(f"\n[3] CHUNKS: {chunks_total} total ({chunks_active} active)")

        # 4. Embeddings summary
        embeddings_total = (await db.execute(select(func.count(AIEmbedding.id)))).scalar_one()
        embeddings_active = (
            await db.execute(
                select(func.count(AIEmbedding.id))
                .join(DocumentChunk, DocumentChunk.id == AIEmbedding.document_chunk_id)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(Document.deleted_at.is_(None))
            )
        ).scalar_one()
        print(f"\n[4] EMBEDDINGS: {embeddings_total} total ({embeddings_active} active)")

        # 5. Invariants
        print("\n[5] INVARIANT VERIFICATION:")
        # Check if chunks == embeddings for active
        diff_active = chunks_active - embeddings_active
        print(
            f"    - active chunks vs embeddings match: {chunks_active == embeddings_active} (diff={diff_active})"
        )

        # Check every embedding has valid chunk
        orphaned_emb = (
            await db.execute(
                select(func.count(AIEmbedding.id))
                .outerjoin(DocumentChunk, DocumentChunk.id == AIEmbedding.document_chunk_id)
                .where(DocumentChunk.id.is_(None))
            )
        ).scalar_one()
        print(f"    - orphaned embeddings (no chunk): {orphaned_emb}")

        # Check every chunk has valid document
        orphaned_chunks = (
            await db.execute(
                select(func.count(DocumentChunk.id))
                .outerjoin(Document, Document.id == DocumentChunk.document_id)
                .where(Document.id.is_(None))
            )
        ).scalar_one()
        print(f"    - orphaned chunks (no document): {orphaned_chunks}")

        # Check chunks missing embeddings
        missing_emb = (
            await db.execute(
                select(func.count(DocumentChunk.id))
                .join(Document, Document.id == DocumentChunk.document_id)
                .outerjoin(AIEmbedding, AIEmbedding.document_chunk_id == DocumentChunk.id)
                .where(Document.deleted_at.is_(None), AIEmbedding.id.is_(None))
            )
        ).scalar_one()
        print(f"    - active chunks missing embeddings: {missing_emb}")

        # 6. FAISS state
        vector_store.ensure_loaded()
        faiss_cnt = vector_store.vector_count
        mapping_cnt = len(vector_store._mapping)
        print("\n[6] FAISS INDEX & MAPPING:")
        print(f"    - Loaded: {vector_store.is_loaded}")
        print(f"    - FAISS Vector Count: {faiss_cnt}")
        print(f"    - FAISS Mapping Count: {mapping_cnt}")
        print(f"    - FAISS Vector Dim: {vector_store._dimension}")

        # Check stale IDs in FAISS (IDs in mapping not in DB)
        mapped_ids = [uuid.UUID(uid_str) for uid_str in vector_store._mapping.values()]
        stale_faiss_ids = 0
        deleted_doc_faiss_ids = 0
        for cid in mapped_ids:
            chunk_row = (
                await db.execute(
                    select(DocumentChunk.id, Document.deleted_at)
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(DocumentChunk.id == cid)
                )
            ).first()
            if not chunk_row:
                stale_faiss_ids += 1
            elif chunk_row[1] is not None:
                deleted_doc_faiss_ids += 1

        print(f"    - Stale FAISS IDs (not in DB at all): {stale_faiss_ids}")
        print(f"    - FAISS IDs belonging to soft-deleted docs: {deleted_doc_faiss_ids}")

        # 7. Document Details & Ownership Distribution
        docs = (
            await db.execute(
                select(
                    Document.id,
                    Document.file_name,
                    Document.owner_id,
                    Document.status,
                    Document.ocr_status,
                    Document.deleted_at,
                    User.email,
                    Role.name,
                )
                .join(User, User.id == Document.owner_id)
                .join(Role, Role.id == User.role_id)
                .order_by(Document.created_at.desc())
            )
        ).all()

        print(f"\n[7] DOCUMENTS DETAIL ({len(docs)} docs):")
        for d in docs:
            c_cnt = (
                await db.execute(
                    select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == d[0])
                )
            ).scalar_one()
            # Sample first chunk
            first_chunk = (
                await db.execute(
                    select(DocumentChunk.chunk_number, func.substr(DocumentChunk.content, 1, 80))
                    .where(DocumentChunk.document_id == d[0])
                    .order_by(DocumentChunk.chunk_number.asc())
                    .limit(1)
                )
            ).first()
            sample = f"c#{first_chunk[0]}: {first_chunk[1]}..." if first_chunk else "NO CHUNKS"
            del_str = "[DELETED]" if d[5] is not None else "[ACTIVE]"
            print(
                f"    {del_str} Doc {d[0]} | File: '{d[1]}' | Owner: {d[6]} ({d[7]}) | Chunks: {c_cnt}"
            )
            print(f"        Sample: {sample}")

    print("\n" + "=" * 60)
    print("DIAGNOSTICS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
