"""Pydantic schemas for extracted document content and metadata."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedPage(BaseModel):
    """Extracted text and structural metadata for a single document page."""

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(
        ...,
        ge=1,
        description="1-indexed physical page number matching the document",
    )
    text: str = Field(
        ...,
        description="Extracted plain text content of the page",
    )
    char_count: int = Field(
        ...,
        ge=0,
        description="Total character count in the extracted text",
    )
    word_count: int = Field(
        ...,
        ge=0,
        description="Total word count in the extracted text",
    )
    has_images: bool = Field(
        ...,
        description="True if the page contains embedded images or raster graphics",
    )
    ocr_applied: bool = Field(
        default=False,
        description="True if local OCR fallback was applied to extract text from this page",
    )


class DocumentExtractionResult(BaseModel):
    """Overall extraction output for a processed PDF document."""

    model_config = ConfigDict(frozen=True)

    total_pages: int = Field(
        ...,
        ge=1,
        description="Total number of physical pages in the document",
    )
    pages: list[ExtractedPage] = Field(
        ...,
        description="Sequential list of extracted pages with 1-indexed numbering",
    )


class DocumentUploadResponse(BaseModel):
    """Response returned upon successful document upload and extraction."""

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(
        ...,
        description="Unique UUID assigned to the stored document",
    )
    filename: str = Field(
        ...,
        description="Original filename of the uploaded document (sanitized)",
    )
    total_pages: int = Field(
        ...,
        ge=1,
        description="Total physical pages extracted from the document",
    )
    pages: list[ExtractedPage] = Field(
        ...,
        description="Sequential list of extracted pages with 1-indexed numbering",
    )

