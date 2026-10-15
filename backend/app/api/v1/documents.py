"""Document upload and extraction API endpoints."""

import logging
from pathlib import Path
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)

from app.core.config import Settings, get_settings
from app.core.errors import (
    CorruptPDFError,
    DocumentAlreadyIndexedError,
    EmptyPDFError,
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    PasswordProtectedPDFError,
    PDFExtractionError,
    VectorStoreError,
)
from app.schemas.document import DocumentUploadResponse
from app.schemas.index import IndexDocumentResponse
from app.services.chunking_service import chunk_document_pages
from app.services.embedding_service import (
    EmbeddingServiceProtocol,
    get_embedding_service,
)
from app.services.pdf_service import extract_pdf_pages
from app.services.storage_service import (
    get_document_filename,
    sanitize_filename,
    save_document,
)
from app.services.vector_service import (
    LanceDBVectorService,
    get_vector_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/acrobat",
    "applications/vnd.pdf",
    "text/pdf",
    "text/x-pdf",
    "application/octet-stream",  # Often sent by generic form uploaders
}

_CHUNK_SIZE = 1024 * 1024  # 1 MB chunk


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and extract PDF document",
    description=(
        "Accepts a PDF file upload (up to 50 MB), validates file headers and structure, "
        "persists the original document under a secure UUID, and extracts text with 1-indexed page mapping."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="PDF document file to upload and extract"),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    """Handle PDF upload, size validation, structure validation, persistence, and text extraction."""
    raw_filename = file.filename or ""

    # 1. Filename extension check
    if not raw_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only PDF documents (.pdf) are accepted.",
        )

    # 2. Content-Type check (when specified by client)
    if file.content_type and file.content_type.lower() not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type '{file.content_type}'. Expected PDF.",
        )

    # 3. Stream reading with strict size limit enforcement
    byte_buffer = bytearray()
    total_bytes = 0

    try:
        while chunk := await file.read(_CHUNK_SIZE):
            total_bytes += len(chunk)
            if total_bytes > settings.max_upload_size_bytes:
                max_mb = settings.max_upload_size_bytes // (1024 * 1024)
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File size exceeds the maximum limit of {max_mb} MB.",
                )
            byte_buffer.extend(chunk)
    finally:
        await file.close()

    # 4. Empty file check
    if len(byte_buffer) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    pdf_bytes = bytes(byte_buffer)

    # 5. Magic byte content verification (must start with %PDF-)
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file content is not a valid PDF document (missing %PDF- header).",
        )

    # 6. Extract text and structural metadata using PyMuPDF service
    try:
        extraction_result = extract_pdf_pages(
            pdf_bytes=pdf_bytes,
            ocr_enabled=settings.ocr_enabled,
            ocr_dpi=settings.ocr_dpi,
            ocr_language=settings.ocr_language,
            tessdata_dir=settings.ocr_tessdata_dir,
        )
    except EmptyPDFError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Empty PDF document: {exc}",
        ) from exc
    except PasswordProtectedPDFError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="PDF is password-protected or encrypted and cannot be processed.",
        ) from exc
    except CorruptPDFError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Corrupt or invalid PDF document: {exc}",
        ) from exc
    except PDFExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to extract PDF document: {exc}",
        ) from exc

    # 7. Persist raw file to local upload directory using unique UUID
    clean_filename = sanitize_filename(raw_filename)
    document_id, _ = save_document(
        pdf_bytes,
        settings.upload_dir,
        original_filename=clean_filename,
    )

    # 8. Privacy-compliant logging (DO NOT log extracted text or confidential content)
    logger.info(
        "Successfully uploaded document: id=%s, filename=%s, pages=%d, size=%d bytes",
        document_id,
        clean_filename,
        extraction_result.total_pages,
        len(pdf_bytes),
    )

    return DocumentUploadResponse(
        document_id=document_id,
        filename=clean_filename,
        total_pages=extraction_result.total_pages,
        pages=extraction_result.pages,
    )


@router.post(
    "/{document_id}/index",
    response_model=IndexDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Index document chunks into local vector store",
    description="Chunk pages, compute embeddings via local Ollama nomic-embed-text, and store in LanceDB.",
)
async def index_document(
    document_id: str,
    reindex: bool = False,
    settings: Settings = Depends(get_settings),
    vector_service: LanceDBVectorService = Depends(get_vector_service),
    embedding_service: EmbeddingServiceProtocol = Depends(get_embedding_service),
) -> IndexDocumentResponse:
    """Generate vector index for a previously uploaded PDF document."""
    # 1. Validate UUID format
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document ID format '{document_id}'. Expected UUID.",
        )

    # 2. Check if file exists on disk
    doc_path = settings.upload_dir / f"{document_id}.pdf"
    if not doc_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found. Please upload the PDF first.",
        )

    # 3. Check for existing index to prevent accidental duplication
    if not reindex and vector_service.is_document_indexed(document_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document '{document_id}' is already indexed in the vector database. Set reindex=true to overwrite.",
        )

    # 4. Read PDF and extract pages
    pdf_bytes = doc_path.read_bytes()
    try:
        extraction_result = extract_pdf_pages(
            pdf_bytes=pdf_bytes,
            ocr_enabled=settings.ocr_enabled,
            ocr_dpi=settings.ocr_dpi,
            ocr_language=settings.ocr_language,
            tessdata_dir=settings.ocr_tessdata_dir,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to extract document for indexing: {exc}",
        ) from exc

    # 5. Chunk pages while strictly maintaining page boundaries
    doc_filename = get_document_filename(document_id, settings.upload_dir)
    chunks = chunk_document_pages(
        pages=extraction_result.pages,
        document_id=document_id,
        filename=doc_filename,
        target_words=settings.chunk_target_words,
        overlap_words=settings.chunk_overlap_words,
    )

    if not chunks:
        return IndexDocumentResponse(
            document_id=document_id,
            filename=doc_filename,
            total_pages=extraction_result.total_pages,
            total_chunks=0,
            reindexed=reindex,
            message="Document contains zero text chunks to index (empty or whitespace only).",
        )

    # 6. Generate embeddings via local Ollama
    chunk_texts = [c.text for c in chunks]
    try:
        embeddings = await embedding_service.embed_documents(chunk_texts)
    except (OllamaConnectionError, OllamaModelNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local embedding generation failed: {exc}",
        ) from exc

    # 7. Store in LanceDB
    try:
        indexed_count = vector_service.index_chunks(
            chunks=chunks,
            embeddings=embeddings,
            reindex=reindex,
        )
    except DocumentAlreadyIndexedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector storage failed: {exc}",
        ) from exc

    logger.info(
        "Successfully indexed document id=%s: %d chunks across %d pages",
        document_id,
        indexed_count,
        extraction_result.total_pages,
    )

    return IndexDocumentResponse(
        document_id=document_id,
        filename=doc_filename,
        total_pages=extraction_result.total_pages,
        total_chunks=indexed_count,
        reindexed=reindex,
        message=f"Successfully indexed {indexed_count} chunks from {extraction_result.total_pages} pages.",
    )

