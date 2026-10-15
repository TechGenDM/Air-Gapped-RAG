"""Focused regression tests for scanned OCR table retrieval and answer generation."""

from pathlib import Path
import pytest
import pymupdf

from app.schemas.search import SearchResultChunk
from app.services.chunking_service import split_text_into_chunks
from app.services.pdf_service import extract_pdf_pages
from app.services.llm_service import OllamaLLMService


def _create_synthetic_scanned_grade_pdf() -> bytes:
    """Generate a synthetic scanned PDF containing a rendered grade evaluation table."""
    # First, render a page with a multi-column grade table
    doc_render = pymupdf.open()
    p_render = doc_render.new_page(width=595, height=842)
    
    # Title
    p_render.insert_text((50, 60), "ACADEMIC EVALUATION GUIDELINES", fontsize=16)
    p_render.insert_text((50, 90), "1. Courses are evaluated according to the following letter grade scheme:", fontsize=11)
    
    # Header and multi-column table
    # Columns spaced by > 100px
    p_render.insert_text((50, 130), "Letter Grade *", fontsize=10)
    p_render.insert_text((180, 130), "A", fontsize=10)
    p_render.insert_text((270, 130), "A-", fontsize=10)
    p_render.insert_text((360, 130), "B", fontsize=10)
    p_render.insert_text((450, 130), "B-", fontsize=10)
    p_render.insert_text((530, 130), "C", fontsize=10)

    p_render.insert_text((50, 160), "Qualitative", fontsize=10)
    p_render.insert_text((270, 160), "Very", fontsize=10)
    p_render.insert_text((450, 160), "Above", fontsize=10)

    p_render.insert_text((50, 180), "Meaning", fontsize=10)
    p_render.insert_text((180, 180), "Excellent", fontsize=10)
    p_render.insert_text((270, 180), "Good", fontsize=10)
    p_render.insert_text((360, 180), "Good", fontsize=10)
    p_render.insert_text((450, 180), "Average", fontsize=10)
    p_render.insert_text((530, 180), "Fair", fontsize=10)

    p_render.insert_text((50, 210), "Grade Point", fontsize=10)
    p_render.insert_text((180, 210), "10", fontsize=10)
    p_render.insert_text((270, 210), "9", fontsize=10)
    p_render.insert_text((360, 210), "8", fontsize=10)
    p_render.insert_text((450, 210), "7", fontsize=10)
    p_render.insert_text((530, 210), "6", fontsize=10)

    p_render.insert_text((50, 260), "Note: Grades A-, B- and C- were introduced in the First Semester.", fontsize=10)

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
    assert "ACADEMIC EVALUATION GUIDELINES" in page.text
    assert "B-" in page.text
    assert "Above" in page.text and "Average" in page.text


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


def test_second_semester_pdf_page_2_table_column_details():
    """Verify that SECOND SEMESTER 2025-26.pdf page 2 extracts table column mappings."""
    sample_path = Path("/Users/devasishmishra/Downloads/SECOND SEMESTER 2025-26.pdf")
    if not sample_path.exists():
        pytest.skip("SECOND SEMESTER 2025-26.pdf not found in local Downloads")

    result = extract_pdf_pages(sample_path.read_bytes())
    assert result.total_pages == 2

    p2 = result.pages[1]
    assert p2.page_number == 2
    assert p2.ocr_applied is True
    assert "SALIENT POINTS OF EVALUATION" in p2.text
    assert "Table Column Details:" in p2.text
    assert "Column B-: Above Average 7" in p2.text
    assert "Column A: Excellent 10" in p2.text
    assert "Column A-: Very Good 9" in p2.text
    assert "Column B: Good 8" in p2.text
