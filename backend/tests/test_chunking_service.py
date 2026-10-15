"""Unit tests for page-aware document chunking service."""

from app.schemas.document import ExtractedPage
from app.services.chunking_service import (
    chunk_document_pages,
    split_text_into_chunks,
)


def test_chunk_single_page_short_text():
    """Verify that a page with short text produces a single chunk with exact metadata."""
    text = "Clause 1: Confidentiality obligation between Party A and Party B."
    chunks = split_text_into_chunks(
        text=text,
        document_id="doc-123",
        filename="contract.pdf",
        page_number=1,
        target_words=400,
        overlap_words=50,
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == "doc-123_p1_c0"
    assert chunk.document_id == "doc-123"
    assert chunk.filename == "contract.pdf"
    assert chunk.page_number == 1
    assert chunk.chunk_index == 0
    assert chunk.text == text
    assert chunk.char_count == len(text)
    assert chunk.word_count == len(text.split())


def test_chunk_multi_page_boundary_preservation():
    """Verify that text from different physical pages is NEVER merged into one chunk."""
    pages = [
        ExtractedPage(
            page_number=1,
            text="Page one contains the preamble and definitions of the master agreement.",
            char_count=73,
            word_count=11,
            has_images=False,
        ),
        ExtractedPage(
            page_number=2,
            text="Page two contains payment terms, billing cycles, and net 30 payment schedules.",
            char_count=82,
            word_count=12,
            has_images=False,
        ),
        ExtractedPage(
            page_number=3,
            text="Page three contains termination for convenience clauses and governing law.",
            char_count=76,
            word_count=10,
            has_images=False,
        ),
    ]

    chunks = chunk_document_pages(
        pages=pages,
        document_id="doc-456",
        filename="service_agreement.pdf",
        target_words=400,
        overlap_words=50,
    )

    assert len(chunks) == 3

    # Check Page 1 chunk
    assert chunks[0].page_number == 1
    assert "preamble and definitions" in chunks[0].text
    assert "payment terms" not in chunks[0].text

    # Check Page 2 chunk
    assert chunks[1].page_number == 2
    assert "payment terms" in chunks[1].text
    assert "termination" not in chunks[1].text

    # Check Page 3 chunk
    assert chunks[2].page_number == 3
    assert "termination for convenience" in chunks[2].text
    assert "preamble" not in chunks[2].text


def test_chunking_blank_and_whitespace_pages():
    """Verify that blank pages are safely handled and produce 0 chunks."""
    pages = [
        ExtractedPage(page_number=1, text="First page content.", char_count=19, word_count=3, has_images=False),
        ExtractedPage(page_number=2, text="   \n\n  ", char_count=6, word_count=0, has_images=False),
        ExtractedPage(page_number=3, text="Third page content.", char_count=19, word_count=3, has_images=False),
    ]

    chunks = chunk_document_pages(pages, "doc-789", "doc.pdf")
    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 3


def test_empty_document_produces_zero_chunks():
    """Verify that an empty list of pages produces an empty list of chunks."""
    assert chunk_document_pages([], "doc-000", "empty.pdf") == []


def test_long_page_splits_with_overlap():
    """Verify that large pages split into multiple chunks with sequential indices and overlap."""
    # Generate 15 distinct paragraphs, ~60 words each (total ~900 words)
    paragraphs = [
        f"Paragraph {i}: " + ("The quick brown fox jumps over the lazy dog. " * 6)
        for i in range(1, 16)
    ]
    long_text = "\n\n".join(paragraphs)

    chunks = split_text_into_chunks(
        text=long_text,
        document_id="doc-long",
        filename="long.pdf",
        page_number=5,
        target_words=200,
        overlap_words=40,
    )

    assert len(chunks) > 1

    # Verify all chunks retain page_number=5 and sequential chunk_index
    for idx, chunk in enumerate(chunks):
        assert chunk.page_number == 5
        assert chunk.chunk_index == idx
        assert chunk.chunk_id == f"doc-long_p5_c{idx}"
        assert chunk.word_count > 0
