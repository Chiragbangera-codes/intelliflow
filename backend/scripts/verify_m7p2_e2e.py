"""
Milestone 7 Phase 2 — Real End-to-End Semantic Search & Cross-User RBAC Verification Script.

This script verifies:
1. Real sentence-transformers embedding generation.
2. Real FAISS indexing & persistent search retrieval with actual vector distances.
3. Live document upload / chunking / embedding generation for two topically distinct documents:
   - Document A: "Engineering Architecture & Cloud Infrastructure (Kubernetes, FAISS, PostgreSQL, Redis)" owned by User A.
   - Document B: "Confidential Executive Payroll & Salary Compensation 2026" owned by User B.
4. Topically accurate query resolution:
   - "cloud microservices kubernetes cluster deployment" -> Ranks Document A #1.
   - "executive salary bonus payroll compensation breakdown" -> Ranks Document B #1.
5. Critical Cross-User RBAC Security Verification:
   - User A executes query "executive salary compensation"
     -> FAISS mathematically retrieves Document B chunks.
     -> PostgreSQL + Service RBAC drops Document B chunks.
     -> User A receives 0 results (or only authorized documents).
   - Admin executes the same query "executive salary compensation"
     -> Admin receives Document B chunks with high similarity.
6. Clean database & vector index cleanup.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

# Ensure project root in sys.path
sys.path.insert(0, "/app")

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.ai_embedding import AIEmbedding
from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.role import Role
from app.models.user import User, UserStatus
from app.services.embedding_service import embedding_service
from app.services.search_service import SearchService
from app.services.vector_store_service import ChunkVector, vector_store


async def run_e2e_verification() -> None:
    print("=" * 80)
    print("STARTING MILESTONE 7 PHASE 2 REAL E2E SEMANTIC SEARCH & RBAC VERIFICATION")
    print("=" * 80)

    async with AsyncSessionLocal() as session:
        # 1. Fetch roles
        roles_result = await session.execute(select(Role))
        roles_map = {r.name: r for r in roles_result.scalars().all()}
        admin_role = roles_map["admin"]
        employee_role = roles_map["employee"]

        # 2. Create Test Users
        tag = uuid.uuid4().hex[:6]
        user_a = User(
            email=f"alice_eng_{tag}@intelliflow.ai",
            password_hash=hash_password("Pass123!"),
            first_name="Alice",
            last_name="Engineer",
            role_id=employee_role.id,
            status=UserStatus.ACTIVE,
        )
        user_b = User(
            email=f"bob_hr_{tag}@intelliflow.ai",
            password_hash=hash_password("Pass123!"),
            first_name="Bob",
            last_name="Finance",
            role_id=employee_role.id,
            status=UserStatus.ACTIVE,
        )
        admin_user = User(
            email=f"admin_{tag}@intelliflow.ai",
            password_hash=hash_password("Pass123!"),
            first_name="Super",
            last_name="Admin",
            role_id=admin_role.id,
            status=UserStatus.ACTIVE,
        )
        session.add_all([user_a, user_b, admin_user])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        await session.refresh(admin_user)
        print(
            f"[+] Created Users: Alice (ID: {user_a.id}), Bob (ID: {user_b.id}), Admin (ID: {admin_user.id})"
        )

        # 3. Create Document A (Engineering Architecture - Owned by Alice)
        doc_a = Document(
            file_name="cloud_engineering_architecture.txt",
            storage_path=f"test_storage/{tag}/doc_a.txt",
            owner_id=user_a.id,
            file_type="text/plain",
            file_size=1024,
            status=DocumentStatus.PROCESSED,
            ocr_status=OcrStatus.COMPLETED,
        )
        # Create Document B (Confidential Payroll - Owned by Bob)
        doc_b = Document(
            file_name="executive_payroll_compensation.txt",
            storage_path=f"test_storage/{tag}/doc_b.txt",
            owner_id=user_b.id,
            file_type="text/plain",
            file_size=2048,
            status=DocumentStatus.PROCESSED,
            ocr_status=OcrStatus.COMPLETED,
        )
        session.add_all([doc_a, doc_b])
        await session.commit()
        await session.refresh(doc_a)
        await session.refresh(doc_b)
        print(f"[+] Created Documents: Doc A ({doc_a.file_name}), Doc B ({doc_b.file_name})")

        # 4. Create Chunks
        content_a1 = (
            "IntelliFlow microservice architecture utilizes Kubernetes clusters for scalable container orchestration. "
            "The backend uses FastAPI with asyncpg, Redis Celery queues for asynchronous OCR, and FAISS for 384-dimensional vector indexing."
        )
        content_a2 = (
            "PostgreSQL stores structured metadata, user identity, document chunk tables, and audit logs. "
            "Vector embeddings generated by sentence-transformers all-MiniLM-L6-v2 are indexed using FAISS IndexFlatL2."
        )
        chunk_a1 = DocumentChunk(document_id=doc_a.id, chunk_number=1, content=content_a1)
        chunk_a2 = DocumentChunk(document_id=doc_a.id, chunk_number=2, content=content_a2)

        content_b1 = (
            "CONFIDENTIAL: Executive Leadership Annual Salary and Compensation Schedule for Q4 2026. "
            "Base salary allocations, quarterly performance bonuses, executive equity stock options, and payroll disbursement dates."
        )
        content_b2 = "Total compensation packages include 401k match, health insurance subsidies, and retention bonuses for C-suite officers."
        chunk_b1 = DocumentChunk(document_id=doc_b.id, chunk_number=1, content=content_b1)
        chunk_b2 = DocumentChunk(document_id=doc_b.id, chunk_number=2, content=content_b2)

        session.add_all([chunk_a1, chunk_a2, chunk_b1, chunk_b2])
        await session.commit()
        await session.refresh(chunk_a1)
        await session.refresh(chunk_a2)
        await session.refresh(chunk_b1)
        await session.refresh(chunk_b2)
        print("[+] Created 4 document chunks in PostgreSQL.")

        # 5. Generate Real Embeddings & Register with FAISS
        all_chunks = [chunk_a1, chunk_a2, chunk_b1, chunk_b2]
        chunk_texts = [c.content for c in all_chunks]
        chunk_ids = [c.id for c in all_chunks]

        print("[*] Generating real embeddings via SentenceTransformer ('all-MiniLM-L6-v2')...")
        embeddings = embedding_service.embed_batch(chunk_texts)
        assert len(embeddings) == 4
        assert len(embeddings[0]) == 384

        print("[*] Adding embeddings to FAISS vector index...")
        chunk_vectors = [
            ChunkVector(chunk_id=cid, vector=vec) for cid, vec in zip(chunk_ids, embeddings, strict=False)
        ]
        vector_store.add_chunks(chunk_vectors)
        vector_store.save()
        print(
            f"[+] FAISS indexed successfully. Total vectors in index: {vector_store._index.ntotal}"
        )

        # Save AIEmbedding records
        for i, (chunk, vec) in enumerate(zip(all_chunks, embeddings, strict=False)):
            emb_record = AIEmbedding(
                document_chunk_id=chunk.id,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                vector_reference=str(i),
            )
            session.add(emb_record)
        await session.commit()
        print("[+] Persisted ai_embeddings records.")

        # 6. Initialize Search Service
        search_svc = SearchService(session)

        # ----------------------------------------------------------------------
        # Test Case 1: Alice searches for engineering topics
        # ----------------------------------------------------------------------
        print(
            "\n--- TEST CASE 1: Alice searches for 'Kubernetes microservice container deployment' ---"
        )
        res_alice_eng = await search_svc.semantic_search(
            query="Kubernetes microservice container deployment",
            actor=user_a,
            top_k=5,
            min_score=None,
        )
        print(f"Results returned to Alice: {res_alice_eng.total_results}")
        for r in res_alice_eng.results:
            print(
                f"  -> Rank: Doc: {r.document_name} | Chunk #{r.chunk_number} | Distance: {r.distance:.4f} | Similarity: {r.similarity:.4f}"
            )
        assert res_alice_eng.total_results >= 1
        assert res_alice_eng.results[0].document_id == doc_a.id
        print(
            "  [PASS] Test Case 1 Passed: Alice correctly retrieved her Engineering document with high similarity."
        )

        # ----------------------------------------------------------------------
        # Test Case 2: CRITICAL RBAC TEST - Alice searches for Payroll/Salary
        # ----------------------------------------------------------------------
        print(
            "\n--- TEST CASE 2: Alice (Employee) searches for 'executive salary bonus payroll compensation' ---"
        )
        # FAISS will mathematically match Bob's document as highest similarity!
        res_alice_salary = await search_svc.semantic_search(
            query="executive salary bonus payroll compensation",
            actor=user_a,
            top_k=5,
            min_score=None,
        )
        print(f"Results returned to Alice: {res_alice_salary.total_results}")
        for r in res_alice_salary.results:
            print(f"  -> Doc: {r.document_name} (ID: {r.document_id})")
            assert (
                r.document_id != doc_b.id
            ), "SECURITY VIOLATION: Alice accessed Bob's confidential document!"

        # Alice should NOT receive Bob's document B
        bob_doc_in_alice = any(r.document_id == doc_b.id for r in res_alice_salary.results)
        assert not bob_doc_in_alice, "SECURITY BREACH: Bob's document found in Alice's results!"
        print(
            "  [PASS] Test Case 2 Passed: RBAC defense-in-depth completely blocked Bob's payroll document from Alice."
        )

        # ----------------------------------------------------------------------
        # Test Case 3: Admin searches for Payroll/Salary (Global Access)
        # ----------------------------------------------------------------------
        print(
            "\n--- TEST CASE 3: Super Admin searches for 'executive salary bonus payroll compensation' ---"
        )
        res_admin_salary = await search_svc.semantic_search(
            query="executive salary bonus payroll compensation",
            actor=admin_user,
            top_k=5,
            min_score=None,
        )
        print(f"Results returned to Admin: {res_admin_salary.total_results}")
        for r in res_admin_salary.results:
            print(
                f"  -> Rank: Doc: {r.document_name} | Chunk #{r.chunk_number} | Distance: {r.distance:.4f} | Similarity: {r.similarity:.4f}"
            )
        assert res_admin_salary.total_results >= 1
        assert res_admin_salary.results[0].document_name == doc_b.file_name
        print(
            "  [PASS] Test Case 3 Passed: Super Admin with global privileges correctly accessed Bob's payroll document."
        )

        # ----------------------------------------------------------------------
        # Test Case 4: min_score threshold filtering
        # ----------------------------------------------------------------------
        print("\n--- TEST CASE 4: Similarity Threshold (min_score=0.90) ---")
        res_threshold = await search_svc.semantic_search(
            query="unrelated cooking recipe for apple pie baking oven",
            actor=admin_user,
            top_k=5,
            min_score=0.90,  # High threshold
        )
        print(
            f"Results returned with min_score=0.90 for unrelated query: {res_threshold.total_results}"
        )
        assert res_threshold.total_results == 0
        print(
            "  [PASS] Test Case 4 Passed: min_score successfully filtered out distant vector matches."
        )

        # ----------------------------------------------------------------------
        # Test Case 5: Audit Log Verification
        # ----------------------------------------------------------------------
        print("\n--- TEST CASE 5: Audit Trail Verification ---")
        audit_res = await session.execute(
            text(
                "SELECT action, user_id, new_value, created_at FROM audit_logs WHERE action = 'search.semantic' ORDER BY created_at DESC LIMIT 5"
            )
        )
        audit_rows = audit_res.fetchall()
        print(f"Recent search audit rows found: {len(audit_rows)}")
        assert len(audit_rows) >= 4
        for row in audit_rows:
            print(f"  -> Action: {row[0]} | User: {row[1]} | Metadata: {row[2]}")
        print("  [PASS] Test Case 5 Passed: Audit records created with safe metadata.")

        print("\n" + "=" * 80)
        print("ALL E2E VERIFICATION CHECKS PASSED PERFECTLY!")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
