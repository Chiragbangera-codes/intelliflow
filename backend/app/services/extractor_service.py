"""
Document text extraction and chunking service.

Supports format-specific text extraction:
  - PDF: Digital text extraction with Tesseract OCR fallback for scanned pages
  - Images (PNG, JPG, JPEG): Optical character recognition via Tesseract
  - DOCX: Paragraphs and structured table extraction via python-docx
  - XLSX: Multi-worksheet cell extraction via openpyxl

Includes text normalization and natural-boundary sliding-window chunking.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import docx
import openpyxl
import pdf2image
import pypdf
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


class ExtractorService:
    """Handles text extraction across supported file formats and logical chunking."""

    DEFAULT_CHUNK_SIZE = 800
    DEFAULT_OVERLAP = 100

    # =========================================================================
    # High-level dispatch
    # =========================================================================

    def extract_text(
        self,
        file_path: Path | str,
        file_name: str | None = None,
        file_type: str | None = None,
    ) -> str:
        """
        Extract readable cleaned text from a document based on its extension or MIME type.

        Args:
            file_path: Path to the target physical file.
            file_name: Optional original filename to resolve extension.
            file_type: Optional MIME type.

        Returns:
            Cleaned and normalized text string.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found on disk: {path}")

        name = file_name or path.name
        ext = Path(name).suffix.lower()

        logger.info("Starting text extraction for %s (ext: %s)", path.name, ext)

        raw_text = ""
        if ext == ".pdf" or (file_type and "pdf" in file_type):
            raw_text = self._extract_from_pdf(path)
        elif ext in {".png", ".jpg", ".jpeg"} or (file_type and "image" in file_type):
            raw_text = self._extract_from_image(path)
        elif ext == ".docx" or (file_type and "word" in file_type):
            raw_text = self._extract_from_docx(path)
        elif ext == ".xlsx" or (file_type and ("sheet" in file_type or "excel" in file_type)):
            raw_text = self._extract_from_xlsx(path)
        else:
            logger.warning("Unsupported file type for extraction: %s", ext)
            raw_text = ""

        cleaned = self.clean_text(raw_text)
        logger.info("Extracted %d characters from %s", len(cleaned), name)
        return cleaned

    # =========================================================================
    # Format-specific extractors
    # =========================================================================

    def _extract_from_pdf(self, path: Path) -> str:
        """
        Extract text from PDF pages. Uses direct digital text extraction first.
        If a page has no digital text, falls back to OCR on rendered page image.
        """
        extracted_pages: list[str] = []
        try:
            reader = pypdf.PdfReader(str(path))
            for page_idx, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                if len(page_text.strip()) >= 20:
                    extracted_pages.append(page_text.strip())
                else:
                    # Attempt OCR fallback on scanned page
                    logger.info(
                        "Page %d of %s has minimal digital text; running OCR fallback",
                        page_idx,
                        path.name,
                    )
                    ocr_page_text = self._ocr_pdf_page(path, page_idx)
                    if ocr_page_text.strip():
                        extracted_pages.append(ocr_page_text.strip())
                    elif page_text.strip():
                        extracted_pages.append(page_text.strip())
        except Exception as exc:
            logger.error(
                "Error during PDF digital extraction on %s: %s; falling back to full OCR",
                path.name,
                exc,
            )
            # Full OCR fallback
            try:
                images = pdf2image.convert_from_path(str(path), dpi=200)
                for img in images:
                    page_text = pytesseract.image_to_string(img)
                    if page_text.strip():
                        extracted_pages.append(page_text.strip())
            except Exception as ocr_exc:
                logger.error("PDF OCR conversion failed on %s: %s", path.name, ocr_exc)

        return "\n\n".join(extracted_pages)

    def _ocr_pdf_page(self, path: Path, page_number: int) -> str:
        """Render a single PDF page to an image and run Tesseract OCR."""
        try:
            images = pdf2image.convert_from_path(
                str(path),
                dpi=200,
                first_page=page_number,
                last_page=page_number,
            )
            if images:
                return str(pytesseract.image_to_string(images[0]))
        except Exception as exc:
            logger.warning(
                "Single page OCR failed for page %d of %s: %s", page_number, path.name, exc
            )
        return ""

    def _extract_from_image(self, path: Path) -> str:
        """Extract text from an image file using Pillow and Tesseract OCR."""
        try:
            with Image.open(path) as opened_img:
                # Convert RGBA/palette images to RGB for tesseract compatibility
                processed: Image.Image = (
                    opened_img.convert("RGB")
                    if opened_img.mode in ("RGBA", "P", "LA")
                    else opened_img
                )
                return str(pytesseract.image_to_string(processed))
        except Exception as exc:
            logger.error("Tesseract OCR extraction failed on image %s: %s", path.name, exc)
            return ""

    def _extract_from_docx(self, path: Path) -> str:
        """Extract paragraphs and table contents from a DOCX document."""
        try:
            doc = docx.Document(str(path))
            parts: list[str] = []

            # Extract paragraphs
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    parts.append(text)

            # Extract tables in structured format
            for table in doc.tables:
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells:
                        parts.append(" | ".join(row_cells))

            return "\n\n".join(parts)
        except Exception as exc:
            logger.error("DOCX extraction failed on %s: %s", path.name, exc)
            return ""

    def _extract_from_xlsx(self, path: Path) -> str:
        """Extract worksheet names and tabular row data from an Excel workbook."""
        try:
            wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
            parts: list[str] = []

            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                parts.append(f"--- Sheet: {sheet_name} ---")

                for row in sheet.iter_rows(values_only=True):
                    # Filter empty rows
                    cells: list[str] = []
                    for val in row:
                        if val is not None:
                            cells.append(str(val).strip())
                        else:
                            cells.append("")

                    # Only append row if it has at least one non-empty value
                    if any(cells):
                        parts.append(" | ".join(cells))

            wb.close()
            return "\n".join(parts)
        except Exception as exc:
            logger.error("XLSX extraction failed on %s: %s", path.name, exc)
            return ""

    # =========================================================================
    # Text Cleaning & Normalization
    # =========================================================================

    def clean_text(self, text: str) -> str:
        """
        Normalize whitespace, linebreaks, and remove unwanted control characters.
        Preserves intentional paragraph and table row boundaries.
        """
        if not text:
            return ""

        # Remove null characters and non-printable control chars except \n, \r, \t
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

        # Normalize carriage returns
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        # Strip trailing spaces on lines
        lines = [line.strip() for line in cleaned.split("\n")]

        # Collapse more than two consecutive newlines into double newlines
        rebuilt = "\n".join(lines)
        rebuilt = re.sub(r"\n{3,}", "\n\n", rebuilt)

        return rebuilt.strip()

    # =========================================================================
    # Sliding-Window Chunking
    # =========================================================================

    def chunk_text(
        self,
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> list[str]:
        """
        Split normalized text into ordered, overlapping chunks along natural boundaries.

        Target chunk size is ~800 characters with ~100 characters overlap.
        Natural split precedence:
          1. Paragraph boundaries (\n\n)
          2. Sentence boundaries (. / ! / ?)
          3. Line boundaries (\n)
          4. Whitespace (space)
          5. Hard boundary fallback

        Returns:
            List of non-empty text strings.
        """
        cleaned = self.clean_text(text)
        if not cleaned:
            return []

        if len(cleaned) <= chunk_size:
            return [cleaned]

        chunks: list[str] = []
        start = 0
        text_length = len(cleaned)

        while start < text_length:
            end = min(start + chunk_size, text_length)

            if end < text_length:
                # Look for natural boundary near target end within the overlap zone
                search_start = max(start + chunk_size - overlap, start + (chunk_size // 2))
                window = cleaned[search_start:end]

                # 1. Paragraph break
                para_pos = window.rfind("\n\n")
                if para_pos != -1:
                    end = search_start + para_pos + 2
                else:
                    # 2. Sentence boundary (. / ! / ? followed by space or newline)
                    sent_match = None
                    for match in re.finditer(r"[.!?](\s|\n)", window):
                        sent_match = match
                    if sent_match:
                        end = search_start + sent_match.end()
                    else:
                        # 3. Line break
                        line_pos = window.rfind("\n")
                        if line_pos != -1:
                            end = search_start + line_pos + 1
                        else:
                            # 4. Word boundary
                            space_pos = window.rfind(" ")
                            if space_pos != -1:
                                end = search_start + space_pos + 1

            chunk = cleaned[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= text_length:
                break

            # Advance start by taking overlap into account
            start = max(end - overlap, start + 1)

        return chunks
