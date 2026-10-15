"""Unit tests for PDF extraction service."""

import pytest

from app.core.errors import (
    CorruptPDFError,
    EmptyPDFError,
    PasswordProtectedPDFError,
)
from app.services.pdf_service import extract_pdf_pages


def test_multipage_pdf_exact_page_to_text_mapping(create_multipage_pdf):
    """Verify that multi-page PDFs extract with exact 1-indexed numbering and page content."""
    pages_content = [
        "Master Services Agreement between Alpha Corp and Beta LLC.\nEffective date: Oct 1, 2026.",
        "Section 2: Payment Terms and Milestones.\nAll invoices payable within 30 days.",
        "Section 3: Intellectual Property and Ownership.\nAll deliverables are work made for hire.",
        "Section 4: Limitation of Liability and Indemnification.\nNeither party liable for consequential damages.",
        "Section 5: Signatures and Governing Law.\nGoverned under the laws of California.",
    ]

    pdf_bytes = create_multipage_pdf(pages_content)
    result = extract_pdf_pages(pdf_bytes)

    # 1. Verify total page count
    assert result.total_pages == 5
    assert len(result.pages) == 5

    # 2. Verify strict 1-indexed page numbering and content mapping
    for idx, expected_text in enumerate(pages_content):
        page = result.pages[idx]
        expected_page_number = idx + 1

        assert page.page_number == expected_page_number
        assert page.text == expected_text
        assert page.char_count == len(expected_text)
        assert page.word_count == len(expected_text.split())
        assert page.has_images is False

    # 3. Direct checks on boundary pages
    assert result.pages[0].page_number == 1
    assert "Master Services Agreement" in result.pages[0].text
    assert result.pages[4].page_number == 5
    assert "Signatures and Governing Law" in result.pages[4].text


def test_pdf_with_embedded_image(create_image_pdf):
    """Verify that embedded raster/vector images are detected correctly."""
    pdf_bytes = create_image_pdf("Architecture diagram and contract specifications.")
    result = extract_pdf_pages(pdf_bytes)

    assert result.total_pages == 1
    page = result.pages[0]
    assert page.page_number == 1
    assert "Architecture diagram" in page.text
    assert page.has_images is True


def test_pdf_with_blank_pages(create_multipage_pdf):
    """Verify that blank pages in a document are preserved in sequence without error."""
    pages_content = [
        "First page content with agreement terms.",
        "",  # Intentionally blank page
        "Third page content with final schedules.",
    ]

    pdf_bytes = create_multipage_pdf(pages_content)
    result = extract_pdf_pages(pdf_bytes)

    assert result.total_pages == 3
    assert len(result.pages) == 3

    # Check page 1
    assert result.pages[0].page_number == 1
    assert result.pages[0].char_count > 0

    # Check blank page 2
    assert result.pages[1].page_number == 2
    assert result.pages[1].text == ""
    assert result.pages[1].char_count == 0
    assert result.pages[1].word_count == 0
    assert result.pages[1].has_images is False

    # Check page 3
    assert result.pages[2].page_number == 3
    assert "Third page content" in result.pages[2].text


def test_empty_bytes_raises_empty_pdf_error():
    """Verify that empty bytes trigger EmptyPDFError."""
    with pytest.raises(EmptyPDFError, match="empty"):
        extract_pdf_pages(b"")


def test_corrupt_bytes_raises_corrupt_pdf_error():
    """Verify that malformed or non-PDF bytes trigger CorruptPDFError."""
    with pytest.raises(CorruptPDFError, match="Failed to parse"):
        extract_pdf_pages(b"This is not a valid PDF file at all.")


def test_corrupt_truncated_header_raises_corrupt_pdf_error():
    """Verify that broken PDF headers trigger CorruptPDFError."""
    with pytest.raises(CorruptPDFError, match="Failed to parse"):
        extract_pdf_pages(b"%PDF-1.7 corrupt trailing garbage without trailer")


def test_non_bytes_input_raises_corrupt_pdf_error():
    """Verify that passing non-bytes input raises CorruptPDFError."""
    with pytest.raises(CorruptPDFError, match="must be provided as bytes"):
        extract_pdf_pages("string instead of bytes")  # type: ignore


def test_password_protected_pdf_raises_error(create_encrypted_pdf):
    """Verify that password-protected PDFs raise PasswordProtectedPDFError."""
    encrypted_bytes = create_encrypted_pdf(
        text="Confidential executive compensation contract",
        password="TopSecretPassword2026",
    )

    with pytest.raises(PasswordProtectedPDFError, match="password-protected"):
        extract_pdf_pages(encrypted_bytes)


def test_bytearray_input_support(create_multipage_pdf):
    """Verify that bytearray instances are supported identically to bytes."""
    raw_bytes = create_multipage_pdf(["Bytearray test content"])
    result = extract_pdf_pages(bytearray(raw_bytes))

    assert result.total_pages == 1
    assert result.pages[0].page_number == 1
    assert "Bytearray test content" in result.pages[0].text


def test_scanned_image_only_page_triggers_ocr():
    """Verify that a page containing text rendered as a raster image triggers OCR fallback."""
    import pymupdf

    # 1. Render synthetic text to an image pixmap
    doc_render = pymupdf.open()
    p_render = doc_render.new_page()
    p_render.insert_text((50, 72), "SALIENT EVALUATION CLAUSE AND PROTOCOLS", fontsize=18)
    pix = p_render.get_pixmap(dpi=150)
    doc_render.close()

    # 2. Embed the raster pixmap into a new PDF with zero digital text
    doc_scanned = pymupdf.open()
    p_scanned = doc_scanned.new_page()
    p_scanned.insert_image(p_scanned.rect, pixmap=pix)
    pdf_bytes = doc_scanned.tobytes()
    doc_scanned.close()

    result = extract_pdf_pages(pdf_bytes)
    assert result.total_pages == 1
    page = result.pages[0]

    assert page.page_number == 1
    assert page.has_images is True
    assert page.ocr_applied is True
    assert "SALIENT EVALUATION CLAUSE" in page.text
    assert page.word_count >= 4
    assert page.char_count > 20


def test_image_without_text_does_not_falsely_extract_text(create_image_pdf):
    """Verify that an embedded graphic without readable text does not falsely produce words."""
    pdf_bytes = create_image_pdf(with_text="")
    result = extract_pdf_pages(pdf_bytes)

    assert result.total_pages == 1
    page = result.pages[0]
    assert page.has_images is True
    assert page.text == ""
    assert page.ocr_applied is False
    assert page.word_count == 0
    assert page.char_count == 0


def test_ocr_failure_falls_back_gracefully_without_exception(monkeypatch):
    """Verify that if OCR fails or encounters an error, the extraction continues gracefully."""
    import pymupdf

    # Create synthetic scanned image
    doc_render = pymupdf.open()
    p_render = doc_render.new_page()
    p_render.insert_text((50, 72), "CONFIDENTIAL CLAUSE", fontsize=18)
    pix = p_render.get_pixmap(dpi=150)
    doc_render.close()

    doc_scanned = pymupdf.open()
    p_scanned = doc_scanned.new_page()
    p_scanned.insert_image(p_scanned.rect, pixmap=pix)
    pdf_bytes = doc_scanned.tobytes()
    doc_scanned.close()

    def mock_get_textpage_ocr(*args, **kwargs):
        raise RuntimeError("Tesseract library initialization failed")

    monkeypatch.setattr(pymupdf.Page, "get_textpage_ocr", mock_get_textpage_ocr)

    result = extract_pdf_pages(pdf_bytes)
    assert result.total_pages == 1
    page = result.pages[0]
    assert page.has_images is True
    assert page.ocr_applied is False
    assert page.text == ""


def test_second_semester_sample_pdf_page_2_ocr():
    """Verify OCR specifically on the user-reported SECOND SEMESTER 2025-26.pdf bug."""
    from pathlib import Path

    sample_path = Path("/Users/devasishmishra/Downloads/SECOND SEMESTER 2025-26.pdf")
    if not sample_path.exists():
        pytest.skip("SECOND SEMESTER 2025-26.pdf not found in local Downloads")

    pdf_bytes = sample_path.read_bytes()
    result = extract_pdf_pages(pdf_bytes)

    assert result.total_pages == 2

    # Page 1 has native selectable text
    assert result.pages[0].page_number == 1
    assert result.pages[0].ocr_applied is False
    assert result.pages[0].word_count > 50

    # Page 2 has the scanned evaluation points table
    p2 = result.pages[1]
    assert p2.page_number == 2
    assert p2.ocr_applied is True
    assert "SALIENT POINTS OF EVALUATION" in p2.text
    assert p2.word_count > 100
    assert p2.char_count > 500
