"""
Storage service — secure local filesystem storage manager.

Handles streaming file uploads, SHA-256 checksum computation,
file type / MIME validation, size limits (100 MB), path-traversal prevention,
and secure file retrieval.
"""

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

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

# Generic MIME types that need extension validation
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
    """Manages file storage operations on the local filesystem."""

    def __init__(self, storage_dir: str | None = None) -> None:
        """Initialize storage manager with base directory."""
        self._storage_dir = Path(storage_dir or settings.STORAGE_DIR).resolve()
        self._max_size = settings.MAX_UPLOAD_SIZE_BYTES
        self._ensure_storage_dir()

    def _ensure_storage_dir(self) -> None:
        """Create the storage directory tree if it does not exist."""
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create storage directory %s: %s", self._storage_dir, exc)
            raise RuntimeError(f"Storage directory initialization failed: {exc}") from exc

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize user-provided filename to prevent path traversal and shell injection.

        Removes paths, null bytes, and non-printable characters.
        """
        if not filename or "\0" in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file name: null bytes or empty name detected.",
            )

        # Check for path traversal sequences
        if ".." in filename or "/" in filename or "\\" in filename:
            # Strip path separators to get the basename
            filename = os.path.basename(filename.replace("\\", "/"))

        # Clean non-standard characters while preserving unicode letters/numbers
        cleaned = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
        if not cleaned or cleaned == ".":
            cleaned = f"upload_{uuid.uuid4().hex[:8]}"

        return cleaned

    def validate_file_type(self, filename: str, content_type: str | None) -> tuple[str, str]:
        """
        Validate that the file extension and MIME type are in the allowlist.

        Returns:
            Tuple of (extension, normalized_mime_type).

        Raises:
            HTTPException 400: If the file type is unsupported or mismatched.
        """
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

    async def save_upload_file(
        self,
        upload_file: UploadFile,
        *,
        owner_id: uuid.UUID,
    ) -> StoredFileMetadata:
        """
        Stream an UploadFile to disk, verifying size and calculating SHA-256.

        Never loads the full file into memory. Enforces max file size during streaming.
        Cleans up partial files on any failure.

        Args:
            upload_file: The FastAPI UploadFile object.
            owner_id: UUID of the uploading user.

        Returns:
            StoredFileMetadata with storage path, original name, size, MIME type, and hash.

        Raises:
            HTTPException 400: Validation failure.
            HTTPException 413: File exceeds max size.
            HTTPException 500: Disk write failure.
        """
        raw_filename = upload_file.filename or f"upload_{uuid.uuid4().hex[:8]}"
        sanitized_name = self.sanitize_filename(raw_filename)
        _, mime_type = self.validate_file_type(sanitized_name, upload_file.content_type)

        # Create user-scoped subdirectory
        user_dir = self._storage_dir / str(owner_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique storage filename
        unique_prefix = uuid.uuid4().hex
        storage_filename = f"{unique_prefix}_{sanitized_name}"
        destination_path = user_dir / storage_filename

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
                        # Limit exceeded — abort and delete partial file
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
        # Relative path within storage
        relative_storage_path = f"{owner_id}/{storage_filename}"

        logger.info(
            "File stored successfully: path=%s size=%d checksum=%s",
            relative_storage_path,
            bytes_written,
            checksum,
        )

        return StoredFileMetadata(
            storage_path=relative_storage_path,
            file_name=sanitized_name,
            file_size=bytes_written,
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

    def get_file_path(self, storage_path: str) -> Path:
        """Alias for resolve_path."""
        return self.resolve_path(storage_path)

    def resolve_path(self, storage_path: str) -> Path:
        """
        Resolve a relative storage path and verify it stays inside STORAGE_DIR.

        Prevents directory traversal attacks.

        Args:
            storage_path: Relative storage path.

        Returns:
            Resolved absolute Path.

        Raises:
            HTTPException 404: If file does not exist.
            HTTPException 403: If path escapes STORAGE_DIR.
        """
        if "\0" in storage_path or ".." in storage_path:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid file path detected.",
            )

        candidate = (self._storage_dir / storage_path).resolve()

        # Strict boundary check: candidate must be relative to storage_dir
        try:
            candidate.relative_to(self._storage_dir)
        except ValueError:
            logger.warning("Directory traversal attempt blocked: %s", storage_path)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to the specified storage path is forbidden.",
            ) from None

        if not candidate.is_file():
            logger.warning("Stored file not found on disk: %s", candidate)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The requested file was not found in storage.",
            )

        return candidate

    def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from storage if it exists.

        Args:
            storage_path: Relative storage path.

        Returns:
            True if deleted, False if file did not exist.
        """
        try:
            resolved = self.resolve_path(storage_path)
            self._delete_file_safely(resolved)
            return True
        except HTTPException:
            return False

    @staticmethod
    def _delete_file_safely(path: Path) -> None:
        """Unlink file without raising if missing."""
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to delete file %s: %s", path, exc)
