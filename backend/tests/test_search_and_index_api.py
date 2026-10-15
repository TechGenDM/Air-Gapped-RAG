"""Integration tests for document indexing and semantic search API endpoints."""

from io import BytesIO
import uuid

from fastapi import status

from app.core.errors import OllamaConnectionError
from app.main import app
from app.services.embedding_service import get_embedding_service


def _upload_test_pdf(client, create_multipage_pdf, pages=None) -> str:
    """Helper to upload a test PDF and return its document_id."""
    if pages is None:
        pages = [
            "SECTION 1: Scope of Work and Deliverables.\nVendor shall deliver cloud-native components.",
            "SECTION 2: Fees, Invoicing, and Payment Schedule.\nInvoices shall be settled within 30 calendar days.",
            "SECTION 3: Indemnification and Limitation of Liability.\nLiability capped at 12 months fees.",
        ]
    pdf_bytes = create_multipage_pdf(pages)
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract_for_indexing.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == status.HTTP_201_CREATED
    return res.json()["document_id"]


def test_successful_document_indexing(client, create_multipage_pdf):
    """Verify indexing an uploaded document into LanceDB via mock embeddings."""
    doc_id = _upload_test_pdf(client, create_multipage_pdf)

    res = client.post(f"/api/v1/documents/{doc_id}/index")
    assert res.status_code == status.HTTP_200_OK

    data = res.json()
    assert data["document_id"] == doc_id
    assert data["total_pages"] == 3
    assert data["total_chunks"] >= 3
    assert data["reindexed"] is False
    assert "Successfully indexed" in data["message"]


def test_duplicate_indexing_returns_409(client, create_multipage_pdf):
    """Verify that re-indexing an already indexed document without reindex=true returns 409 Conflict."""
    doc_id = _upload_test_pdf(client, create_multipage_pdf)

    # First indexing
    res1 = client.post(f"/api/v1/documents/{doc_id}/index")
    assert res1.status_code == status.HTTP_200_OK

    # Duplicate indexing
    res2 = client.post(f"/api/v1/documents/{doc_id}/index")
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert "already indexed" in res2.json()["detail"].lower()


def test_reindexing_with_flag_succeeds(client, create_multipage_pdf):
    """Verify that reindex=true succeeds on an already indexed document."""
    doc_id = _upload_test_pdf(client, create_multipage_pdf)

    client.post(f"/api/v1/documents/{doc_id}/index")

    # Re-index with flag
    res = client.post(f"/api/v1/documents/{doc_id}/index?reindex=true")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["reindexed"] is True


def test_indexing_nonexistent_document_returns_404(client):
    """Verify that attempting to index an un-uploaded UUID returns 404 Not Found."""
    fake_id = str(uuid.uuid4())
    res = client.post(f"/api/v1/documents/{fake_id}/index")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in res.json()["detail"].lower()


def test_indexing_invalid_uuid_returns_400(client):
    """Verify that malformed document IDs return 400 Bad Request."""
    res = client.post("/api/v1/documents/not-a-valid-uuid/index")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid document id" in res.json()["detail"].lower()


def test_semantic_search_success(client, create_multipage_pdf):
    """Verify semantic search query returns ranked chunks with exact page citations."""
    doc_id = _upload_test_pdf(client, create_multipage_pdf)
    client.post(f"/api/v1/documents/{doc_id}/index")

    search_payload = {
        "query": "What are the payment terms and schedule?",
        "limit": 2,
    }
    res = client.post("/api/v1/search", json=search_payload)
    assert res.status_code == status.HTTP_200_OK

    data = res.json()
    assert data["query"] == search_payload["query"]
    assert data["total_results"] <= 2
    assert len(data["results"]) > 0

    top_result = data["results"][0]
    assert "chunk_id" in top_result
    assert top_result["document_id"] == doc_id
    assert top_result["page_number"] in [1, 2, 3]
    assert 0.0 <= top_result["score"] <= 1.0
    assert "text" in top_result


def test_semantic_search_with_document_filter(client, create_multipage_pdf):
    """Verify semantic search scoped to a specific document_id."""
    doc_a = _upload_test_pdf(client, create_multipage_pdf, ["Agreement A terms."])
    doc_b = _upload_test_pdf(client, create_multipage_pdf, ["Agreement B terms."])

    client.post(f"/api/v1/documents/{doc_a}/index")
    client.post(f"/api/v1/documents/{doc_b}/index")

    res = client.post(
        "/api/v1/search",
        json={"query": "Agreement terms", "document_id": doc_a, "limit": 5},
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    for item in data["results"]:
        assert item["document_id"] == doc_a


def test_search_query_validation(client):
    """Verify input validation on search request queries."""
    # Empty query
    res1 = client.post("/api/v1/search", json={"query": "", "limit": 5})
    assert res1.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Limit too high
    res2 = client.post("/api/v1/search", json={"query": "valid query", "limit": 100})
    assert res2.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Invalid document_id format
    res3 = client.post("/api/v1/search", json={"query": "valid query", "document_id": "not-a-uuid"})
    assert res3.status_code == status.HTTP_400_BAD_REQUEST


def test_ollama_unavailable_returns_503(client, create_multipage_pdf):
    """Verify that when Ollama is unreachable, the search and index APIs return 503 Service Unavailable."""
    doc_id = _upload_test_pdf(client, create_multipage_pdf)

    class FailingEmbeddingService:
        async def embed_query(self, query: str):
            raise OllamaConnectionError("Ollama daemon is down.")

        async def embed_documents(self, texts: list[str]):
            raise OllamaConnectionError("Ollama daemon is down.")

    app.dependency_overrides[get_embedding_service] = lambda: FailingEmbeddingService()

    try:
        # Index attempt
        res_idx = client.post(f"/api/v1/documents/{doc_id}/index")
        assert res_idx.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "ollama daemon is down" in res_idx.json()["detail"].lower()

        # Search attempt
        res_search = client.post("/api/v1/search", json={"query": "test query", "limit": 5})
        assert res_search.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "ollama daemon is down" in res_search.json()["detail"].lower()
    finally:
        # Clear override
        app.dependency_overrides.pop(get_embedding_service, None)
