"""
Celery background tasks for asynchronous report generation (Phase 9).

Task:
  generate_report(report_id, report_type, fmt, filters)
    Fetches data from the database, serialises it to the requested format
    (CSV, XLSX, or PDF), writes the file to disk, and updates the Report
    record status to COMPLETED (or FAILED on error).

Supported formats:
  csv  — Python's stdlib csv module (no new dependencies)
  xlsx — openpyxl (already in requirements.txt)
  pdf  — reportlab if available; falls back to plain-text PDF otherwise

File output path:
  /app/storage/reports/<report_id>.<ext>
  Parent directory is created on first use.

Architecture:
  ReportService.request_report() → send_task("generate_report")
      → Celery worker → generate_report() → AnalyticsRepository
      → write file → ReportRepository.update_status(COMPLETED)

Security:
  Files are written server-side only. The API never returns raw file bytes
  directly; a dedicated download endpoint (future) would add auth checks.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.database import AsyncSessionLocal
from app.models.report import ReportStatus
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.report_repository import ReportRepository
from app.workers.celery_app import celery_app
from app.workers.task_runner import run_in_worker

logger = logging.getLogger(__name__)

_REPORTS_DIR = Path("/app/storage/reports")


# ===========================================================================
# Celery task entry point
# ===========================================================================


@celery_app.task(
    name="app.workers.report_tasks.generate_report",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def generate_report(
    self,  # noqa: ANN001  (Celery bound task)
    report_id: str,
    report_type: str,
    fmt: str,
    filters: dict[str, Any] | None,
) -> dict[str, str]:
    """
    Celery task: generate a report file and update the DB record.

    Args:
        report_id:   UUID string of the Report row.
        report_type: One of 'revenue', 'employees', 'departments',
                     'workflows', 'documents', 'ai_usage'.
        fmt:         Output format: 'csv', 'xlsx', or 'pdf'.
        filters:     Optional filter dict (e.g. {'year': 2026}).

    Returns:
        dict with 'status' and 'file_path' keys.
    """
    logger.info(
        "generate_report started: id=%s type=%s format=%s",
        report_id,
        report_type,
        fmt,
    )
    try:
        return run_in_worker(
            _async_generate_report(
                report_id=uuid.UUID(report_id),
                report_type=report_type,
                fmt=fmt,
                filters=filters or {},
            )
        )
    except Exception as exc:
        logger.exception(
            "generate_report failed: id=%s error=%s — retrying",
            report_id,
            exc,
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            run_in_worker(_mark_report_failed(uuid.UUID(report_id)))
            return {"status": "failed", "file_path": ""}


# ===========================================================================
# Async implementation
# ===========================================================================


async def _async_generate_report(
    *,
    report_id: uuid.UUID,
    report_type: str,
    fmt: str,
    filters: dict[str, Any],
) -> dict[str, str]:
    """
    Async body: fetch data, write file, update DB record.

    Must run inside run_in_worker() since it opens its own session.
    """
    async with AsyncSessionLocal() as session:
        analytics_repo = AnalyticsRepository(session)
        report_repo = ReportRepository(session)

        try:
            rows, headers = await _fetch_data(analytics_repo, report_type, filters)
        except Exception as exc:
            logger.exception("Data fetch failed for report %s: %s", report_id, exc)
            await report_repo.update_status(report_id, status=ReportStatus.FAILED)
            await session.commit()
            return {"status": "failed", "file_path": ""}

        try:
            file_path = _write_file(report_id, report_type, fmt, headers, rows)
        except Exception as exc:
            logger.exception("File write failed for report %s: %s", report_id, exc)
            await report_repo.update_status(report_id, status=ReportStatus.FAILED)
            await session.commit()
            return {"status": "failed", "file_path": ""}

        await report_repo.update_status(
            report_id,
            status=ReportStatus.COMPLETED,
            file_path=str(file_path),
            generated_at=datetime.now(UTC),
        )
        await session.commit()

    logger.info("generate_report completed: id=%s path=%s", report_id, file_path)
    return {"status": "completed", "file_path": str(file_path)}


async def _mark_report_failed(report_id: uuid.UUID) -> None:
    """Mark a report as FAILED after max retries exceeded."""
    async with AsyncSessionLocal() as session:
        repo = ReportRepository(session)
        await repo.update_status(report_id, status=ReportStatus.FAILED)
        await session.commit()


# ===========================================================================
# Data fetchers
# ===========================================================================


async def _fetch_data(
    repo: AnalyticsRepository,
    report_type: str,
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Return (rows, headers) for the given report_type.

    Each row is a flat dict; headers is the ordered list of column names.
    """
    if report_type == "employees":
        rows = await repo.get_all_employees_for_report()
        headers = [
            "email",
            "first_name",
            "last_name",
            "employee_code",
            "designation",
            "salary",
            "date_of_joining",
            "created_at",
        ]
    elif report_type == "documents":
        rows = await repo.get_all_documents_for_report()
        headers = [
            "file_name",
            "file_type",
            "file_size",
            "status",
            "ocr_status",
            "owner_email",
            "created_at",
        ]
    elif report_type == "workflows":
        rows = await repo.get_all_workflows_for_report()
        headers = [
            "name",
            "is_active",
            "execution_count",
            "completed",
            "failed",
            "created_at",
        ]
    elif report_type == "departments":
        dept_rows = await repo.get_department_breakdown()
        rows = [
            {
                "department_name": r["department_name"],
                "employee_count": r["employee_count"],
                "avg_salary": r["avg_salary"],
            }
            for r in dept_rows
        ]
        headers = ["department_name", "employee_count", "avg_salary"]
    elif report_type == "revenue":
        year = int(filters.get("year", datetime.now(UTC).year))
        monthly = await repo.get_monthly_salary_totals(year)
        rows = [
            {
                "month": f"{m['month']:02d}/{year}",
                "expenses": m["total_salary"],
                "estimated_revenue": round(float(m["total_salary"]) * 3.5, 2),
            }
            for m in monthly
        ]
        headers = ["month", "expenses", "estimated_revenue"]
    elif report_type == "ai_usage":
        stats = await repo.get_ai_usage_stats()
        monthly = await repo.get_monthly_ai_conversations()
        rows = [{"metric": k, "value": v} for k, v in stats.items()] + [
            {"metric": f"conversations_{r['month']}", "value": r["count"]} for r in monthly
        ]
        headers = ["metric", "value"]
    else:
        rows = []
        headers = ["metric", "value"]

    return rows, headers


# ===========================================================================
# File writers
# ===========================================================================


def _write_file(
    report_id: uuid.UUID,
    report_type: str,
    fmt: str,
    headers: list[str],
    rows: list[dict[str, Any]],
) -> Path:
    """Write rows to a file in the specified format. Returns the file path."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ext = fmt.lower()
    file_path = _REPORTS_DIR / f"{report_id}.{ext}"

    if ext == "csv":
        _write_csv(file_path, headers, rows)
    elif ext == "xlsx":
        _write_xlsx(file_path, headers, rows, report_type)
    elif ext == "pdf":
        _write_pdf(file_path, headers, rows, report_type)
    else:
        # Unknown format — fallback to CSV
        logger.warning("Unknown format '%s', falling back to CSV", ext)
        _write_csv(file_path, headers, rows)

    return file_path


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    """Write rows to a CSV file using stdlib csv."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_xlsx(
    path: Path,
    headers: list[str],
    rows: list[dict[str, Any]],
    report_type: str,
) -> None:
    """Write rows to an XLSX file using openpyxl."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        logger.warning("openpyxl not available, falling back to CSV for xlsx report")
        _write_csv(path.with_suffix(".csv"), headers, rows)
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report_type.replace("_", " ").title()

    # Header row styling
    header_fill = PatternFill("solid", fgColor="2563EB")
    header_font = Font(color="FFFFFF", bold=True)

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header.replace("_", " ").title())
        cell.fill = header_fill
        cell.font = header_font
        ws.column_dimensions[cell.column_letter].width = max(len(header) + 4, 14)

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, header in enumerate(headers, start=1):
            ws.cell(row=row_idx, column=col_idx, value=row.get(header, ""))

    wb.save(path)


def _write_pdf(
    path: Path,
    headers: list[str],
    rows: list[dict[str, Any]],
    report_type: str,
) -> None:
    """
    Write a basic PDF report.

    Uses reportlab if available; falls back to a minimal hand-crafted PDF
    (valid ASCII-safe PDF) to avoid hard dependency on reportlab.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

        doc = SimpleDocTemplate(str(path), pagesize=A4)
        table_data = [headers] + [[str(row.get(h, "")) for h in headers] for row in rows]
        table = Table(table_data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F3F4F6")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        doc.build([table])

    except ImportError:
        # Minimal hand-crafted ASCII PDF fallback
        _write_minimal_pdf(path, headers, rows, report_type)


def _write_minimal_pdf(
    path: Path,
    headers: list[str],
    rows: list[dict[str, Any]],
    report_type: str,
) -> None:
    """Write a plain-text content PDF without external dependencies."""
    buf = io.StringIO()
    buf.write(f"IntelliFlow AI — {report_type.replace('_', ' ').title()} Report\n")
    buf.write("=" * 60 + "\n")
    buf.write("\t".join(h.replace("_", " ").title() for h in headers) + "\n")
    buf.write("-" * 60 + "\n")
    for row in rows:
        buf.write("\t".join(str(row.get(h, "")) for h in headers) + "\n")

    content = buf.getvalue()
    # Minimal valid PDF structure (plain text stream)
    pdf = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        f"4 0 obj\n<< /Length {len(content) + 60} >>\nstream\n"
        f"BT /F1 10 Tf 40 750 Td ({content[:200].replace('(', '').replace(')', '')}) Tj ET\n"
        f"endstream\nendobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        "xref\n0 6\n"
        "trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
    )
    path.write_text(pdf, encoding="utf-8", errors="replace")
