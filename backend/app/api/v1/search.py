"""Semantic search endpoint over local LanceDB vector index."""

import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core.errors import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
)
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
)
from app.services.embedding_service import (
    EmbeddingServiceProtocol,
    get_embedding_service,
)
from app.services.vector_service import (
    LanceDBVectorService,
    get_vector_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post(
    "",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic vector search across indexed documents",
    description=(
        "Generates dense query embeddings via local Ollama (nomic-embed-text) and retrieves "
        "the most relevant chunks with exact page citations and similarity scores."
    ),
)
async def semantic_search(
    request: SearchRequest,
    vector_service: LanceDBVectorService = Depends(get_vector_service),
    embedding_service: EmbeddingServiceProtocol = Depends(get_embedding_service),
) -> SearchResponse:
    """Execute semantic vector search over document chunks."""
    # 1. Validate optional document_id filter
    if request.document_id:
        try:
            uuid.UUID(request.document_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document ID format '{request.document_id}'. Expected UUID.",
            )

    # 2. Generate local dense embedding for the search query
    try:
        query_vector = await embedding_service.embed_query(request.query)
    except (OllamaConnectionError, OllamaModelNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query embedding generation failed: {exc}",
        ) from exc

    # 3. Perform vector similarity retrieval in LanceDB
    matched_chunks = vector_service.search(
        query_vector=query_vector,
        limit=request.limit,
        document_id=request.document_id,
    )

    logger.info(
        "Semantic search executed: query_len=%d, filter_doc=%s, limit=%d, returned=%d",
        len(request.query),
        request.document_id,
        request.limit,
        len(matched_chunks),
    )

    return SearchResponse(
        query=request.query,
        document_id=request.document_id,
        total_results=len(matched_chunks),
        results=matched_chunks,
    )
