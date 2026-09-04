"""
Storage service — secure storage manager supporting Local filesystem and Supabase Storage.

Backends:
  - "local" (default): Local Docker filesystem volume (/app/storage/documents).
  - "supabase": Private bucket in Supabase Object Storage with service-role authentication.

Features:
  - Streaming uploads with SHA-256 checksum computation.
  - File type / MIME validation, size limits (25 MB default).
  - Strict path traversal prevention.
  - Transparent legacy fallback: if a file is not in Supabase Storage, checks local disk.
  - Async streaming for downloads and previews.
  - Temporary local path scoping for file-path-dependent tasks (e.g. OCR text extraction).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# Allowed file extensions (lowercase with leading dot)
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"})

# Allowed MIME types mapped to extensions
MIME_TO_EXTENSIONS: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/pjpeg": {".jpg", ".jpeg"},
}

GENERIC_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/octet-stream",
        "application/x-zip-compressed",
        "binary/octet-stream",
    }
)

CHUNK_SIZE = 64 * 1024  # 64 KB chunks for streaming


@dataclass(frozen=True)
class StoredFileMetadata:
    """Metadata returned after a successful file stream and persistence."""

    storage_path: str
    file_name: str
    file_size: int
    file_type: str
    checksum: str


class StorageService:
    """Manages file storage operations on local disk or Supabase Object Storage."""

    def __init__(self, storage_dir: str | None = None) -> None:
        self._storage_dir = Path(storage_dir or settings.STORAGE_DIR).resolve()
        self._backend = settings.STORAGE_BACKEND.lower()
        self._max_size = settings.MAX_UPLOAD_SIZE_BYTES
        self._ensure_storage_dir()

    def _ensure_storage_dir(self) -> None:
        """Create the storage directory tree if it does not exist."""
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create storage directory %s: %s", self._storage_dir, exc)
            raise RuntimeError(f"Storage directory initialization failed: {exc}") from exc

    # =========================================================================
    # Validation & Sanitization
    # =========================================================================

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize user-provided filename to prevent path traversal and shell injection.
        """
        if not filename or "\0" in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file name: null bytes or empty name detected.",
            )

        if ".." in filename or "/" in filename or "\\" in filename:
            filename = os.path.basename(filename.replace("\\", "/"))

        cleaned = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
        if not cleaned or cleaned == ".":
            cleaned = f"upload_{uuid.uuid4().hex[:8]}"

        return cleaned

    def validate_file_type(self, filename: str, content_type: str | None) -> tuple[str, str]:
        """Validate file extension and MIME type against allowed list."""
        ext = Path(filename).suffix.lower()
        if not ext or ext not in ALLOWED_EXTENSIONS:
            allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{ext}'. Allowed formats: {allowed_list}",
            )

        mime = (content_type or "").lower().split(";")[0].strip()

        # If MIME is provided and known, verify it matches the extension
        if mime in MIME_TO_EXTENSIONS:
            if ext not in MIME_TO_EXTENSIONS[mime]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File extension '{ext}' does not match content type '{mime}'.",
                )
        elif mime and mime not in GENERIC_MIME_TYPES:
            # Unrecognized specific MIME type
            logger.warning("Unrecognized MIME type '%s' for extension '%s'", mime, ext)

        # Default MIME type if generic or missing
        if not mime or mime in GENERIC_MIME_TYPES:
            ext_to_default_mime = {
                ".pdf": "application/pdf",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }
            mime = ext_to_default_mime.get(ext, "application/octet-stream")

        return ext, mime

    def _validate_safe_path(self, storage_path: str) -> str:
        """Verify that storage_path does not contain path traversal sequences."""
        if not storage_path or "\0" in storage_path or ".." in storage_path:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid file path detected.",
            )
        # Normalize slashes
        clean_path = storage_path.replace("\\", "/").strip("/")
        return clean_path

    # =========================================================================
    # Upload Operations
    # =========================================================================

    async def save_upload_file(
        self,
        upload_file: UploadFile,
        *,
        owner_id: uuid.UUID,
    ) -> StoredFileMetadata:
        """
        Stream an UploadFile to storage (local disk or Supabase), validating size and SHA-256.
        """
        raw_filename = upload_file.filename or f"upload_{uuid.uuid4().hex[:8]}"
        sanitized_name = self.sanitize_filename(raw_filename)
        _, mime_type = self.validate_file_type(sanitized_name, upload_file.content_type)

        unique_prefix = uuid.uuid4().hex
        storage_filename = f"{unique_prefix}_{sanitized_name}"
        relative_storage_path = f"{owner_id}/{storage_filename}"

        if self._backend == "supabase":
            return await self._save_supabase(upload_file, relative_storage_path, sanitized_name, mime_type)

        return await self._save_local(upload_file, relative_storage_path, sanitized_name, mime_type, owner_id)

    async def _save_local(
        self,
        upload_file: UploadFile,
        relative_storage_path: str,
        sanitized_name: str,
        mime_type: str,
        owner_id: uuid.UUID,
    ) -> StoredFileMetadata:
        user_dir = self._storage_dir / str(owner_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        destination_path = self._storage_dir / relative_storage_path

        hasher = hashlib.sha256()
        bytes_written = 0

        try:
            with open(destination_path, "wb") as out_file:
                while True:
                    chunk = await upload_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > self._max_size:
                        out_file.close()
                        self._delete_file_safely(destination_path)
                        max_mb = self._max_size // (1024 * 1024)
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds the maximum allowed size of {max_mb} MB.",
                        )
                    hasher.update(chunk)
                    out_file.write(chunk)

            if bytes_written == 0:
                self._delete_file_safely(destination_path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot upload an empty file.",
                )
        except HTTPException:
            self._delete_file_safely(destination_path)
            raise
        except Exception as exc:
            self._delete_file_safely(destination_path)
            logger.exception("Failed while streaming file to disk: %s", destination_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded file.",
            ) from exc

        checksum = hasher.hexdigest()
        logger.info("File stored locally: path=%s size=%d", relative_storage_path, bytes_written)
        return StoredFileMetadata(
            storage_path=relative_storage_path,
            file_name=sanitized_name,
            file_size=bytes_written,
            file_type=mime_type,
            checksum=checksum,
        )

    async def _save_supabase(
        self,
        upload_file: UploadFile,
        relative_storage_path: str,
        sanitized_name: str,
        mime_type: str,
    ) -> StoredFileMetadata:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase Storage is not configured on the server.",
            )

        content = await upload_file.read()
        file_size = len(content)

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot upload an empty file.",
            )
        if file_size > self._max_size:
            max_mb = self._max_size // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the maximum allowed size of {max_mb} MB.",
            )

        hasher = hashlib.sha256(content)
        checksum = hasher.hexdigest()

        endpoint = (
            f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/"
            f"{settings.SUPABASE_STORAGE_BUCKET}/{relative_storage_path}"
        )
        headers = {
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": mime_type,
            "x-upsert": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.SUPABASE_TIMEOUT_SECONDS) as client:
                res = await client.post(endpoint, content=content, headers=headers)
        except Exception as exc:
            logger.error("Supabase Storage upload connection error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload document to cloud storage.",
            ) from exc

        if res.status_code not in (200, 201):
            logger.error("Supabase Storage upload failed (%d): %s", res.status_code, res.text[:200])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cloud storage rejected the uploaded file.",
            )

        logger.info("File stored in Supabase Storage: path=%s size=%d", relative_storage_path, file_size)
        return StoredFileMetadata(
            storage_path=relative_storage_path,
            file_name=sanitized_name,
            file_size=file_size,
            file_type=mime_type,
            checksum=checksum,
        )

    # Alias for interface compatibility
    async def save_upload(
        self,
        upload_file: UploadFile,
        *,
        owner_id: uuid.UUID,
    ) -> StoredFileMetadata:
        """Alias for save_upload_file."""
        return await self.save_upload_file(upload_file, owner_id=owner_id)

    # =========================================================================
    # Retrieval & Streaming
    # =========================================================================

    def resolve_path(self, storage_path: str) -> Path:
        """
        Resolve a relative storage path on the local filesystem.
        Used for local mode and local file operations.
        """
        clean_path = self._validate_safe_path(storage_path)
        candidate = (self._storage_dir / clean_path).resolve()

        try:
            candidate.relative_to(self._storage_dir)
        except ValueError:
            logger.warning("Directory traversal attempt blocked: %s", storage_path)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to the specified storage path is forbidden.",
            ) from None

        if not candidate.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The requested file was not found in storage.",
            )

        return candidate

    def get_file_path(self, storage_path: str) -> Path:
        """Alias for resolve_path."""
        return self.resolve_path(storage_path)

    async def exists(self, storage_path: str) -> bool:
        """
        Check if a file exists in the active storage backend or local legacy store.
        """
        clean_path = self._validate_safe_path(storage_path)

        # Check local disk first
        local_file = (self._storage_dir / clean_path).resolve()
        try:
            local_file.relative_to(self._storage_dir)
            if local_file.is_file():
                return True
        except ValueError:
            return False

        if self._backend != "supabase":
            return False

        # Check Supabase Storage
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            return False

        endpoint = (
            f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/info/authenticated/"
            f"{settings.SUPABASE_STORAGE_BUCKET}/{clean_path}"
        )
        headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(endpoint, headers=headers)
                return res.status_code == 200
        except Exception:
            return False

    async def open_stream(
        self,
        storage_path: str,
        file_size: int | None = None,
        file_type: str | None = None,
    ) -> tuple[AsyncIterable[bytes], int, str]:
        """
        Open an async byte stream for the specified document.
        Returns: (byte_generator, content_length, content_type)
        """
        clean_path = self._validate_safe_path(storage_path)
        content_type = file_type or "application/octet-stream"

        # 1. If stored in Supabase, fetch from Supabase Storage
        if self._backend == "supabase" and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            endpoint = (
                f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/authenticated/"
                f"{settings.SUPABASE_STORAGE_BUCKET}/{clean_path}"
            )
            headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"}

            try:
                client = httpx.AsyncClient(timeout=settings.SUPABASE_TIMEOUT_SECONDS)
                req = client.build_request("GET", endpoint, headers=headers)
                res = await client.send(req, stream=True)
            except Exception as exc:
                logger.error("Supabase Storage stream connection failed: %s", exc)
                res = None

            if res is not None and res.status_code == 200:
                length = int(res.headers.get("content-length", file_size or 0))
                ctype = res.headers.get("content-type", content_type)

                async def _supabase_stream() -> AsyncIterable[bytes]:
                    try:
                        async for chunk in res.aiter_bytes(CHUNK_SIZE):
                            yield chunk
                    finally:
                        await res.aclose()
                        await client.aclose()

                return _supabase_stream(), length, ctype

            if res is not None:
                await res.aclose()
                await client.aclose()

        # 2. Legacy / Local fallback: check local disk
        local_candidate = (self._storage_dir / clean_path).resolve()
        try:
            local_candidate.relative_to(self._storage_dir)
            if local_candidate.is_file():
                actual_size = file_size or local_candidate.stat().st_size

                async def _local_stream() -> AsyncIterable[bytes]:
                    with open(local_candidate, "rb") as f:
                        while True:
                            data = f.read(CHUNK_SIZE)
                            if not data:
                                break
                            yield data

                return _local_stream(), actual_size, content_type
        except ValueError:
            pass

        # 3. If file exists nowhere, raise 404
        logger.warning("Requested storage file does not exist: %s", storage_path)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file was not found in storage.",
        )

    @asynccontextmanager
    async def scoped_local_path(self, storage_path: str) -> AsyncIterator[Path]:
        """
        Async context manager providing a physical file Path on disk for processing.
        If local file exists, yields it directly.
        If in Supabase, downloads to a temporary file, yields the Path, and cleans up on exit.
        """
        clean_path = self._validate_safe_path(storage_path)
        local_candidate = (self._storage_dir / clean_path).resolve()

        try:
            local_candidate.relative_to(self._storage_dir)
            if local_candidate.is_file():
                yield local_candidate
                return
        except ValueError:
            pass

        if self._backend != "supabase" or not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise FileNotFoundError(f"File not found on local disk or cloud: {storage_path}")

        # Download from Supabase to a temporary file
        endpoint = (
            f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/authenticated/"
            f"{settings.SUPABASE_STORAGE_BUCKET}/{clean_path}"
        )
        headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"}

        ext = Path(clean_path).suffix
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_path = Path(temp_file.name)

        try:
            async with httpx.AsyncClient(timeout=settings.SUPABASE_TIMEOUT_SECONDS) as client:
                res = await client.get(endpoint, headers=headers)
                if res.status_code != 200:
                    raise FileNotFoundError(
                        f"Supabase Storage file not found (status {res.status_code}): {clean_path}"
                    )
                temp_file.write(res.content)
                temp_file.flush()
                temp_file.close()

            yield temp_path
        finally:
            self._delete_file_safely(temp_path)

    # =========================================================================
    # Deletion Operations
    # =========================================================================

    def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from storage if it exists (local disk and Supabase).
        """
        clean_path = self._validate_safe_path(storage_path)
        deleted = False

        # 1. Delete from local disk
        try:
            local_path = (self._storage_dir / clean_path).resolve()
            local_path.relative_to(self._storage_dir)
            if local_path.is_file():
                local_path.unlink()
                deleted = True
                logger.info("Deleted local file: %s", local_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error deleting local file %s: %s", storage_path, exc)

        # 2. Delete from Supabase Storage
        if self._backend == "supabase" and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            endpoint = (
                f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/"
                f"{settings.SUPABASE_STORAGE_BUCKET}"
            )
            headers = {
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            }
            payload = {"prefixes": [clean_path]}
            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.request("DELETE", endpoint, json=payload, headers=headers)
                    if res.status_code == 200:
                        deleted = True
                        logger.info("Deleted file from Supabase Storage: %s", clean_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error deleting Supabase Storage file %s: %s", clean_path, exc)

        return deleted

    def _delete_file_safely(self, path: Path) -> None:
        """Helper to delete a local file without raising."""
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.warning("Failed to clean up file %s: %s", path, exc)
