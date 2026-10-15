"""Unit tests for OllamaEmbeddingService and /api/embed compatibility."""

import httpx
import pytest

from app.core.errors import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
)
from app.services.embedding_service import OllamaEmbeddingService


@pytest.mark.anyio
async def test_embed_query_successful_api_embed(monkeypatch):
    """Verify embed_query correctly calls /api/embed and unpacks embeddings[0]."""
    service = OllamaEmbeddingService(base_url="http://127.0.0.1:11434", model="nomic-embed-text")

    async def mock_post(self, url, json=None):
        assert "/api/embed" in url
        assert json["model"] == "nomic-embed-text"
        assert json["input"] == "What is the jurisdiction?"
        return httpx.Response(
            status_code=200,
            json={"model": "nomic-embed-text", "embeddings": [[0.1, 0.2, 0.3]]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    vec = await service.embed_query("What is the jurisdiction?")
    assert vec == [0.1, 0.2, 0.3]


@pytest.mark.anyio
async def test_embed_documents_batching_api_embed(monkeypatch):
    """Verify embed_documents sends batches to /api/embed and preserves order."""
    service = OllamaEmbeddingService(base_url="http://127.0.0.1:11434", model="nomic-embed-text")

    call_count = 0

    async def mock_post(self, url, json=None):
        nonlocal call_count
        call_count += 1
        assert "/api/embed" in url
        assert isinstance(json["input"], list)
        # Return parallel dummy vectors of length 3
        dummy_vectors = [[float(i), float(i + 1), float(i + 2)] for i in range(len(json["input"]))]
        return httpx.Response(
            status_code=200,
            json={"model": "nomic-embed-text", "embeddings": dummy_vectors},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    texts = [f"Chunk number {i}" for i in range(5)]
    results = await service.embed_documents(texts, batch_size=2)
    assert len(results) == 5
    assert call_count == 3  # 5 items with batch_size 2 -> 3 calls (2, 2, 1)


@pytest.mark.anyio
async def test_embed_fallback_legacy_embedding_key(monkeypatch):
    """Verify transitional response with legacy 'embedding' single vector is supported."""
    service = OllamaEmbeddingService(base_url="http://127.0.0.1:11434", model="nomic-embed-text")

    async def mock_post(self, url, json=None):
        return httpx.Response(
            status_code=200,
            json={"model": "nomic-embed-text", "embedding": [0.8, 0.9]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    vec = await service.embed_query("Query string")
    assert vec == [0.8, 0.9]


@pytest.mark.anyio
async def test_embed_empty_query_raises_value_error():
    """Verify empty or whitespace query raises ValueError without network call."""
    service = OllamaEmbeddingService()
    with pytest.raises(ValueError, match="cannot be empty"):
        await service.embed_query("   ")


@pytest.mark.anyio
async def test_embed_documents_empty_returns_empty_list():
    """Verify passing an empty list of texts returns empty list immediately."""
    service = OllamaEmbeddingService()
    res = await service.embed_documents([])
    assert res == []


@pytest.mark.anyio
async def test_embed_model_not_found_raises_error(monkeypatch):
    """Verify 404 model not found raises OllamaModelNotFoundError."""
    service = OllamaEmbeddingService(model="nonexistent-model")

    async def mock_post(self, url, json=None):
        return httpx.Response(
            status_code=404,
            json={"error": "model 'nonexistent-model' not found"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(OllamaModelNotFoundError, match="not found in local Ollama"):
        await service.embed_query("Test query")


@pytest.mark.anyio
async def test_embed_connection_error_raises_ollama_connection_error(monkeypatch):
    """Verify network connection failure raises OllamaConnectionError."""
    service = OllamaEmbeddingService()

    async def mock_post(self, url, json=None):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(OllamaConnectionError, match="Cannot connect to local Ollama"):
        await service.embed_query("Test query")


@pytest.mark.anyio
async def test_embed_timeout_raises_ollama_connection_error(monkeypatch):
    """Verify request timeout raises OllamaConnectionError."""
    service = OllamaEmbeddingService()

    async def mock_post(self, url, json=None):
        raise httpx.TimeoutException("Read timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(OllamaConnectionError, match="Timed out waiting for local Ollama"):
        await service.embed_query("Test query")
