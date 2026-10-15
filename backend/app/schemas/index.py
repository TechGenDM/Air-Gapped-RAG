"""Schemas for document indexing operations."""

from pydantic import BaseModel, ConfigDict, Field


class IndexDocumentResponse(BaseModel):
    """Response returned upon indexing a document's chunks into LanceDB."""

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(..., description="UUID of the indexed document")
    filename: str = Field(..., description="Filename of the indexed document")
    total_pages: int = Field(..., ge=1, description="Total physical pages parsed")
    total_chunks: int = Field(..., ge=0, description="Total vector chunks generated and stored")
    reindexed: bool = Field(..., description="True if existing index was replaced")
    message: str = Field(..., description="Status summary message")
