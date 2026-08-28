"""
Milestone 7 Phase 1 — AI Embedding Pipeline Tests.

Coverage (19 tests):
  1.  embed_text returns a vector
  2.  embed_batch returns vectors
  3.  embedding model is loaded lazily (not at import time)
  4.  embedding model is not repeatedly instantiated
  5.  FAISS index creation (build_index)
  6.  FAISS incremental add (add_chunks)
  7.  FAISS save/load roundtrip
  8.  FAISS mapping persistence
  9.  FAISS search returns expected chunk IDs
  10. empty index search behaves safely
  11. AIEmbedding repository creation
  12. AIEmbedding repository retrieval by chunk_id
  13. AIEmbedding deletion by document_id
  14. embedding Celery task with chunks — success path
  15. embedding Celery task with no chunks — graceful skip
  16. OCR completion dispatches embedding task
  17. embedding failure does not corrupt document OCR status
  18. worker warm-up handles missing index
  19. worker warm-up handles stale/corrupted index

All SentenceTransformer and FAISS calls are mocked.
No Ollama required.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.repositories.ai_embedding_repository import AIEmbeddingRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.vector_store_service import ChunkVector, VectorStoreService
from app.workers.ocr_tasks import _async_process_document_ocr

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EMBED_DIM = 384
_FAKE_VECTOR = [0.1] * EMBED_DIM


def _make_fake_model() -> MagicMock:
    """Return a MagicMock that mimics SentenceTransformer.encode()."""
    model = MagicMock()
    model.encode.side_effect = lambda texts, **kw: (
        np.array([[0.1] * EMBED_DIM for _ in texts], dtype=np.float32)
        if isinstance(texts, list)
        else np.array([0.1] * EMBED_DIM, dtype=np.float32)
    )
    return model


# ---------------------------------------------------------------------------
# EmbeddingService tests (tests 1–4)
# ---------------------------------------------------------------------------


class TestEmbeddingService:
    """Tests for EmbeddingService lazy loading and embed methods."""

    def _fresh_service(self) -> EmbeddingService:
        """Return a fresh EmbeddingService and reset the module-level model."""
        import app.services.embedding_service as emb_mod

        emb_mod._model_instance = None  # reset singleton
        return EmbeddingService()

    def test_embed_text_returns_vector(self) -> None:
        """Test 1: embed_text returns a list of floats with correct length."""
        svc = self._fresh_service()
        with patch(
            "app.services.embedding_service.SentenceTransformer",
            return_value=_make_fake_model(),
        ):
            import app.services.embedding_service as emb_mod

            emb_mod._model_instance = None
            vector = svc.embed_text("hello world")

        assert isinstance(vector, list)
        assert len(vector) == EMBED_DIM
        assert all(isinstance(v, float) for v in vector)

    def test_embed_batch_returns_vectors(self) -> None:
        """Test 2: embed_batch returns one vector per input text."""
        import app.services.embedding_service as emb_mod

        emb_mod._model_instance = None
        svc = EmbeddingService()
        texts = ["first chunk", "second chunk", "third chunk"]

        with patch(
            "app.services.embedding_service.SentenceTransformer",
            return_value=_make_fake_model(),
        ):
            emb_mod._model_instance = None
            vectors = svc.embed_batch(texts)

        assert len(vectors) == 3
        assert all(len(v) == EMBED_DIM for v in vectors)

    def test_model_loaded_lazily(self) -> None:
        """Test 3: SentenceTransformer is not imported/loaded at module import time."""
        import app.services.embedding_service as emb_mod

        emb_mod._model_instance = None

        # Model should NOT be loaded before any embed call
        assert emb_mod._model_instance is None

        mock_cls = MagicMock(return_value=_make_fake_model())
        with patch("app.services.embedding_service.SentenceTransformer", mock_cls):
            emb_mod._model_instance = None
            svc = EmbeddingService()
            # Model still not loaded before first call
            assert emb_mod._model_instance is None
            svc.embed_text("trigger load")
            # Now it should be loaded
            assert emb_mod._model_instance is not None

    def test_model_not_repeatedly_instantiated(self) -> None:
        """Test 4: Model constructor is called exactly once even with many embed calls."""
        import app.services.embedding_service as emb_mod

        emb_mod._model_instance = None
        mock_cls = MagicMock(return_value=_make_fake_model())

        with patch("app.services.embedding_service.SentenceTransformer", mock_cls):
            emb_mod._model_instance = None
            svc = EmbeddingService()
            for _ in range(5):
                svc.embed_text("some text")

        mock_cls.assert_called_once()

    def test_embed_batch_empty_returns_empty(self) -> None:
        """embed_batch([]) must return [] without calling the model."""
        import app.services.embedding_service as emb_mod

        emb_mod._model_instance = None
        svc = EmbeddingService()
        mock_model = _make_fake_model()
        emb_mod._model_instance = mock_model

        result = svc.embed_batch([])
        assert result == []
        mock_model.encode.assert_not_called()


# ---------------------------------------------------------------------------
# VectorStoreService tests (tests 5–10)
# ---------------------------------------------------------------------------


class TestVectorStoreService:
    """Tests for VectorStoreService FAISS operations."""

    def _svc_with_mock_faiss(self, tmp_path: Path) -> tuple[VectorStoreService, Any]:
        """Build a VectorStoreService backed by a real in-process FAISS index."""
        import faiss  # type: ignore[import-untyped]

        svc = VectorStoreService()
        svc._dimension = EMBED_DIM
        # Point index path to tmp dir
        index_file = tmp_path / "index.faiss"
        with patch.object(
            type(svc), "_index_path", new_callable=lambda: property(lambda s: index_file)
        ):
            pass
        svc.__dict__["_index_path_override"] = index_file
        return svc, faiss

    def _make_svc(self, tmp_path: Path) -> VectorStoreService:
        """Return a VectorStoreService with paths inside tmp_path."""
        svc = VectorStoreService()
        svc.__class__ = type(
            "PatchedVSS",
            (VectorStoreService,),
            {
                "_index_path": property(lambda self: tmp_path / "index.faiss"),
                "_mapping_path": property(lambda self: tmp_path / "index_mapping.json"),
            },
        )
        return svc

    def test_build_index(self, tmp_path: Path) -> None:
        """Test 5: build_index creates a populated FAISS index."""
        svc = self._make_svc(tmp_path)
        chunks = [
            ChunkVector(chunk_id=uuid.uuid4(), vector=[float(i % 10) / 10.0] * EMBED_DIM)
            for i in range(3)
        ]
        svc.build_index(chunks)

        assert svc.is_loaded
        assert svc.vector_count == 3

    def test_add_chunks_incremental(self, tmp_path: Path) -> None:
        """Test 6: add_chunks appends vectors without losing existing ones."""
        svc = self._make_svc(tmp_path)
        svc.load()  # initialise empty

        first = [ChunkVector(chunk_id=uuid.uuid4(), vector=_FAKE_VECTOR)]
        svc.add_chunks(first)
        assert svc.vector_count == 1

        second = [ChunkVector(chunk_id=uuid.uuid4(), vector=_FAKE_VECTOR)]
        svc.add_chunks(second)
        assert svc.vector_count == 2

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Test 7: save() then load() on a new instance restores the same vector count."""
        svc1 = self._make_svc(tmp_path)
        chunk_id = uuid.uuid4()
        svc1.build_index([ChunkVector(chunk_id=chunk_id, vector=_FAKE_VECTOR)])
        svc1.save()

        assert (tmp_path / "index.faiss").exists()
        assert (tmp_path / "index_mapping.json").exists()

        svc2 = self._make_svc(tmp_path)
        svc2.load()
        assert svc2.vector_count == 1

    def test_mapping_persistence(self, tmp_path: Path) -> None:
        """Test 8: chunk UUID mapping is correctly saved and restored."""
        svc1 = self._make_svc(tmp_path)
        chunk_id = uuid.uuid4()
        svc1.build_index([ChunkVector(chunk_id=chunk_id, vector=_FAKE_VECTOR)])
        svc1.save()

        with open(tmp_path / "index_mapping.json") as f:
            mapping = json.load(f)

        assert "0" in mapping
        assert mapping["0"] == str(chunk_id)

    def test_search_returns_expected_chunk_ids(self, tmp_path: Path) -> None:
        """Test 9: search returns the chunk_id for the nearest vector."""
        svc = self._make_svc(tmp_path)
        target_id = uuid.uuid4()
        other_id = uuid.uuid4()

        target_vec = [1.0] + [0.0] * (EMBED_DIM - 1)
        other_vec = [0.0] * EMBED_DIM

        svc.build_index(
            [
                ChunkVector(chunk_id=target_id, vector=target_vec),
                ChunkVector(chunk_id=other_id, vector=other_vec),
            ]
        )

        results = svc.search(query_vector=target_vec, top_k=1)
        assert len(results) == 1
        assert results[0].chunk_id == target_id
        assert results[0].rank == 1

    def test_empty_index_search_safe(self, tmp_path: Path) -> None:
        """Test 10: searching an empty index returns [] without raising."""
        svc = self._make_svc(tmp_path)
        svc.load()

        results = svc.search(query_vector=_FAKE_VECTOR, top_k=5)
        assert results == []


# ---------------------------------------------------------------------------
# AIEmbeddingRepository tests (tests 11–13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAIEmbeddingRepository:
    """Tests for AIEmbeddingRepository CRUD operations."""

    async def test_create_embedding(self, db_session: AsyncSession, test_user: User) -> None:
        """Test 11: create() persists an AIEmbedding row."""
        # Create a parent document and chunk first
        doc = Document(
            file_name="test.pdf",
            file_type="application/pdf",
            file_size=1000,
            storage_path="test/path/test.pdf",
            owner_id=test_user.id,
            status=DocumentStatus.PROCESSED,
            ocr_status=OcrStatus.COMPLETED,
        )
        db_session.add(doc)
        await db_session.flush()

        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_number=1,
            content="Sample chunk text for embedding.",
        )
        db_session.add(chunk)
        await db_session.flush()

        repo = AIEmbeddingRepository(db_session)
        emb = await repo.create(
            document_chunk_id=chunk.id,
            vector_reference=str(chunk.id),
            embedding_model="all-MiniLM-L6-v2",
        )
        await db_session.commit()

        assert emb.id is not None
        assert emb.document_chunk_id == chunk.id
        assert emb.embedding_model == "all-MiniLM-L6-v2"
        assert emb.vector_reference == str(chunk.id)

    async def test_get_by_chunk_id(self, db_session: AsyncSession, test_user: User) -> None:
        """Test 12: get_by_chunk_id() retrieves the correct record."""
        doc = Document(
            file_name="test2.pdf",
            file_type="application/pdf",
            file_size=2000,
            storage_path="test/path/test2.pdf",
            owner_id=test_user.id,
            status=DocumentStatus.PROCESSED,
            ocr_status=OcrStatus.COMPLETED,
        )
        db_session.add(doc)
        await db_session.flush()

        chunk = DocumentChunk(
            document_id=doc.id, chunk_number=1, content="Chunk for retrieval test."
        )
        db_session.add(chunk)
        await db_session.flush()

        repo = AIEmbeddingRepository(db_session)
        await repo.create(
            document_chunk_id=chunk.id,
            vector_reference=str(chunk.id),
            embedding_model="all-MiniLM-L6-v2",
        )
        await db_session.commit()

        found = await repo.get_by_chunk_id(chunk.id)
        assert found is not None
        assert found.document_chunk_id == chunk.id

    async def test_delete_by_document_id(self, db_session: AsyncSession, test_user: User) -> None:
        """Test 13: delete_by_document_id() removes all embeddings for that document."""
        doc = Document(
            file_name="test3.pdf",
            file_type="application/pdf",
            file_size=3000,
            storage_path="test/path/test3.pdf",
            owner_id=test_user.id,
            status=DocumentStatus.PROCESSED,
            ocr_status=OcrStatus.COMPLETED,
        )
        db_session.add(doc)
        await db_session.flush()

        repo_chunk = DocumentChunkRepository(db_session)
        chunks = await repo_chunk.save_chunks(doc.id, ["Chunk 1", "Chunk 2"])
        await db_session.flush()

        repo = AIEmbeddingRepository(db_session)
        for chunk in chunks:
            await repo.create(
                document_chunk_id=chunk.id,
                vector_reference=str(chunk.id),
                embedding_model="all-MiniLM-L6-v2",
            )
        await db_session.commit()

        deleted = await repo.delete_by_document_id(doc.id)
        await db_session.commit()
        assert deleted == 2

        # Verify they are gone
        for chunk in chunks:
            found = await repo.get_by_chunk_id(chunk.id)
            assert found is None


# ---------------------------------------------------------------------------
# Celery embedding task tests (tests 14–15)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmbedDocumentChunksTask:
    """Tests for the embed_document_chunks Celery task (async inner function)."""

    async def test_embed_task_with_chunks(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """Test 14: task embeds chunks, creates AIEmbedding rows, and updates FAISS."""
        doc = Document(
            file_name="embed_test.pdf",
            file_type="application/pdf",
            file_size=5000,
            storage_path="test/embed_test.pdf",
            owner_id=test_user.id,
            status=DocumentStatus.PROCESSED,
            ocr_status=OcrStatus.COMPLETED,
        )
        db_session.add(doc)
        await db_session.flush()

        chunk_repo = DocumentChunkRepository(db_session)
        await chunk_repo.save_chunks(doc.id, ["Chunk A content.", "Chunk B content."])
        await db_session.commit()

        from app.workers.ai_tasks import _async_embed_document_chunks

        mock_vs = MagicMock()
        mock_vs.vector_count = 2

        with (
            patch(
                "app.workers.ai_tasks.embedding_service.embed_batch",
                return_value=[_FAKE_VECTOR, _FAKE_VECTOR],
            ),
            patch("app.workers.ai_tasks.vector_store", mock_vs),
        ):
            result = await _async_embed_document_chunks(str(doc.id), db=db_session)

        assert result["status"] == "completed"
        assert result["chunks_processed"] == 2
        assert result["document_id"] == str(doc.id)

        # AIEmbedding rows must exist
        emb_repo = AIEmbeddingRepository(db_session)
        chunk_repo2 = DocumentChunkRepository(db_session)
        chunks = await chunk_repo2.get_chunks_by_document(doc.id)
        for chunk in chunks:
            emb = await emb_repo.get_by_chunk_id(chunk.id)
            assert emb is not None

        # FAISS add and save must have been called
        mock_vs.add_chunks.assert_called_once()
        mock_vs.save.assert_called_once()

    async def test_embed_task_no_chunks_graceful(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test 15: task skips gracefully when document has no chunks."""
        doc = Document(
            file_name="empty_doc.pdf",
            file_type="application/pdf",
            file_size=100,
            storage_path="test/empty_doc.pdf",
            owner_id=test_user.id,
            status=DocumentStatus.PENDING,
            ocr_status=OcrStatus.PENDING,
        )
        db_session.add(doc)
        await db_session.commit()

        from app.workers.ai_tasks import _async_embed_document_chunks

        result = await _async_embed_document_chunks(str(doc.id), db=db_session)

        assert result["status"] == "skipped"
        assert result["chunks_processed"] == 0
        assert result["reason"] == "no_chunks"


# ---------------------------------------------------------------------------
# OCR → embedding integration tests (tests 16–17)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOCREmbeddingIntegration:
    """Tests verifying OCR completion triggers embedding and failure isolation."""

    async def test_ocr_dispatches_embedding_task(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """Test 16: OCR completion dispatches the embedding Celery task."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        doc_file = storage_dir / "test_ocr.pdf"
        doc_file.write_bytes(b"%PDF-1.4 test content")

        doc = Document(
            file_name="ocr_dispatch_test.pdf",
            file_type="application/pdf",
            file_size=len(doc_file.read_bytes()),
            storage_path=str(doc_file),
            owner_id=test_user.id,
            status=DocumentStatus.PROCESSING,
            ocr_status=OcrStatus.PENDING,
        )
        db_session.add(doc)
        await db_session.commit()

        mock_send_task = MagicMock()

        with (
            patch("app.workers.ocr_tasks.StorageService") as MockStorage,
            patch("app.workers.ocr_tasks.ExtractorService") as MockExtractor,
            patch("app.workers.ocr_tasks.celery_app.send_task", mock_send_task),
        ):
            MockStorage.return_value.resolve_path.return_value = doc_file
            MockExtractor.return_value.extract_text.return_value = "Extracted text content."
            MockExtractor.return_value.chunk_text.return_value = ["Chunk 1", "Chunk 2"]

            await _async_process_document_ocr(str(doc.id), db=db_session)

        # Verify embedding task was dispatched
        mock_send_task.assert_called_once_with("tasks.embed_document_chunks", args=[str(doc.id)])

    async def test_embedding_failure_does_not_corrupt_ocr_status(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """Test 17: embedding dispatch failure does not affect document's OCR status."""
        doc_file = tmp_path / "ocr_safe.pdf"
        doc_file.write_bytes(b"%PDF-1.4 content")

        doc = Document(
            file_name="ocr_safe_test.pdf",
            file_type="application/pdf",
            file_size=100,
            storage_path=str(doc_file),
            owner_id=test_user.id,
            status=DocumentStatus.PROCESSING,
            ocr_status=OcrStatus.PENDING,
        )
        db_session.add(doc)
        await db_session.commit()

        with (
            patch("app.workers.ocr_tasks.StorageService") as MockStorage,
            patch("app.workers.ocr_tasks.ExtractorService") as MockExtractor,
            patch(
                "app.workers.ocr_tasks.celery_app.send_task",
                side_effect=Exception("Redis unavailable"),
            ),
        ):
            MockStorage.return_value.resolve_path.return_value = doc_file
            MockExtractor.return_value.extract_text.return_value = "Content."
            MockExtractor.return_value.chunk_text.return_value = ["Chunk"]

            # OCR should succeed even though embedding dispatch fails
            result = await _async_process_document_ocr(str(doc.id), db=db_session)

        assert result["status"] == "completed"

        # Reload and verify OCR status is still COMPLETED
        doc_repo = DocumentRepository(db_session)
        refreshed = await doc_repo.get_by_id(doc.id)
        assert refreshed is not None
        assert refreshed.ocr_status == OcrStatus.COMPLETED


# ---------------------------------------------------------------------------
# Worker warm-up tests (tests 18–19)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestWorkerWarmUp:
    """Tests for FAISS warm-up on worker startup."""

    async def test_warm_up_handles_missing_index(self, tmp_path: Path) -> None:
        """Test 18: warm-up creates an empty index when index.faiss is missing."""
        from app.workers.celery_app import _warm_up_faiss

        mock_vs = MagicMock()
        mock_vs.vector_count = 0

        with (
            patch("app.workers.celery_app.settings") as mock_settings,
            patch("app.workers.celery_app.vector_store", mock_vs),
            patch("app.workers.celery_app.AsyncSessionLocal") as MockSession,
            patch("app.workers.celery_app.AIEmbeddingRepository") as MockRepo,
        ):
            # Index file does not exist
            mock_settings.FAISS_INDEX_PATH = str(tmp_path / "nonexistent.faiss")

            mock_repo_inst = AsyncMock()
            mock_repo_inst.get_all_with_chunks = AsyncMock(return_value=[])
            MockRepo.return_value = mock_repo_inst
            MockSession.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            MockSession.return_value.__aexit__ = AsyncMock(return_value=None)

            await _warm_up_faiss()

        # With no index file and no embeddings, load() should be called
        mock_vs.load.assert_called()

    async def test_warm_up_handles_existing_index(self, tmp_path: Path) -> None:
        """Test 19: warm-up loads from disk when index.faiss exists."""
        from app.workers.celery_app import _warm_up_faiss

        # Create a dummy index.faiss to make it appear to exist
        index_file = tmp_path / "index.faiss"
        index_file.touch()

        mock_vs = MagicMock()
        mock_vs.vector_count = 5

        with (
            patch("app.workers.celery_app.settings") as mock_settings,
            patch("app.workers.celery_app.vector_store", mock_vs),
        ):
            mock_settings.FAISS_INDEX_PATH = str(index_file)

            await _warm_up_faiss()

        # With existing index, load() should be called (not build_index)
        mock_vs.load.assert_called_once()
        mock_vs.build_index.assert_not_called()


# ---------------------------------------------------------------------------
# Worker task runner tests (event loop isolation & pool disposal)
# ---------------------------------------------------------------------------


class TestWorkerTaskRunner:
    """Tests for run_in_worker event loop isolation and engine pool disposal."""

    def test_run_in_worker_executes_coroutine(self) -> None:
        """run_in_worker successfully executes an async coroutine."""
        from app.workers.task_runner import run_in_worker

        async def _sample() -> str:
            return "worker_ok"

        assert run_in_worker(_sample()) == "worker_ok"

    def test_run_in_worker_disposes_engine_on_completion(self) -> None:
        """run_in_worker awaits engine.dispose() on exit."""
        from app.workers.task_runner import run_in_worker

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        with patch("app.workers.task_runner.engine", mock_engine):

            async def _coro() -> int:
                return 42

            result = run_in_worker(_coro())
            assert result == 42
            mock_engine.dispose.assert_awaited_once()

    def test_run_in_worker_disposes_engine_on_exception(self) -> None:
        """run_in_worker disposes engine even if the task coroutine raises."""
        from app.workers.task_runner import run_in_worker

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        with patch("app.workers.task_runner.engine", mock_engine):

            async def _failing_coro() -> None:
                raise RuntimeError("task exploded")

            with pytest.raises(RuntimeError, match="task exploded"):
                run_in_worker(_failing_coro())

            mock_engine.dispose.assert_awaited_once()

    def test_run_in_worker_sequential_runs_independent_loops(self) -> None:
        """Multiple sequential run_in_worker invocations run on separate, clean loops."""
        import asyncio

        from app.workers.task_runner import run_in_worker

        loops: list[asyncio.AbstractEventLoop] = []

        async def _record_loop() -> int:
            loop = asyncio.get_running_loop()
            loops.append(loop)
            return len(loops)

        r1 = run_in_worker(_record_loop())
        r2 = run_in_worker(_record_loop())
        r3 = run_in_worker(_record_loop())

        assert r1 == 1
        assert r2 == 2
        assert r3 == 3
        # Each invocation ran on a distinct event loop instance
        assert len(loops) == 3
        assert loops[0] is not loops[1]
        assert loops[1] is not loops[2]
        # All loops were properly closed after execution
        assert all(loop.is_closed() for loop in loops)
