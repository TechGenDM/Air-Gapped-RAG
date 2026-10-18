"""Citation-backed Question-Answering endpoint powered by local Gemma 4 12B."""

import logging
import time
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core.config import Settings, get_settings
from app.core.errors import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
)
from app.schemas.answer import (
    AnswerRequest,
    AnswerResponse,
    SourceReference,
)
from app.services.embedding_service import (
    EmbeddingServiceProtocol,
    get_embedding_service,
)
from app.services.llm_service import (
    LLMServiceProtocol,
    get_llm_service,
)
from app.services.vector_service import (
    LanceDBVectorService,
    get_vector_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/answer", tags=["answer"])


@router.post(
    "",
    response_model=AnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate citation-backed answer to document questions",
    description=(
        "Retrieves the most semantically relevant document chunks from the local LanceDB "
        "vector database, synthesizes a concise factual answer using local Gemma 4 12B via Ollama, "
        "and returns verified page citations. Responds with 'Not found in records' if evidence is insufficient."
    ),
)
async def generate_answer(
    request: AnswerRequest,
    vector_service: LanceDBVectorService = Depends(get_vector_service),
    embedding_service: EmbeddingServiceProtocol = Depends(get_embedding_service),
    llm_service: LLMServiceProtocol = Depends(get_llm_service),
    settings: Settings = Depends(get_settings),
) -> AnswerResponse:
    """Execute citation-backed Q&A pipeline over indexed document chunks."""
    start_time = time.perf_counter()

    # 1. Validate query string
    clean_query = request.query.strip()
    if not clean_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Query string cannot be empty or whitespace.",
        )

    # 2. Validate optional document_id filter
    if request.document_id:
        try:
            uuid.UUID(request.document_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document ID format '{request.document_id}'. Expected UUID.",
            )

    # 3. Generate dense query embedding
    try:
        query_vector = await embedding_service.embed_query(clean_query)
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

    # 4. Retrieve nearest-neighbor chunks from local vector store
    matched_chunks = vector_service.search(
        query_vector=query_vector,
        limit=request.limit,
        document_id=request.document_id,
    )

    # 4b. Expand with relevant continuation chunks for clauses spanning boundaries
    if matched_chunks:
        matched_chunks = vector_service.expand_continuation_chunks(
            chunks=matched_chunks,
            query=clean_query,
            query_vector=query_vector,
            max_total_chunks=min(request.limit + 2, 6),
        )

    # If no relevant chunks exist in the vector database
    if not matched_chunks:
        elapsed = round(time.perf_counter() - start_time, 3)
        return AnswerResponse(
            question=clean_query,
            answer="Not found in records",
            sources=[],
            evidence_sufficient=False,
            model=settings.llm_model,
            elapsed_seconds=elapsed,
        )

    # 5. Synthesize answer with local Gemma LLM
    try:
        answer_text, verified_chunks, evidence_sufficient = await llm_service.generate_answer(
            query=clean_query,
            chunks=matched_chunks,
        )
    except (OllamaConnectionError, OllamaModelNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM answer generation failed: {exc}",
        ) from exc

    # 6. Build verified source references
    sources: list[SourceReference] = []
    clean_answer = answer_text.strip().rstrip(".! ").lower()
    if evidence_sufficient and verified_chunks and clean_answer != "not found in records":
        for chunk in verified_chunks:
            sources.append(
                SourceReference(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page_number=chunk.page_number,
                    excerpt=chunk.text.strip(),
                )
            )
    else:
        # If insufficient evidence or zero verified sources, strictly report Not found in records
        answer_text = "Not found in records"
        evidence_sufficient = False
        sources = []

    elapsed = round(time.perf_counter() - start_time, 3)

    logger.info(
        "Answer generated: query='%s', sufficient=%s, sources_count=%d, elapsed=%.3fs",
        clean_query[:50],
        evidence_sufficient,
        len(sources),
        elapsed,
    )

    return AnswerResponse(
        question=clean_query,
        answer=answer_text,
        sources=sources,
        evidence_sufficient=evidence_sufficient,
        model=settings.llm_model,
        elapsed_seconds=elapsed,
    )
