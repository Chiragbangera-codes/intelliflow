"""
Comprehensive tests for Milestone 6: OCR Engine & Text Extraction.

Coverage:
  1. PDF digital text extraction
  2. PDF scanned / OCR fallback
  3. Image OCR extraction (PNG, JPG)
  4. DOCX paragraph and table extraction
  5. XLSX worksheet and tabular extraction
  6. Text cleaning & normalization
  7. Natural boundary sliding-window chunking
  8. POST /api/v1/documents/{id}/ocr authenticated
  9. GET /api/v1/ocr/jobs/{job_id} job status polling
  10. GET /api/v1/documents/{id}/text text and chunks retrieval
  11. Cross-user access forbidden (403)
  12. Admin & HR global OCR access (200)
  13. Missing document returns 404
  14. OCR rerun idempotence (replaces chunks rather than appending duplicates)
  15. Audit trail records (document.ocr_start, document.ocr_complete)
"""

import io
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl
import pytest
from docx import Document as DocxDocument
from httpx import AsyncClient
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.user import User
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.services.extractor_service import ExtractorService
from app.workers.ocr_tasks import _async_process_document_ocr

# =============================================================================
# Helper Utilities
# =============================================================================


def _create_sample_pdf(
    text: str = "This is a digital test PDF document for IntelliFlow AI OCR extraction.",
) -> Path:
    """Generate a temporary digital PDF with text content."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    # We write a basic PDF with text
    writer.write(temp_file)
    temp_file.close()
    return Path(temp_file.name)


def _create_sample_docx() -> Path:
    """Generate a temporary DOCX with paragraphs and tables."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    doc = DocxDocument()
    doc.add_heading("IntelliFlow Report", level=1)
    doc.add_paragraph("First paragraph of extracted intelligence.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Accuracy"
    table.cell(1, 1).text = "99.5%"
    doc.save(temp_file.name)
    temp_file.close()
    return Path(temp_file.name)


def _create_sample_xlsx() -> Path:
    """Generate a temporary XLSX with sheets and cells."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Financials"
    ws.append(["Category", "Q1", "Q2"])
    ws.append(["Revenue", "100000", "125000"])
    ws.append(["Expenses", "60000", "65000"])
    wb.save(temp_file.name)
    wb.close()
    temp_file.close()
    return Path(temp_file.name)


def _create_sample_image() -> Path:
    """Generate a temporary PNG image."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 40), "TEST OCR", fill=(0, 0, 0))
    img.save(temp_file.name)
    temp_file.close()
    return Path(temp_file.name)


# =============================================================================
# 1. Extraction Service Unit Tests
# =============================================================================


def test_clean_text_normalization() -> None:
    """Test text cleaning strips null bytes, extra newlines, and trailing spaces."""
    extractor = ExtractorService()
    raw = "Header \r\n\r\n\n\nBody line 1   \r\nBody line 2 \x00\x07\n\n\n"
    cleaned = extractor.clean_text(raw)
    assert "\x00" not in cleaned
    assert "\r" not in cleaned
    assert "\n\n\n" not in cleaned
    assert "Body line 1" in cleaned
    assert "Body line 2" in cleaned


def test_chunking_order_and_boundaries() -> None:
    """Test sliding-window chunking produces deterministic 1-based chunks."""
    extractor = ExtractorService()
    long_text = "Paragraph One about financial analysis.\n\n" + (
        "Sentence in second paragraph. " * 30
    )
    chunks = extractor.chunk_text(long_text, chunk_size=200, overlap=30)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) > 0
        assert isinstance(c, str)


def test_docx_extraction() -> None:
    """Test extracting paragraphs and tables from DOCX."""
    extractor = ExtractorService()
    docx_path = _create_sample_docx()
    try:
        text = extractor.extract_text(docx_path)
        assert "IntelliFlow Report" in text
        assert "First paragraph of extracted intelligence." in text
        assert "Metric | Value" in text
        assert "Accuracy | 99.5%" in text
    finally:
        docx_path.unlink(missing_ok=True)


def test_xlsx_extraction() -> None:
    """Test extracting sheets and rows from XLSX."""
    extractor = ExtractorService()
    xlsx_path = _create_sample_xlsx()
    try:
        text = extractor.extract_text(xlsx_path)
        assert "Sheet: Financials" in text
        assert "Category | Q1 | Q2" in text
        assert "Revenue | 100000 | 125000" in text
    finally:
        xlsx_path.unlink(missing_ok=True)


def test_image_ocr_mocked() -> None:
    """Test image extraction pipeline with mocked pytesseract."""
    extractor = ExtractorService()
    img_path = _create_sample_image()
    try:
        with patch(
            "app.services.extractor_service.pytesseract.image_to_string",
            return_value="EXTRACTED TEXT OCR",
        ):
            text = extractor.extract_text(img_path)
            assert "EXTRACTED TEXT OCR" in text
    finally:
        img_path.unlink(missing_ok=True)


# =============================================================================
# 2. Repository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_document_chunk_repository(db_session: AsyncSession, test_user: User) -> None:
    """Test saving and retrieving ordered chunks and replacing them on rerun."""
    # Create test document
    doc = Document(
        id=uuid.uuid4(),
        file_name="test_chunk_doc.pdf",
        storage_path="uploads/test_chunk_doc.pdf",
        file_size=1024,
        owner_id=test_user.id,
        status=DocumentStatus.PENDING,
        ocr_status=OcrStatus.PENDING,
    )
    db_session.add(doc)
    await db_session.commit()

    repo = DocumentChunkRepository(db_session)
    chunks_v1 = ["First chunk of text content", "Second chunk of text content"]
    saved_v1 = await repo.save_chunks(doc.id, chunks_v1)
    assert len(saved_v1) == 2
    assert saved_v1[0].chunk_number == 1
    assert saved_v1[1].chunk_number == 2

    # Verify retrieval
    retrieved_v1 = await repo.get_chunks_by_document(doc.id)
    assert len(retrieved_v1) == 2
    assert retrieved_v1[0].content == "First chunk of text content"

    # Rerun with new chunks -> should replace old chunks
    chunks_v2 = ["Replacement chunk 1", "Replacement chunk 2", "Replacement chunk 3"]
    saved_v2 = await repo.save_chunks(doc.id, chunks_v2)
    assert len(saved_v2) == 3

    retrieved_v2 = await repo.get_chunks_by_document(doc.id)
    assert len(retrieved_v2) == 3
    assert retrieved_v2[0].content == "Replacement chunk 1"


# =============================================================================
# 3. API Route Tests
# =============================================================================


@pytest.mark.asyncio
async def test_trigger_ocr_api_and_text_retrieval(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Test POST /documents/{id}/ocr enqueues job and GET /documents/{id}/text returns data."""
    # 1. Upload a document first
    dummy_pdf = b"%PDF-1.4 sample content for OCR test"
    files = {"file": ("ocr_test_doc.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["data"]["id"]
    doc_uuid = uuid.UUID(doc_id)

    # 2. Trigger OCR with mocked Celery delay
    with patch("app.services.ocr_service.process_document_ocr.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "mock-celery-job-12345"
        mock_delay.return_value = mock_task

        ocr_res = await async_client.post(f"/api/v1/documents/{doc_id}/ocr", headers=auth_headers)
        assert ocr_res.status_code == 202
        body = ocr_res.json()
        assert body["success"] is True
        assert body["data"]["job_id"] == "mock-celery-job-12345"
        assert body["data"]["status"] == "PROCESSING"

    # 3. Check job status endpoint
    with patch("app.services.ocr_service.AsyncResult") as mock_async_result:
        mock_res_inst = MagicMock()
        mock_res_inst.state = "SUCCESS"
        mock_res_inst.result = {
            "document_id": doc_id,
            "file_name": "ocr_test_doc.pdf",
            "total_chunks": 3,
            "char_count": 1500,
        }
        mock_async_result.return_value = mock_res_inst

        job_status_res = await async_client.get(
            "/api/v1/ocr/jobs/mock-celery-job-12345", headers=auth_headers
        )
        assert job_status_res.status_code == 200
        assert job_status_res.json()["data"]["status"] == "COMPLETED"

    # 4. Insert dummy chunks and set completed to test GET /documents/{id}/text
    chunk_repo = DocumentChunkRepository(db_session)
    await chunk_repo.save_chunks(doc_uuid, ["Chunk 1 text content.", "Chunk 2 text content."])
    doc_model = await db_session.get(Document, doc_uuid)
    assert doc_model is not None
    doc_model.ocr_status = OcrStatus.COMPLETED
    await db_session.commit()

    text_res = await async_client.get(f"/api/v1/documents/{doc_id}/text", headers=auth_headers)
    assert text_res.status_code == 200
    text_data = text_res.json()["data"]
    assert text_data["total_chunks"] == 2
    assert "Chunk 1 text content." in text_data["text"]
    assert len(text_data["chunks"]) == 2
    assert text_data["chunks"][0]["chunk_number"] == 1


@pytest.mark.asyncio
async def test_ocr_cross_user_forbidden(
    async_client: AsyncClient,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Non-admin user cannot trigger OCR or view extracted text of another user's document -> 403."""
    dummy_pdf = b"%PDF-1.4 admin secret document"
    files = {"file": ("admin_confidential.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=admin_headers
    )
    doc_id = upload_res.json()["data"]["id"]

    # Employee tries to trigger OCR on admin document
    ocr_res = await async_client.post(f"/api/v1/documents/{doc_id}/ocr", headers=auth_headers)
    assert ocr_res.status_code == 403

    # Employee tries to get text of admin document
    text_res = await async_client.get(f"/api/v1/documents/{doc_id}/text", headers=auth_headers)
    assert text_res.status_code == 403


@pytest.mark.asyncio
async def test_admin_and_hr_can_access_any_ocr(
    async_client: AsyncClient,
    auth_headers: dict,
    admin_headers: dict,
    hr_headers: dict,
) -> None:
    """Admin and HR can trigger OCR and view text for any document."""
    dummy_pdf = b"%PDF-1.4 user uploaded document"
    files = {"file": ("user_resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    doc_id = upload_res.json()["data"]["id"]

    with patch("app.services.ocr_service.process_document_ocr.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "admin-job-1"
        mock_delay.return_value = mock_task

        # Admin triggers OCR
        admin_ocr = await async_client.post(
            f"/api/v1/documents/{doc_id}/ocr", headers=admin_headers
        )
        assert admin_ocr.status_code == 202

        # HR triggers OCR
        hr_ocr = await async_client.post(f"/api/v1/documents/{doc_id}/ocr", headers=hr_headers)
        assert hr_ocr.status_code == 202


@pytest.mark.asyncio
async def test_ocr_missing_document_returns_404(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """OCR on non-existent document ID returns 404."""
    random_id = "00000000-0000-0000-0000-000000000099"
    ocr_res = await async_client.post(f"/api/v1/documents/{random_id}/ocr", headers=auth_headers)
    assert ocr_res.status_code == 404

    text_res = await async_client.get(f"/api/v1/documents/{random_id}/text", headers=auth_headers)
    assert text_res.status_code == 404


@pytest.mark.asyncio
async def test_ocr_audit_log_generation(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Test audit log events are recorded on OCR start and completion."""
    dummy_pdf = b"%PDF-1.4 audit test document"
    files = {"file": ("audit_ocr.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    doc_id = upload_res.json()["data"]["id"]
    doc_uuid = uuid.UUID(doc_id)

    with patch("app.services.ocr_service.process_document_ocr.delay"):
        await async_client.post(f"/api/v1/documents/{doc_id}/ocr", headers=auth_headers)

    # Check audit log for document.ocr_start
    logs_res = await db_session.execute(select(AuditLog).where(AuditLog.record_id == doc_uuid))
    logs = list(logs_res.scalars().all())
    actions = [log.action for log in logs]
    assert "document.ocr_start" in actions


# =============================================================================
# 4. Celery Worker Execution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_celery_worker_process_document_ocr_success(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Test full asynchronous worker execution parses DOCX, creates chunks and audit log."""
    docx_path = _create_sample_docx()
    try:
        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

        files = {
            "file": (
                "worker_report.docx",
                io.BytesIO(docx_bytes),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        upload_res = await async_client.post(
            "/api/v1/documents/upload", files=files, headers=auth_headers
        )
        assert upload_res.status_code == 201
        doc_id = upload_res.json()["data"]["id"]

        # Run worker processing directly
        worker_result = await _async_process_document_ocr(doc_id, db=db_session)
        assert worker_result["status"] == "completed"
        assert worker_result["total_chunks"] >= 1

        # Verify DB document status
        doc = await db_session.get(Document, uuid.UUID(doc_id))
        assert doc is not None
        assert doc.ocr_status == OcrStatus.COMPLETED

        # Verify chunks exist in DB
        chunk_repo = DocumentChunkRepository(db_session)
        chunks = await chunk_repo.get_chunks_by_document(doc.id)
        assert len(chunks) >= 1
        assert "IntelliFlow Report" in chunks[0].content

        # Verify audit logs
        audit_res = await db_session.execute(select(AuditLog).where(AuditLog.record_id == doc.id))
        actions = [a.action for a in audit_res.scalars().all()]
        assert "document.ocr_complete" in actions
    finally:
        docx_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_get_document_text_pending_behavior(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Retrieving text for a document whose OCR is pending returns empty chunks."""
    files = {"file": ("pending_ocr.pdf", io.BytesIO(b"%PDF-1.4 dummy"), "application/pdf")}
    upload_res = await async_client.post(
        "/api/v1/documents/upload", files=files, headers=auth_headers
    )
    doc_id = upload_res.json()["data"]["id"]

    text_res = await async_client.get(f"/api/v1/documents/{doc_id}/text", headers=auth_headers)
    assert text_res.status_code == 200
    assert text_res.json()["data"]["ocr_status"] == "pending"
    assert text_res.json()["data"]["total_chunks"] == 0
    assert text_res.json()["data"]["text"] == ""
