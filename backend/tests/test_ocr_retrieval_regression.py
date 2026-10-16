"""Focused regression tests for scanned OCR table retrieval and answer generation."""

import pytest
import pymupdf

from app.schemas.search import SearchResultChunk
from app.services.chunking_service import split_text_into_chunks
from app.services.pdf_service import extract_pdf_pages
from app.services.llm_service import OllamaLLMService


def _create_synthetic_scanned_grade_pdf() -> bytes:
    """Generate a synthetic scanned PDF containing a rendered grade evaluation table."""
    doc_render = pymupdf.open()
    p_render = doc_render.new_page(width=595, height=842)

    p_render.insert_text((50, 60), "SALIENT POINTS OF EVALUATION", fontsize=12, fontname="helv")
    p_render.insert_text(
        (50, 85),
        "1. The performance in most courses is spelt out in terms of letter grades A, A-, B, B-, C.\n"
        "Each letter grade has a qualitative meaning and a grade point value as given below:",
        fontsize=10,
        fontname="helv",
    )

    # Table headers and cells
    p_render.insert_text((50, 130), "Letter Grade *", fontsize=9, fontname="helv")
    p_render.insert_text((160, 130), "A", fontsize=9, fontname="helv")
    p_render.insert_text((230, 130), "A-", fontsize=9, fontname="helv")
    p_render.insert_text((300, 130), "B", fontsize=9, fontname="helv")
    p_render.insert_text((370, 130), "B-", fontsize=9, fontname="helv")
    p_render.insert_text((440, 130), "C", fontsize=9, fontname="helv")

    p_render.insert_text((50, 146), "Qualitative", fontsize=9, fontname="helv")
    p_render.insert_text((230, 146), "Very", fontsize=9, fontname="helv")
    p_render.insert_text((370, 146), "Above", fontsize=9, fontname="helv")

    p_render.insert_text((50, 160), "Meaning", fontsize=9, fontname="helv")
    p_render.insert_text((160, 160), "Excellent", fontsize=9, fontname="helv")
    p_render.insert_text((230, 160), "Good", fontsize=9, fontname="helv")
    p_render.insert_text((300, 160), "Good", fontsize=9, fontname="helv")
    p_render.insert_text((370, 160), "Average", fontsize=9, fontname="helv")
    p_render.insert_text((440, 160), "Fair", fontsize=9, fontname="helv")

    p_render.insert_text((50, 176), "Grade Point", fontsize=9, fontname="helv")
    p_render.insert_text((160, 176), "10", fontsize=9, fontname="helv")
    p_render.insert_text((230, 176), "9", fontsize=9, fontname="helv")
    p_render.insert_text((300, 176), "8", fontsize=9, fontname="helv")
    p_render.insert_text((370, 176), "7", fontsize=9, fontname="helv")
    p_render.insert_text((440, 176), "6", fontsize=9, fontname="helv")

    p_render.insert_text(
        (50, 210),
        "Note: Among the letter grades mentioned above, the grades A- and B- were introduced in Semester 1.",
        fontsize=9,
        fontname="helv",
    )

    pix = p_render.get_pixmap(dpi=300)
    doc_render.close()

    # Create image-only scanned document
    doc_scanned = pymupdf.open()
    p_scanned = doc_scanned.new_page(width=595, height=842)
    p_scanned.insert_image(p_scanned.rect, pixmap=pix)
    pdf_bytes = doc_scanned.tobytes()
    doc_scanned.close()

    return pdf_bytes


def test_synthetic_scanned_grade_table_extraction():
    """Verify that OCR extracts synthetic grade table and preserves grade-to-meaning mapping."""
    pdf_bytes = _create_synthetic_scanned_grade_pdf()
    result = extract_pdf_pages(pdf_bytes)

    assert result.total_pages == 1
    page = result.pages[0]
    assert page.page_number == 1
    assert page.ocr_applied is True
    assert page.word_count > 20
    assert "SALIENT POINTS OF EVALUATION" in page.text
    assert "Table Column Details:" in page.text
    assert "Column B-: Above Average 7" in page.text
    assert "Column A: Excellent 10" in page.text
    assert "Column A-: Very Good 9" in page.text
    assert "Column B: Good 8" in page.text


def test_synthetic_ocr_table_chunking_preserves_page_boundaries():
    """Verify that chunking on OCR-extracted text maintains strict page boundaries."""
    pdf_bytes = _create_synthetic_scanned_grade_pdf()
    result = extract_pdf_pages(pdf_bytes)
    page = result.pages[0]

    chunks = split_text_into_chunks(
        text=page.text,
        document_id="doc-reg-001",
        filename="academic_eval.pdf",
        page_number=page.page_number,
    )

    assert len(chunks) >= 1
    for c in chunks:
        assert c.page_number == 1
        assert c.document_id == "doc-reg-001"
        assert c.filename == "academic_eval.pdf"
        assert len(c.text) > 0


@pytest.mark.anyio
async def test_llm_answer_generation_with_synthetic_ocr_chunk(monkeypatch):
    """Verify that LLM answer generation resolves grade mappings from OCR text."""
    pdf_bytes = _create_synthetic_scanned_grade_pdf()
    result = extract_pdf_pages(pdf_bytes)
    page = result.pages[0]

    chunk = SearchResultChunk(
        chunk_id="reg_chunk_p1_c0",
        document_id="doc-reg-001",
        filename="academic_eval.pdf",
        page_number=1,
        chunk_index=0,
        text=page.text,
        score=0.92,
        distance=0.08,
    )

    llm_service = OllamaLLMService()

    # Mock ollama chat call to return verified response
    async def mock_call_ollama(user_content: str):
        assert "academic_eval.pdf" in user_content
        assert "What is the qualitative meaning of grade B-?" in user_content
        return {
            "message": {
                "content": '{"answer": "Above Average", "used_source_ids": ["SOURCE_1"], "evidence_sufficient": true}'
            }
        }

    monkeypatch.setattr(llm_service, "_call_ollama_chat", mock_call_ollama)

    answer, sources, suff = await llm_service.generate_answer(
        query="What is the qualitative meaning of grade B-?",
        chunks=[chunk],
    )

    assert suff is True
    assert "Above Average" in answer
    assert len(sources) == 1
    assert sources[0].page_number == 1
    assert sources[0].filename == "academic_eval.pdf"


@pytest.mark.anyio
async def test_unrelated_grade_query_safeguard_refusal(monkeypatch):
    """Verify that absent grades (e.g. Z+) correctly return 'Not found in records'."""
    chunk = SearchResultChunk(
        chunk_id="reg_chunk_p1_c0",
        document_id="doc-reg-001",
        filename="academic_eval.pdf",
        page_number=1,
        chunk_index=0,
        text="Letter Grade A: Excellent. Letter Grade B-: Above Average.",
        score=0.85,
        distance=0.15,
    )

    llm_service = OllamaLLMService()

    async def mock_call_ollama(user_content: str):
        return {
            "message": {
                "content": '{"answer": "Not found in records", "used_source_ids": [], "evidence_sufficient": false}'
            }
        }

    monkeypatch.setattr(llm_service, "_call_ollama_chat", mock_call_ollama)

    answer, sources, suff = await llm_service.generate_answer(
        query="What is the qualitative meaning of grade Z+?",
        chunks=[chunk],
    )

    assert suff is False
    assert answer == "Not found in records"
    assert len(sources) == 0


def test_synthetic_scanned_multipage_grade_table_column_details():
    """Verify that multi-page PDF with scanned evaluation table preserves column alignment."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 60), "COMPUTER SCIENCE 101 SYLLABUS", fontsize=14, fontname="helv")
    p1.insert_text(
        (50, 90),
        "This course introduces fundamental principles of computer systems and programming.\n"
        "Lectures meet on Mondays and Wednesdays. Midterm exams are held during Week 8.\n"
        "Students are expected to adhere to academic integrity guidelines for all assignments.\n"
        "Grading policies and performance standards are summarized on Page 2.",
        fontsize=10,
        fontname="helv",
    )

    p2_bytes = _create_synthetic_scanned_grade_pdf()
    p2_doc = pymupdf.open(stream=p2_bytes, filetype="pdf")
    doc.insert_pdf(p2_doc)
    p2_doc.close()

    full_pdf_bytes = doc.tobytes()
    doc.close()

    result = extract_pdf_pages(full_pdf_bytes)
    assert result.total_pages == 2

    # Page 1 is native text
    assert result.pages[0].page_number == 1
    assert result.pages[0].ocr_applied is False
    assert "COMPUTER SCIENCE 101 SYLLABUS" in result.pages[0].text

    # Page 2 is scanned table with OCR
    p2 = result.pages[1]
    assert p2.page_number == 2
    assert p2.ocr_applied is True
    assert "SALIENT POINTS OF EVALUATION" in p2.text
    assert "Table Column Details:" in p2.text
    assert "Column B-: Above Average 7" in p2.text
    assert "Column A: Excellent 10" in p2.text
    assert "Column A-: Very Good 9" in p2.text
    assert "Column B: Good 8" in p2.text
