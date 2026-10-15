"""Embedded LanceDB vector database service for document chunk storage and retrieval."""

import logging
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from app.core.config import Settings, get_settings
from app.core.errors import (
    DocumentAlreadyIndexedError,
    VectorStoreError,
)
from app.schemas.chunk import DocumentChunk
from app.schemas.search import SearchResultChunk

logger = logging.getLogger(__name__)

TABLE_NAME = "document_chunks"


class LanceDBVectorService:
    """Local-first embedded vector database using LanceDB."""

    def __init__(self, db_dir: Path, vector_dim: int = 768) -> None:
        self.db_dir = Path(db_dir)
        self.vector_dim = vector_dim
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_dir))
        self._schema = pa.schema([
            pa.field("vector", pa.list_(pa.float32(), self.vector_dim)),
            pa.field("chunk_id", pa.string()),
            pa.field("document_id", pa.string()),
            pa.field("filename", pa.string()),
            pa.field("page_number", pa.int32()),
            pa.field("chunk_index", pa.int32()),
            pa.field("text", pa.string()),
            pa.field("char_count", pa.int32()),
            pa.field("word_count", pa.int32()),
        ])

    def _get_or_create_table(self) -> Any:
        """Retrieve existing table or initialize with Arrow schema."""
        try:
            return self.db.open_table(TABLE_NAME)
        except Exception:
            return self.db.create_table(TABLE_NAME, schema=self._schema)

    def is_document_indexed(self, document_id: str) -> bool:
        """Check whether any chunks for the given document_id already exist."""
        try:
            table = self.db.open_table(TABLE_NAME)
        except Exception:
            return False

        try:
            matches = table.search().where(f"document_id = '{document_id}'").limit(1).to_list()
            return len(matches) > 0
        except Exception:
            return False

    def delete_document_chunks(self, document_id: str) -> None:
        """Remove all chunks associated with a specific document_id."""
        try:
            table = self.db.open_table(TABLE_NAME)
        except Exception:
            return

        try:
            table.delete(f"document_id = '{document_id}'")
            logger.info("Deleted chunks for document_id=%s from vector index", document_id)
        except Exception as exc:
            logger.warning("Could not delete chunks for document_id=%s: %s", document_id, exc)

    def index_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        reindex: bool = False,
    ) -> int:
        """Store chunk vectors and metadata into the local LanceDB table.

        Args:
            chunks: List of DocumentChunk instances.
            embeddings: Parallel list of embedding vectors.
            reindex: If True, overwrites existing document index. If False, raises error on duplicate.

        Returns:
            Number of indexed chunks.
        """
        if not chunks:
            return 0

        if len(chunks) != len(embeddings):
            raise VectorStoreError(
                f"Mismatch between chunks ({len(chunks)}) and embeddings ({len(embeddings)})."
            )

        document_id = chunks[0].document_id
        table = self._get_or_create_table()

        if self.is_document_indexed(document_id):
            if not reindex:
                raise DocumentAlreadyIndexedError(
                    f"Document '{document_id}' is already indexed in the vector database. "
                    "Use reindex=true to overwrite."
                )
            self.delete_document_chunks(document_id)

        records = []
        for chunk, emb in zip(chunks, embeddings):
            records.append({
                "vector": emb,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "char_count": chunk.char_count,
                "word_count": chunk.word_count,
            })

        table.add(records)
        logger.info("Indexed %d chunks for document_id=%s", len(records), document_id)
        return len(records)

    def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        document_id: str | None = None,
    ) -> list[SearchResultChunk]:
        """Perform nearest-neighbor vector search in the local LanceDB index.

        Args:
            query_vector: Dense embedding vector for the search query.
            limit: Maximum number of chunks to return.
            document_id: Optional document filter.

        Returns:
            List of SearchResultChunk ranked by relevance.
        """
        try:
            table = self.db.open_table(TABLE_NAME)
        except Exception:
            return []

        if table.count_rows() == 0:
            return []

        query_builder = table.search(query_vector).limit(limit)
        if document_id:
            query_builder = query_builder.where(f"document_id = '{document_id}'")

        raw_results = query_builder.to_list()
        results: list[SearchResultChunk] = []

        for r in raw_results:
            raw_dist = float(r.get("_distance", 0.0))
            score = round(1.0 / (1.0 + max(0.0, raw_dist)), 4)

            results.append(
                SearchResultChunk(
                    chunk_id=r["chunk_id"],
                    document_id=r["document_id"],
                    filename=r["filename"],
                    page_number=int(r["page_number"]),
                    chunk_index=int(r["chunk_index"]),
                    text=r["text"],
                    score=score,
                    distance=round(raw_dist, 4),
                )
            )

        return results


from fastapi import Depends


def get_vector_service(settings: Settings = Depends(get_settings)) -> LanceDBVectorService:
    """Dependency provider returning configured LanceDBVectorService instance."""
    return LanceDBVectorService(
        db_dir=settings.lancedb_dir,
        vector_dim=settings.embedding_dim,
    )

