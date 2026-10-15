"""Local embedding service using Ollama and nomic-embed-text."""

import asyncio
import logging
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
)

logger = logging.getLogger(__name__)


class EmbeddingServiceProtocol(Protocol):
    """Protocol for embedding providers, enabling test mocking."""

    async def embed_query(self, query: str) -> list[float]:
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...


class OllamaEmbeddingService:
    """Local embedding generator communicating strictly with local Ollama API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "nomic-embed-text",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds

    async def embed_query(self, query: str) -> list[float]:
        """Generate a dense embedding vector for a single query string."""
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Query string cannot be empty.")

        vectors = await self._call_ollama_embed(clean_query)
        if not vectors or not isinstance(vectors[0], list):
            raise OllamaError("Ollama /api/embed did not return a valid embedding vector.")
        return vectors[0]

    async def embed_documents(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        """Generate dense embeddings for a list of text chunks with batching."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_vectors = await self._call_ollama_embed(batch)
            if len(batch_vectors) != len(batch):
                raise OllamaError(
                    f"Ollama returned {len(batch_vectors)} embeddings for a batch of {len(batch)} items."
                )
            all_embeddings.extend(batch_vectors)

        return all_embeddings

    async def _call_ollama_embed(self, input_data: str | list[str]) -> list[list[float]]:
        """Make HTTP request to local Ollama /api/embed endpoint."""
        url = f"{self.base_url}/api/embed"
        payload = {
            "model": self.model,
            "input": input_data,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.error("Failed to connect to local Ollama at %s: %s", self.base_url, exc)
            raise OllamaConnectionError(
                f"Cannot connect to local Ollama service at {self.base_url}. Ensure the Ollama daemon is running."
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error("Timeout connecting to Ollama at %s: %s", self.base_url, exc)
            raise OllamaConnectionError(
                f"Timed out waiting for local Ollama embeddings after {self.timeout}s."
            ) from exc
        except Exception as exc:
            logger.error("Unexpected error contacting Ollama at %s: %s", self.base_url, exc)
            raise OllamaError(f"Error communicating with local Ollama: {exc}") from exc

        if res.status_code == 404 or (not res.is_success and "not found" in res.text.lower()):
            raise OllamaModelNotFoundError(
                f"Embedding model '{self.model}' not found in local Ollama. Please run 'ollama pull {self.model}'."
            )

        if not res.is_success:
            raise OllamaError(
                f"Ollama embedding request failed with HTTP {res.status_code}: {res.text}"
            )

        data = res.json()
        embeddings = data.get("embeddings")
        if embeddings is not None and isinstance(embeddings, list):
            return embeddings

        # Fallback for transitional endpoints providing legacy single-embedding format
        legacy_embedding = data.get("embedding")
        if legacy_embedding and isinstance(legacy_embedding, list):
            return [legacy_embedding]

        raise OllamaError("Ollama response did not contain valid embedding vectors.")


from fastapi import Depends


def get_embedding_service(
    settings: Settings = Depends(get_settings),
) -> EmbeddingServiceProtocol:
    """Dependency provider returning configured OllamaEmbeddingService."""
    return OllamaEmbeddingService(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
        timeout_seconds=settings.embedding_timeout_seconds,
    )

