"""Schemas for semantic search requests and responses."""

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    """Payload for semantic vector search."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query or question",
    )
    document_id: str | None = Field(
        None,
        description="Optional document UUID to scope the search to a specific contract",
    )
    limit: int = Field(
        5,
        ge=1,
        le=50,
        description="Maximum number of relevant chunks to retrieve",
    )


class SearchResultChunk(BaseModel):
    """A matched chunk with relevance scoring and page metadata."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(..., description="Unique chunk identifier")
    document_id: str = Field(..., description="UUID of source document")
    filename: str = Field(..., description="Filename of source document")
    page_number: int = Field(..., ge=1, description="1-indexed physical page citation")
    chunk_index: int = Field(..., ge=0, description="Chunk sequence on page")
    text: str = Field(..., description="Matched text excerpt")
    score: float = Field(..., description="Normalized similarity score (0.0 to 1.0)")
    distance: float = Field(..., description="Raw vector distance metric")


class SearchResponse(BaseModel):
    """Top-k semantic retrieval response."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="Original query evaluated")
    document_id: str | None = Field(None, description="Document filter applied, if any")
    total_results: int = Field(..., ge=0, description="Count of retrieved chunks")
    results: list[SearchResultChunk] = Field(..., description="Ranked list of matching chunks")
