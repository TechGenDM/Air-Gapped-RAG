"""Schemas for citation-backed local LLM answer generation."""

from pydantic import BaseModel, ConfigDict, Field


class AnswerRequest(BaseModel):
    """Payload for question-answering over indexed document chunks."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User question regarding the uploaded document",
    )
    document_id: str | None = Field(
        None,
        description="Optional document UUID to constrain Q&A to a single document",
    )
    limit: int = Field(
        4,
        ge=1,
        le=20,
        description="Number of top relevant chunks to retrieve as context",
    )


class SourceReference(BaseModel):
    """A verified source citation matching retrieved document text."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(..., description="Unique ID of source chunk")
    document_id: str = Field(..., description="UUID of source document")
    filename: str = Field(..., description="Source document filename")
    page_number: int = Field(..., ge=1, description="1-indexed physical page citation")
    excerpt: str = Field(..., description="Exact textual excerpt supporting the answer")


class AnswerResponse(BaseModel):
    """Citation-backed Q&A response synthesized by local Gemma."""

    model_config = ConfigDict(frozen=True)

    question: str = Field(..., description="Original user question")
    answer: str = Field(..., description="Synthesized answer text or 'Not found in records'")
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="List of verified source citations with exact page numbers",
    )
    evidence_sufficient: bool = Field(
        ...,
        description="True if context contained sufficient evidence; False if 'Not found in records'",
    )
    model: str = Field(..., description="Local LLM model identifier")
    elapsed_seconds: float = Field(
        ...,
        ge=0.0,
        description="End-to-end processing latency in seconds",
    )
