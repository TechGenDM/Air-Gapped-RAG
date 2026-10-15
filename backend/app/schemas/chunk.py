"""Pydantic schemas for document chunking."""

from pydantic import BaseModel, ConfigDict, Field


class DocumentChunk(BaseModel):
    """A granular piece of text derived from a single physical page."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(
        ...,
        description="Deterministic unique ID: {document_id}_p{page_number}_c{chunk_index}",
    )
    document_id: str = Field(
        ...,
        description="UUID of the parent document",
    )
    filename: str = Field(
        ...,
        description="Sanitized original document filename",
    )
    page_number: int = Field(
        ...,
        ge=1,
        description="1-indexed physical page number where this text originated",
    )
    chunk_index: int = Field(
        ...,
        ge=0,
        description="0-indexed sequence of this chunk within the page",
    )
    text: str = Field(
        ...,
        description="Text content of the chunk",
    )
    char_count: int = Field(
        ...,
        ge=0,
        description="Character count of chunk text",
    )
    word_count: int = Field(
        ...,
        ge=0,
        description="Word count of chunk text",
    )
