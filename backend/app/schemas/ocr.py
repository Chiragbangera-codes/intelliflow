"""
Pydantic schemas for OCR jobs, status tracking, and extracted document text.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentChunkResponse(BaseModel):
    """Single extracted text chunk response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_number: int
    content: str
    created_at: datetime


class DocumentTextResponse(BaseModel):
    """Full aggregated extracted text and chunk breakdown for a document."""

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    file_name: str
    ocr_status: str
    total_chunks: int
    text: str
    chunks: list[DocumentChunkResponse] = Field(default_factory=list)


class OCRJobData(BaseModel):
    """Data payload returned when an OCR task is initiated."""

    job_id: str
    document_id: uuid.UUID
    status: str


class OCRStatusData(BaseModel):
    """Data payload returned when polling an OCR job status."""

    job_id: str
    status: str
    result: dict[str, Any] | None = None
