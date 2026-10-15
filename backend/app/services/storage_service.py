import json
import logging
from pathlib import Path
import re
import uuid

logger = logging.getLogger(__name__)


def sanitize_filename(filename: str | None) -> str:
    """Sanitize client-provided filename to prevent directory traversal or control characters.

    Args:
        filename: Raw filename string from client request.

    Returns:
        Safe basename with dangerous characters removed. Defaults to 'document.pdf'.
    """
    if not filename:
        return "document.pdf"

    # Extract only the basename (strips any leading directory paths like ../ or C:\)
    base_name = Path(filename).name.strip()

    # Remove null bytes, path separators, and unprintable characters
    clean_name = re.sub(r"[\x00-\x1f\x7f/\\]", "", base_name)

    if not clean_name:
        return "document.pdf"

    # Ensure it ends with .pdf
    if not clean_name.lower().endswith(".pdf"):
        clean_name = f"{clean_name}.pdf"

    return clean_name


def save_document(
    pdf_bytes: bytes,
    upload_dir: Path,
    original_filename: str | None = None,
) -> tuple[str, Path]:
    """Store raw PDF bytes under upload_dir using a newly generated UUID.

    Args:
        pdf_bytes: Raw bytes of the document.
        upload_dir: Directory where the document will be saved.
        original_filename: Optional human-readable sanitized filename.

    Returns:
        A tuple of (document_id, target_file_path).
    """
    upload_dir.mkdir(parents=True, exist_ok=True)
    document_id = str(uuid.uuid4())
    target_path = upload_dir / f"{document_id}.pdf"

    # Atomic write to avoid partial writes
    temp_path = upload_dir / f".{document_id}.tmp"
    try:
        temp_path.write_bytes(pdf_bytes)
        temp_path.replace(target_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

    # Store sanitized metadata if original_filename provided
    if original_filename:
        meta_path = upload_dir / f"{document_id}.meta.json"
        try:
            meta_path.write_text(json.dumps({"filename": original_filename}), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not persist document metadata for %s: %s", document_id, exc)

    logger.info("Saved document id=%s at %s (%d bytes)", document_id, target_path, len(pdf_bytes))
    return document_id, target_path


def get_document_filename(document_id: str, upload_dir: Path) -> str:
    """Retrieve original document filename from stored metadata or default to UUID.pdf."""
    meta_path = upload_dir / f"{document_id}.meta.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "filename" in data:
                return str(data["filename"])
        except Exception:
            pass
    return f"{document_id}.pdf"


def delete_document(document_id: str, upload_dir: Path) -> bool:
    """Safely delete a stored document by its UUID.

    Args:
        document_id: UUID of the document to delete.
        upload_dir: Storage directory.

    Returns:
        True if deleted, False if file did not exist.
    """
    # Strict UUID validation to prevent path traversal
    try:
        uuid.UUID(document_id)
    except ValueError:
        logger.warning("Attempted to delete with invalid UUID format: %s", document_id)
        return False

    target_path = upload_dir / f"{document_id}.pdf"
    meta_path = upload_dir / f"{document_id}.meta.json"

    if meta_path.exists():
        meta_path.unlink(missing_ok=True)

    if target_path.exists():
        target_path.unlink()
        logger.info("Deleted document id=%s", document_id)
        return True
    return False
