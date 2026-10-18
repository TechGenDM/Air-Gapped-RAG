"""Automated integration and unit tests for citation-backed Q&A endpoint."""

from io import BytesIO
import uuid

from fastapi import status
import pytest

from app.core.errors import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
)
from app.main import app
from app.schemas.search import SearchResultChunk
from app.services.llm_service import (
    OllamaLLMService,
    get_llm_service,
)


def _upload_and_index_pdf(client, create_multipage_pdf) -> str:
    """Helper to upload and index a test PDF document."""
    pages = [
        "SECTION 1: Scope of Work and Deliverables.\nVendor shall deliver cloud-native components.",
        "SECTION 2: Term and Termination.\nEither party may terminate this agreement with 30 days written notice.",
        "SECTION 3: Governing Law and Dispute Resolution.\nThis Agreement is governed by Delaware law.",
    ]
    pdf_bytes = create_multipage_pdf(pages)
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract_agreement.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["document_id"]

    index_res = client.post(f"/api/v1/documents/{doc_id}/index")
    assert index_res.status_code == status.HTTP_200_OK
    return doc_id


def test_successful_answer_generation_with_citation(client, create_multipage_pdf):
    """Verify that asking a question retrieves context, generates an answer, and returns verified citations."""
    doc_id = _upload_and_index_pdf(client, create_multipage_pdf)

    res = client.post(
        "/api/v1/answer",
        json={
            "query": "What is the notice period for contract termination?",
            "document_id": doc_id,
            "limit": 3,
        },
    )
    assert res.status_code == status.HTTP_200_OK

    data = res.json()
    assert data["question"] == "What is the notice period for contract termination?"
    assert "30-day notice" in data["answer"]
    assert data["evidence_sufficient"] is True
    assert data["model"] == "gemma4:12b"
    assert data["elapsed_seconds"] >= 0.0

    # Validate citations
    assert len(data["sources"]) >= 1
    citation = data["sources"][0]
    assert citation["document_id"] == doc_id
    assert citation["filename"] == "contract_agreement.pdf"
    assert citation["page_number"] >= 1
    assert "terminate" in citation["excerpt"].lower() or "section" in citation["excerpt"].lower()


def test_insufficient_evidence_returns_not_found_in_records(client, create_multipage_pdf):
    """Verify that when evidence is insufficient, answer is 'Not found in records' and sources are empty."""
    doc_id = _upload_and_index_pdf(client, create_multipage_pdf)

    class InsufficientLLMMock:
        async def generate_answer(self, query: str, chunks: list) -> tuple[str, list, bool]:
            return "Not found in records", [], False

    app.dependency_overrides[get_llm_service] = lambda: InsufficientLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={
                "query": "What is the penalty for late cloud component delivery?",
                "document_id": doc_id,
            },
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["answer"] == "Not found in records"
        assert data["evidence_sufficient"] is False
        assert data["sources"] == []
    finally:
        del app.dependency_overrides[get_llm_service]


def test_empty_vector_search_results_returns_not_found_without_calling_llm(client):
    """Verify that if vector search returns no results, the API immediately returns 'Not found in records'."""
    random_doc_id = str(uuid.uuid4())
    res = client.post(
        "/api/v1/answer",
        json={
            "query": "Any query for a non-indexed document?",
            "document_id": random_doc_id,
        },
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["answer"] == "Not found in records"
    assert data["evidence_sufficient"] is False
    assert data["sources"] == []


def test_llm_hallucinated_source_rejection():
    """Unit test verifying OllamaLLMService strictly rejects source IDs not in retrieved chunks."""
    llm_service = OllamaLLMService(base_url="http://127.0.0.1:11434", model="gemma4:12b")

    chunk1 = SearchResultChunk(
        chunk_id="chunk_uuid_1",
        document_id="doc_1",
        filename="terms.pdf",
        page_number=2,
        chunk_index=0,
        text="Payment is due within thirty (30) days.",
        score=0.95,
        distance=0.05,
    )
    chunk2 = SearchResultChunk(
        chunk_id="chunk_uuid_2",
        document_id="doc_1",
        filename="terms.pdf",
        page_number=4,
        chunk_index=0,
        text="Governing jurisdiction is California.",
        score=0.85,
        distance=0.15,
    )

    _, source_map = llm_service._build_context_prompt([chunk1, chunk2])

    # Case 1: Model claims SOURCE_1 and a hallucinated SOURCE_99
    raw_response = {
        "message": {
            "content": '{"answer": "Payment is due in 30 days.", "used_source_ids": ["SOURCE_1", "SOURCE_99"], "evidence_sufficient": true}'
        }
    }
    answer, verified, sufficient = llm_service._parse_and_validate_response(
        raw_response, [chunk1, chunk2], source_map
    )
    assert answer == "Payment is due in 30 days."
    assert sufficient is True
    assert len(verified) == 1
    assert verified[0].chunk_id == "chunk_uuid_1"

    # Case 2: Model returns Markdown code-fenced JSON
    fenced_response = {
        "message": {
            "content": '```json\n{"answer": "Governing jurisdiction is California.", "used_source_ids": ["SOURCE_2"], "evidence_sufficient": true}\n```'
        }
    }
    answer, verified, sufficient = llm_service._parse_and_validate_response(
        fenced_response, [chunk1, chunk2], source_map
    )
    assert answer == "Governing jurisdiction is California."
    assert sufficient is True
    assert len(verified) == 1
    assert verified[0].chunk_id == "chunk_uuid_2"

    # Case 3: Model states Not found in records
    not_found_response = {
        "message": {
            "content": '{"answer": "Not found in records", "used_source_ids": [], "evidence_sufficient": false}'
        }
    }
    answer, verified, sufficient = llm_service._parse_and_validate_response(
        not_found_response, [chunk1, chunk2], source_map
    )
    assert answer == "Not found in records"
    assert sufficient is False
    assert verified == []

    # Case 4 (Regression): Model claims evidence sufficient but provides ONLY hallucinated source IDs
    all_hallucinated_response = {
        "message": {
            "content": '{"answer": "Acme was founded in 1890.", "used_source_ids": ["SOURCE_999", "SOURCE_XYZ"], "evidence_sufficient": true}'
        }
    }
    answer, verified, sufficient = llm_service._parse_and_validate_response(
        all_hallucinated_response, [chunk1, chunk2], source_map
    )
    assert answer == "Not found in records"
    assert sufficient is False
    assert verified == []

    # Case 5 (Regression): Model claims evidence sufficient but provides empty source IDs
    empty_sources_response = {
        "message": {
            "content": '{"answer": "Fabricated claim without sources.", "used_source_ids": [], "evidence_sufficient": true}'
        }
    }
    answer, verified, sufficient = llm_service._parse_and_validate_response(
        empty_sources_response, [chunk1, chunk2], source_map
    )
    assert answer == "Not found in records"
    assert sufficient is False
    assert verified == []

    # Case 6 (Regression): Model states Not found in records with trailing punctuation or phrasing variation
    punctuated_not_found = {
        "message": {
            "content": '{"answer": "Not found in records.", "used_source_ids": ["SOURCE_1"], "evidence_sufficient": true}'
        }
    }
    answer, verified, sufficient = llm_service._parse_and_validate_response(
        punctuated_not_found, [chunk1, chunk2], source_map
    )
    assert answer == "Not found in records"
    assert sufficient is False
    assert verified == []


def test_answer_api_zero_verified_sources_forces_not_found(client, create_multipage_pdf):
    """Verify that if LLM returns an answer with zero verified sources, endpoint forces 'Not found in records'."""
    doc_id = _upload_and_index_pdf(client, create_multipage_pdf)

    class UngroundedLLMMock:
        async def generate_answer(self, query: str, chunks: list) -> tuple[str, list, bool]:
            # Mock LLM returning text with empty verified source list
            return "Ungrounded answer text", [], True

    app.dependency_overrides[get_llm_service] = lambda: UngroundedLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={
                "query": "What is the penalty for late cloud component delivery?",
                "document_id": doc_id,
            },
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["answer"] == "Not found in records"
        assert data["evidence_sufficient"] is False
        assert data["sources"] == []
    finally:
        del app.dependency_overrides[get_llm_service]


def test_answer_api_ollama_unavailable_returns_503(client, create_multipage_pdf):
    """Verify that an Ollama connection error during Q&A generation returns 503 Service Unavailable."""
    doc_id = _upload_and_index_pdf(client, create_multipage_pdf)

    class FailingLLMMock:
        async def generate_answer(self, query: str, chunks: list):
            raise OllamaConnectionError("Ollama daemon unreachable")

    app.dependency_overrides[get_llm_service] = lambda: FailingLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={"query": "What is the scope?", "document_id": doc_id},
        )
        assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "unreachable" in res.json()["detail"].lower()
    finally:
        del app.dependency_overrides[get_llm_service]


def test_answer_api_ollama_model_not_found_returns_503(client, create_multipage_pdf):
    """Verify that a missing LLM model returns 503 Service Unavailable."""
    doc_id = _upload_and_index_pdf(client, create_multipage_pdf)

    class MissingModelLLMMock:
        async def generate_answer(self, query: str, chunks: list):
            raise OllamaModelNotFoundError("Model 'gemma4:12b' not found")

    app.dependency_overrides[get_llm_service] = lambda: MissingModelLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={"query": "What is the scope?", "document_id": doc_id},
        )
        assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "not found" in res.json()["detail"].lower()
    finally:
        del app.dependency_overrides[get_llm_service]


def test_answer_api_invalid_document_uuid_returns_400(client):
    """Verify that passing an invalid UUID format as document_id returns 400 Bad Request."""
    res = client.post(
        "/api/v1/answer",
        json={"query": "What is the termination clause?", "document_id": "malicious/path/traversal"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid document id" in res.json()["detail"].lower()


def test_answer_api_empty_query_returns_422(client):
    """Verify that empty or whitespace query returns 422 Unprocessable Entity."""
    res = client.post(
        "/api/v1/answer",
        json={"query": "    "},
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.anyio
async def test_ollama_llm_service_uses_configured_timeout_and_options(monkeypatch):
    """Verify OllamaLLMService configures timeout and options.num_predict in chat payload."""
    captured_kwargs = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            import httpx

            captured_kwargs["url"] = url
            captured_kwargs["payload"] = json
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": '{"answer": "Test answer", "used_source_ids": ["SOURCE_1"], "evidence_sufficient": true}'
                    }
                },
                request=httpx.Request("POST", url),
            )

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    service = OllamaLLMService(
        base_url="http://127.0.0.1:11434",
        model="gemma4:12b",
        timeout_seconds=120.0,
        num_predict=1024,
    )
    chunk = SearchResultChunk(
        chunk_id="chk1",
        document_id="doc1",
        filename="test.pdf",
        page_number=1,
        chunk_index=0,
        text="Sample text",
        score=0.9,
        distance=0.1,
    )
    answer, sources, suff = await service.generate_answer("What is this?", [chunk])
    assert answer == "Test answer"
    assert captured_kwargs["timeout"] == 120.0
    assert captured_kwargs["payload"]["think"] is False
    assert captured_kwargs["payload"]["options"]["num_predict"] == 1024
    assert captured_kwargs["payload"]["options"]["temperature"] == 0.0


@pytest.mark.anyio
async def test_ollama_llm_service_timeout_exception_handling(monkeypatch):
    """Verify OllamaLLMService raises OllamaConnectionError with actionable timeout message on httpx.TimeoutException."""

    class TimeoutClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            import httpx

            raise httpx.ReadTimeout("Read timed out after 120s")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", TimeoutClient)

    service = OllamaLLMService(
        base_url="http://127.0.0.1:11434",
        model="gemma4:12b",
        timeout_seconds=120.0,
        num_predict=1024,
    )
    chunk = SearchResultChunk(
        chunk_id="chk1",
        document_id="doc1",
        filename="test.pdf",
        page_number=1,
        chunk_index=0,
        text="Sample text",
        score=0.9,
        distance=0.1,
    )
    with pytest.raises(OllamaConnectionError) as exc_info:
        await service.generate_answer("Any query?", [chunk])

    error_msg = str(exc_info.value)
    assert "Timed out waiting for local Ollama LLM (gemma4:12b) after 120.0s" in error_msg
    assert "AIR_GAPPED_LLM_TIMEOUT_SECONDS" in error_msg


def test_answer_api_llm_timeout_returns_503(client, create_multipage_pdf):
    """Verify that when Ollama LLM times out during Q&A, the API returns 503 with timeout detail."""
    doc_id = _upload_and_index_pdf(client, create_multipage_pdf)

    class TimeoutLLMMock:
        async def generate_answer(self, query: str, chunks: list):
            raise OllamaConnectionError(
                "Timed out waiting for local Ollama LLM (gemma4:12b) after 120.0s."
            )

    app.dependency_overrides[get_llm_service] = lambda: TimeoutLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={"query": "What is the penalty?", "document_id": doc_id},
        )
        assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = res.json()
        assert "timed out waiting for local ollama llm" in data["detail"].lower()
        assert "120.0s" in data["detail"]
    finally:
        del app.dependency_overrides[get_llm_service]


def test_statutory_qualification_preservation_regression(client, create_multipage_pdf):
    """Verify that material statutory qualifications (written form, signature, authorized agent) are preserved in answer generation."""
    page_text = (
        "SECTION 25: Exceptions to Void Agreements.\n"
        "An agreement made without consideration is void unless:\n"
        "(1) it is expressed in writing and registered under the registration law on account of natural love and affection;\n"
        "(2) it is a promise to compensate a person who has already voluntarily done something for the promisor;\n"
        "(3) it is a promise, made in writing and signed by the person to be charged therewith or by an authorized agent, "
        "to pay wholly or in part a debt barred by the law of limitation."
    )
    pdf_bytes = create_multipage_pdf([page_text])
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("synthetic_statute.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["document_id"]

    index_res = client.post(f"/api/v1/documents/{doc_id}/index")
    assert index_res.status_code == status.HTTP_200_OK

    class QualifiedLLMMock:
        async def generate_answer(self, query: str, chunks: list) -> tuple[str, list, bool]:
            assert len(chunks) >= 1
            answer_text = (
                "An agreement without consideration is valid under Section 25 if: "
                "1. It is in writing and registered based on natural love and affection; "
                "2. It is a promise to compensate voluntary past acts; "
                "3. It is a promise, made in writing and signed by the debtor or their authorized agent, "
                "to pay a time-barred debt."
            )
            return answer_text, [chunks[0]], True

    app.dependency_overrides[get_llm_service] = lambda: QualifiedLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={
                "query": "Under what specific exceptions is an agreement made without consideration considered valid under Section 25?",
                "document_id": doc_id,
            },
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["evidence_sufficient"] is True
        ans_lower = data["answer"].lower()
        # Ensure material statutory qualifications are preserved
        assert "writing" in ans_lower
        assert "signed" in ans_lower
        assert "agent" in ans_lower
        assert "time-barred" in ans_lower or "limitation" in ans_lower
        assert len(data["sources"]) == 1
        assert data["sources"][0]["page_number"] == 1
        assert "signed" in data["sources"][0]["excerpt"].lower()
    finally:
        del app.dependency_overrides[get_llm_service]


def test_cross_page_clause_continuation_retrieval_and_answer(client, create_multipage_pdf):
    """Verify that a multi-page PDF with a clause split across pages 1 and 2 retrieves both pages and cites them."""
    page1_text = (
        "SECTION 25: Exceptions to Void Agreements.\n"
        "An agreement made without consideration is void unless:\n"
        "(1) it is expressed in writing and registered on account of natural love and affection;\n"
        "(2) it is a promise to compensate voluntary past acts; or unless;"
    )
    page2_text = (
        "(3) it is a promise, made in writing and signed by the debtor or by an authorized agent, "
        "to pay wholly or in part a debt barred by the law of limitation.\n"
        "In any of these cases, such an agreement is a contract."
    )
    pdf_bytes = create_multipage_pdf([page1_text, page2_text])
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("split_statute.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["document_id"]

    index_res = client.post(f"/api/v1/documents/{doc_id}/index")
    assert index_res.status_code == status.HTTP_200_OK

    captured_chunks = []

    class RealRetrievalLLMMock:
        async def generate_answer(self, query: str, chunks: list) -> tuple[str, list, bool]:
            nonlocal captured_chunks
            captured_chunks = list(chunks)
            # The LLM receives both chunks from the expanded retrieval pipeline
            answer_text = (
                "Under Section 25, an agreement without consideration is valid in three exceptions: "
                "1. Expressed in writing and registered based on natural love and affection; "
                "2. Promise to compensate voluntary past acts; "
                "3. Promise made in writing and signed by the debtor or by an authorized agent to pay a time-barred debt."
            )
            return answer_text, chunks, True

    app.dependency_overrides[get_llm_service] = lambda: RealRetrievalLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={
                "query": "Under what specific exceptions is an agreement made without consideration considered valid under Section 25?",
                "document_id": doc_id,
                "limit": 1,  # Initial limit is 1, so continuation expansion MUST trigger to reach page 2
            },
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["evidence_sufficient"] is True

        # Verify that the pipeline actually delivered both page 1 and page 2 to the LLM
        pages_supplied = [c.page_number for c in captured_chunks]
        assert 1 in pages_supplied
        assert 2 in pages_supplied

        # Verify citations
        assert len(data["sources"]) == 2
        assert data["sources"][0]["page_number"] == 1
        assert data["sources"][1]["page_number"] == 2
        assert "signed by the debtor or by an authorized agent" in data["sources"][1]["excerpt"]

        # Verify answer preserved all material qualifications
        ans_lower = data["answer"].lower()
        assert "writing" in ans_lower
        assert "signed" in ans_lower
        assert "agent" in ans_lower
    finally:
        del app.dependency_overrides[get_llm_service]


def test_cross_page_missing_evidence_safe_abstention(client, create_multipage_pdf):
    """Verify that an absent topic on a multi-page PDF strictly returns safe abstention without fabricated citations."""
    page1_text = "SECTION 25: Agreement without consideration is void unless registered on natural love."
    page2_text = "SECTION 26: Agreement in restraint of marriage of any person other than a minor is void."
    pdf_bytes = create_multipage_pdf([page1_text, page2_text])

    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("statute_test.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    doc_id = upload_res.json()["document_id"]
    client.post(f"/api/v1/documents/{doc_id}/index")

    class AbstainingLLMMock:
        async def generate_answer(self, query: str, chunks: list) -> tuple[str, list, bool]:
            return "Not found in records", [], False

    app.dependency_overrides[get_llm_service] = lambda: AbstainingLLMMock()

    try:
        res = client.post(
            "/api/v1/answer",
            json={
                "query": "What is the penalty for maritime salvage under admiralty law?",
                "document_id": doc_id,
            },
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["answer"] == "Not found in records"
        assert data["evidence_sufficient"] is False
        assert data["sources"] == []
    finally:
        del app.dependency_overrides[get_llm_service]
