"""Embedded LanceDB vector database service for document chunk storage and retrieval."""

import logging
import math
from pathlib import Path
import re
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

    def expand_continuation_chunks(
        self,
        chunks: list[SearchResultChunk],
        query: str = "",
        query_vector: list[float] | None = None,
        max_total_chunks: int = 5,
    ) -> list[SearchResultChunk]:
        """Expand retrieved candidate chunks with adjacent continuation chunks when a clause spans boundaries.

        Args:
            chunks: Ranked candidate chunks from initial vector search.
            query: User query string.
            query_vector: Dense embedding vector for relevance evaluation.
            max_total_chunks: Upper bound on total chunks to maintain bounded context and fast inference.

        Returns:
            Deduplicated list of chunks preserving original IDs and physical page numbers.
        """
        if not chunks or len(chunks) >= max_total_chunks:
            return chunks

        try:
            table = self.db.open_table(TABLE_NAME)
        except Exception:
            return chunks

        expanded: list[SearchResultChunk] = []
        seen_ids: set[str] = set()

        for chunk in chunks:
            if chunk.chunk_id not in seen_ids:
                expanded.append(chunk)
                seen_ids.add(chunk.chunk_id)

            if len(expanded) >= max_total_chunks:
                break

            # Only inspect continuation if chunk exhibits open-ended or clause-boundary characteristics
            if not _is_continuation_candidate(chunk.text):
                continue

            # Query adjacent chunks from the same document on current page and next page
            try:
                raw_adjacent = (
                    table.search()
                    .where(
                        f"document_id = '{chunk.document_id}' AND page_number IN ({chunk.page_number}, {chunk.page_number + 1})"
                    )
                    .to_list()
                )
            except Exception:
                continue

            # Sort candidate adjacent chunks chronologically by (page_number, chunk_index)
            raw_adjacent.sort(key=lambda x: (x["page_number"], x["chunk_index"]))

            for candidate in raw_adjacent:
                cand_id = candidate["chunk_id"]
                cand_page = candidate["page_number"]
                cand_idx = candidate["chunk_index"]
                cand_text = candidate["text"]

                # Skip already included chunks
                if cand_id in seen_ids:
                    continue

                # Skip chunks before or identical to current chunk
                if (cand_page, cand_idx) <= (chunk.page_number, chunk.chunk_index):
                    continue

                # Skip non-substantive chunks (e.g. isolated page number headers like '18')
                if len(cand_text.strip()) < 30 or len(cand_text.split()) < 5:
                    continue

                # Strictly verify relevance: do NOT assume every next page or chunk is relevant
                cand_vec = candidate.get("vector")
                if _check_continuation_relevance(
                    parent_text=chunk.text,
                    candidate_text=cand_text,
                    query=query,
                    query_vec=query_vector,
                    candidate_vec=cand_vec,
                ):
                    dist = (
                        math.sqrt(sum((q - c) ** 2 for q, c in zip(query_vector, cand_vec)))
                        if query_vector and cand_vec
                        else float(candidate.get("_distance", chunk.distance))
                    )
                    score = round(1.0 / (1.0 + max(0.0, dist)), 4)

                    expanded.append(
                        SearchResultChunk(
                            chunk_id=cand_id,
                            document_id=candidate["document_id"],
                            filename=candidate["filename"],
                            page_number=int(cand_page),
                            chunk_index=int(cand_idx),
                            text=cand_text,
                            score=score,
                            distance=round(dist, 4),
                        )
                    )
                    seen_ids.add(cand_id)
                    # Expand at most one continuation per candidate chunk to stay bounded
                    break

        return expanded


def _is_continuation_candidate(text: str) -> bool:
    """Check if chunk text indicates a clause or sentence continuing across a boundary."""
    stripped = text.strip()
    if not stripped:
        return False
    # Ends with unfinished punctuation
    if stripped.endswith((";", ":", ",", "—", "-", "(", "[", "...")):
        return True
    # Ends with trailing conjunction or proviso words
    last_word = re.findall(r"[a-zA-Z]+", stripped)
    if last_word and last_word[-1].lower() in {
        "unless", "or", "and", "provided", "except", "namely", "including",
        "that", "where", "if", "by", "with", "without", "to"
    }:
        return True
    # Does not end with terminal punctuation
    if not stripped.endswith((".", "!", "?", '"', "'", ")", "]")):
        return True
    # Contains unclosed numbered list like (1) ... (2) ...
    if re.search(r"\([0-9]{1,2}\)[^(]+$", stripped):
        return True
    return False


def _check_continuation_relevance(
    parent_text: str,
    candidate_text: str,
    query: str,
    query_vec: list[float] | None = None,
    candidate_vec: list[float] | None = None,
) -> bool:
    """Verify that a candidate continuation chunk is genuinely related to parent and query."""
    cand_stripped = candidate_text.strip()

    # 1. Structural list continuation (e.g. parent ends with (2), candidate starts with (3))
    parent_markers = re.findall(r"\(([0-9]{1,2}|[a-zA-Z])\)", parent_text)
    if parent_markers:
        last_m = parent_markers[-1]
        if last_m.isdigit():
            next_m = f"({int(last_m) + 1})"
            if cand_stripped.startswith(next_m):
                return True
        elif len(last_m) == 1 and last_m.isalpha():
            next_m = f"({chr(ord(last_m) + 1)})"
            if cand_stripped.startswith(next_m):
                return True

    # 2. Query / parent topical keyword overlap
    stopwords = {
        "what", "under", "which", "where", "when", "is", "an", "a", "the",
        "made", "considered", "this", "that", "for", "of", "in", "on", "to", "by", "are"
    }
    q_words = {w.lower() for w in re.findall(r"[a-zA-Z]{3,}", query) if w.lower() not in stopwords}
    p_words = {w.lower() for w in re.findall(r"[a-zA-Z]{3,}", parent_text) if w.lower() not in stopwords}
    cand_words = {w.lower() for w in re.findall(r"[a-zA-Z]{3,}", candidate_text)}

    query_overlap = q_words & cand_words
    parent_overlap = p_words & cand_words

    # Must have either query keyword overlap or strong topical continuation from parent clause
    if len(query_overlap) >= 1 or len(parent_overlap) >= 3:
        if query_vec and candidate_vec:
            dist = math.sqrt(sum((q - c) ** 2 for q, c in zip(query_vec, candidate_vec)))
            return dist <= 0.85
        return True

    return False


from fastapi import Depends


def get_vector_service(settings: Settings = Depends(get_settings)) -> LanceDBVectorService:
    """Dependency provider returning configured LanceDBVectorService instance."""
    return LanceDBVectorService(
        db_dir=settings.lancedb_dir,
        vector_dim=settings.embedding_dim,
    )

