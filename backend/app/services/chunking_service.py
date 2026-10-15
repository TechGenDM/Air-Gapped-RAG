"""Page-aware document chunking service preserving exact page boundaries."""

import re

from app.schemas.chunk import DocumentChunk
from app.schemas.document import ExtractedPage


def split_text_into_chunks(
    text: str,
    document_id: str,
    filename: str,
    page_number: int,
    target_words: int = 400,
    overlap_words: int = 50,
) -> list[DocumentChunk]:
    """Split text from a single page into overlapping chunks without crossing page boundaries.

    Args:
        text: Plain text from a single physical page.
        document_id: Parent document identifier.
        filename: Document source filename.
        page_number: 1-indexed physical page number.
        target_words: Target word count per chunk (~400-500 words / 500-650 tokens).
        overlap_words: Number of overlapping words between consecutive chunks.

    Returns:
        List of DocumentChunk instances with strictly preserved page_number.
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        return []

    words = cleaned_text.split()
    total_words = len(words)

    # If the page content fits within the target size, keep it as a single chunk
    if total_words <= target_words:
        return [
            DocumentChunk(
                chunk_id=f"{document_id}_p{page_number}_c0",
                document_id=document_id,
                filename=filename,
                page_number=page_number,
                chunk_index=0,
                text=cleaned_text,
                char_count=len(cleaned_text),
                word_count=total_words,
            )
        ]

    # Try natural paragraph-based splitting first
    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned_text) if p.strip()]
    chunks: list[DocumentChunk] = []

    # If paragraph splitting yields clean blocks
    if len(raw_paragraphs) > 1:
        current_paragraphs: list[str] = []
        current_word_count = 0
        chunk_idx = 0

        for para in raw_paragraphs:
            para_words = len(para.split())

            if current_paragraphs and (current_word_count + para_words > target_words):
                chunk_text = "\n\n".join(current_paragraphs)
                chunk_words = len(chunk_text.split())
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{document_id}_p{page_number}_c{chunk_idx}",
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                        char_count=len(chunk_text),
                        word_count=chunk_words,
                    )
                )
                chunk_idx += 1

                # Carry over last paragraph for overlap if it doesn't exceed target
                if para_words < target_words and len(current_paragraphs[-1].split()) <= overlap_words * 2:
                    current_paragraphs = [current_paragraphs[-1], para]
                    current_word_count = len(current_paragraphs[0].split()) + para_words
                else:
                    current_paragraphs = [para]
                    current_word_count = para_words
            else:
                current_paragraphs.append(para)
                current_word_count += para_words

        if current_paragraphs:
            chunk_text = "\n\n".join(current_paragraphs)
            chunk_words = len(chunk_text.split())
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}_p{page_number}_c{chunk_idx}",
                    document_id=document_id,
                    filename=filename,
                    page_number=page_number,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    char_count=len(chunk_text),
                    word_count=chunk_words,
                )
            )
        return chunks

    # Fallback for monolithic text blocks without double newlines: sliding word window
    step = max(1, target_words - overlap_words)
    chunk_idx = 0
    for start_idx in range(0, total_words, step):
        end_idx = min(start_idx + target_words, total_words)
        chunk_words_slice = words[start_idx:end_idx]
        chunk_text = " ".join(chunk_words_slice)

        chunks.append(
            DocumentChunk(
                chunk_id=f"{document_id}_p{page_number}_c{chunk_idx}",
                document_id=document_id,
                filename=filename,
                page_number=page_number,
                chunk_index=chunk_idx,
                text=chunk_text,
                char_count=len(chunk_text),
                word_count=len(chunk_words_slice),
            )
        )
        chunk_idx += 1

        if end_idx >= total_words:
            break

    return chunks


def chunk_document_pages(
    pages: list[ExtractedPage],
    document_id: str,
    filename: str,
    target_words: int = 400,
    overlap_words: int = 50,
) -> list[DocumentChunk]:
    """Chunk all pages of a document while strictly preserving individual physical page boundaries.

    Args:
        pages: Extracted pages with 1-indexed page_number.
        document_id: Parent document UUID.
        filename: Document source filename.
        target_words: Target word count per chunk.
        overlap_words: Overlapping word count between chunks on the same page.

    Returns:
        Flat list of DocumentChunk instances. Blank pages produce no chunks.
    """
    all_chunks: list[DocumentChunk] = []

    for page in pages:
        page_chunks = split_text_into_chunks(
            text=page.text,
            document_id=document_id,
            filename=filename,
            page_number=page.page_number,
            target_words=target_words,
            overlap_words=overlap_words,
        )
        all_chunks.extend(page_chunks)

    return all_chunks
