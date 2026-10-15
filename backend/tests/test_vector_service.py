"""Unit tests for LanceDB embedded vector storage and semantic retrieval."""

import pytest

from app.core.errors import DocumentAlreadyIndexedError
from app.schemas.chunk import DocumentChunk
from app.services.vector_service import LanceDBVectorService


def _create_test_chunk(
    document_id: str,
    page_number: int,
    chunk_index: int,
    text: str,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"{document_id}_p{page_number}_c{chunk_index}",
        document_id=document_id,
        filename=f"{document_id}.pdf",
        page_number=page_number,
        chunk_index=chunk_index,
        text=text,
        char_count=len(text),
        word_count=len(text.split()),
    )


def test_index_and_search_chunks(temp_lancedb_dir, mock_embedding_service):
    """Verify storing vectors in LanceDB and retrieving nearest neighbors with page citations."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)

    chunks = [
        _create_test_chunk("doc-1", 1, 0, "Confidentiality and nondisclosure terms for trade secrets."),
        _create_test_chunk("doc-1", 2, 0, "Payment milestones and net 30 invoice settlement rules."),
        _create_test_chunk("doc-1", 3, 0, "Arbitration and choice of venue under Delaware jurisdiction."),
    ]
    embeddings = [
        mock_embedding_service._make_vector(c.text)
        for c in chunks
    ]

    count = vector_service.index_chunks(chunks, embeddings)
    assert count == 3
    assert vector_service.is_document_indexed("doc-1") is True

    # Search using vector close to chunk 1 (payment)
    query_vec = mock_embedding_service._make_vector("How are invoices and payments settled?")
    results = vector_service.search(query_vec, limit=2)

    assert len(results) <= 2
    top_result = results[0]
    assert top_result.document_id == "doc-1"
    assert top_result.page_number in [1, 2, 3]
    assert 0.0 <= top_result.score <= 1.0
    assert top_result.distance >= 0.0


def test_document_id_filtering(temp_lancedb_dir, mock_embedding_service):
    """Verify that document_id parameter strictly scopes the vector search."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)

    chunks_a = [_create_test_chunk("doc-A", 1, 0, "Software licensing terms for Alpha Corp.")]
    chunks_b = [_create_test_chunk("doc-B", 1, 0, "Hardware manufacturing agreement for Beta Corp.")]

    vector_service.index_chunks(chunks_a, [mock_embedding_service._make_vector(chunks_a[0].text)])
    vector_service.index_chunks(chunks_b, [mock_embedding_service._make_vector(chunks_b[0].text)])

    query_vec = mock_embedding_service._make_vector("corporate licensing")

    # Search scoped to doc-A
    results_a = vector_service.search(query_vec, limit=5, document_id="doc-A")
    assert len(results_a) == 1
    assert results_a[0].document_id == "doc-A"

    # Search scoped to doc-B
    results_b = vector_service.search(query_vec, limit=5, document_id="doc-B")
    assert len(results_b) == 1
    assert results_b[0].document_id == "doc-B"


def test_duplicate_indexing_prevention(temp_lancedb_dir, mock_embedding_service):
    """Verify that re-indexing an existing document without reindex=True raises DocumentAlreadyIndexedError."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)

    chunks = [_create_test_chunk("doc-dup", 1, 0, "Original document text.")]
    embs = [mock_embedding_service._make_vector(chunks[0].text)]

    vector_service.index_chunks(chunks, embs, reindex=False)

    with pytest.raises(DocumentAlreadyIndexedError, match="already indexed"):
        vector_service.index_chunks(chunks, embs, reindex=False)


def test_reindex_overwrites_previous_chunks(temp_lancedb_dir, mock_embedding_service):
    """Verify that reindex=True cleanly purges old document chunks and inserts new ones."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)

    chunks_v1 = [_create_test_chunk("doc-re", 1, 0, "Version 1 deprecated contract clause.")]
    vector_service.index_chunks(chunks_v1, [mock_embedding_service._make_vector(chunks_v1[0].text)])

    chunks_v2 = [_create_test_chunk("doc-re", 1, 0, "Version 2 amended and restated contract clause.")]
    vector_service.index_chunks(chunks_v2, [mock_embedding_service._make_vector(chunks_v2[0].text)], reindex=True)

    query_vec = mock_embedding_service._make_vector("amended clause")
    results = vector_service.search(query_vec, limit=5, document_id="doc-re")

    assert len(results) == 1
    assert "Version 2 amended" in results[0].text
    assert "deprecated" not in results[0].text


def test_search_empty_database_returns_empty_list(temp_lancedb_dir):
    """Verify that searching an unpopulated vector database returns an empty list gracefully."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)
    dummy_vec = [0.0] * 768
    assert vector_service.search(dummy_vec, limit=5) == []
