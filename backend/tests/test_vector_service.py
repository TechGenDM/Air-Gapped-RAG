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


def test_expand_continuation_chunks_includes_next_page_material_clause(
    temp_lancedb_dir, mock_embedding_service
):
    """Verify that when a relevant chunk ends with an open clause, the next page's substantive continuation is included."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)

    chunk_p1 = _create_test_chunk(
        "doc-span",
        1,
        0,
        "SECTION 25: Agreement without consideration is void unless: "
        "(1) it is in writing and registered; or unless "
        "(2) it is a promise to compensate voluntary past acts; or unless;",
    )
    chunk_p2_hdr = _create_test_chunk("doc-span", 2, 0, "2")  # Non-substantive page number header
    chunk_p2_cont = _create_test_chunk(
        "doc-span",
        2,
        1,
        "(3) it is a promise, made in writing and signed by the debtor or their authorized agent, "
        "to pay wholly or in part a debt barred by limitation.",
    )

    chunks = [chunk_p1, chunk_p2_hdr, chunk_p2_cont]
    embs = [mock_embedding_service._make_vector(c.text) for c in chunks]
    vector_service.index_chunks(chunks, embs)

    query = "Under what specific exceptions is an agreement made without consideration valid under Section 25?"
    q_vec = mock_embedding_service._make_vector(query)

    # Initial search with limit=1 only retrieves the page 1 chunk
    initial = vector_service.search(q_vec, limit=1, document_id="doc-span")
    assert len(initial) == 1
    assert initial[0].page_number == 1

    # Expansion pipeline identifies the continuation on page 2 and excludes the non-substantive header
    expanded = vector_service.expand_continuation_chunks(
        chunks=initial,
        query=query,
        query_vector=q_vec,
        max_total_chunks=3,
    )

    assert len(expanded) == 2
    assert expanded[0].page_number == 1
    assert expanded[0].chunk_id == "doc-span_p1_c0"
    assert expanded[1].page_number == 2
    assert expanded[1].chunk_id == "doc-span_p2_c1"
    assert "signed by the debtor or their authorized agent" in expanded[1].text


def test_expand_continuation_chunks_ignores_cleanly_terminated_chunks(
    temp_lancedb_dir, mock_embedding_service
):
    """Verify that chunks ending with a complete sentence do not trigger unnecessary adjacent page expansion."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)

    chunk_p1 = _create_test_chunk(
        "doc-term",
        1,
        0,
        "Section 4: Limitation of Liability. The total aggregate liability shall not exceed $100,000 USD.",
    )
    chunk_p2 = _create_test_chunk(
        "doc-term",
        2,
        0,
        "Section 5: Governing Law. This agreement is governed by the laws of California.",
    )

    chunks = [chunk_p1, chunk_p2]
    embs = [mock_embedding_service._make_vector(c.text) for c in chunks]
    vector_service.index_chunks(chunks, embs)

    query = "What is the limitation of liability under Section 4?"
    q_vec = mock_embedding_service._make_vector(query)

    initial = vector_service.search(q_vec, limit=1, document_id="doc-term")
    assert len(initial) == 1
    assert initial[0].page_number == 1

    expanded = vector_service.expand_continuation_chunks(
        chunks=initial,
        query=query,
        query_vector=q_vec,
        max_total_chunks=3,
    )

    # Since page 1 ends with a clean period, no continuation is added
    assert len(expanded) == 1
    assert expanded[0].page_number == 1


def test_expand_continuation_chunks_rejects_unrelated_next_page(
    temp_lancedb_dir, mock_embedding_service
):
    """Verify that continuation expansion does NOT assume every next page is relevant when content is unrelated."""
    vector_service = LanceDBVectorService(db_dir=temp_lancedb_dir, vector_dim=768)

    # Page 1 ends with an open-ended colon
    chunk_p1 = _create_test_chunk(
        "doc-unrel",
        1,
        0,
        "The following specifications apply to the hydraulic pressure testing apparatus:",
    )
    # Page 2 is completely unrelated biological taxonomy text
    chunk_p2 = _create_test_chunk(
        "doc-unrel",
        2,
        0,
        "Canis lupus familiaris is a domesticated carnivore of the family Canidae. It is part of the wolf-like canids.",
    )

    chunks = [chunk_p1, chunk_p2]
    embs = [mock_embedding_service._make_vector(c.text) for c in chunks]
    vector_service.index_chunks(chunks, embs)

    query = "What are the hydraulic pressure testing specifications?"
    q_vec = mock_embedding_service._make_vector(query)

    initial = vector_service.search(q_vec, limit=1, document_id="doc-unrel")
    assert len(initial) == 1

    expanded = vector_service.expand_continuation_chunks(
        chunks=initial,
        query=query,
        query_vector=q_vec,
        max_total_chunks=3,
    )

    # Page 2 has no structural list continuity or keyword overlap with hydraulic pressure, so it is rejected
    assert len(expanded) == 1
    assert expanded[0].page_number == 1
