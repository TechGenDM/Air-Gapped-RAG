"""PDF extraction service for parsing text and page structure using PyMuPDF and local OCR."""

import csv
import io
import logging
import os
from pathlib import Path
import shutil
import subprocess

import pymupdf

from app.core.errors import (
    CorruptPDFError,
    EmptyPDFError,
    PasswordProtectedPDFError,
)
from app.schemas.document import DocumentExtractionResult, ExtractedPage

logger = logging.getLogger(__name__)

# Standard candidate directories for offline Tesseract tessdata
TESSDATA_CANDIDATE_DIRS = [
    "/opt/homebrew/share/tessdata",
    "/usr/local/share/tessdata",
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",
]


def _resolve_tessdata_dir(custom_path: str | None = None) -> str | None:
    """Resolve directory containing Tesseract language models (tessdata)."""
    if custom_path and Path(custom_path).is_dir():
        return custom_path

    env_prefix = os.environ.get("TESSDATA_PREFIX")
    if env_prefix and Path(env_prefix).is_dir():
        return env_prefix

    for candidate in TESSDATA_CANDIDATE_DIRS:
        if Path(candidate).is_dir():
            return candidate

    return None


def _parse_tsv_layout_with_tables(tsv_str: str, dpi: int = 300) -> str:
    """Parse Tesseract TSV output, detecting and reconstructing column-aligned tables."""
    reader = csv.DictReader(io.StringIO(tsv_str), delimiter="\t")
    words: list[dict] = []
    for r in reader:
        t = r.get("text", "").strip()
        if t:
            try:
                words.append({
                    "text": t,
                    "left": int(r["left"]),
                    "top": int(r["top"]),
                    "width": int(r["width"]),
                    "height": int(r["height"]),
                    "right": int(r["left"]) + int(r["width"]),
                    "bottom": int(r["top"]) + int(r["height"]),
                    "block_num": int(r["block_num"]),
                    "par_num": int(r["par_num"]),
                    "line_num": int(r["line_num"]),
                })
            except (ValueError, KeyError):
                continue

    if not words:
        return ""

    blocks: dict[int, list[dict]] = {}
    for w in words:
        blocks.setdefault(w["block_num"], []).append(w)

    min_gap = max(45, int(90 * (dpi / 300.0)))
    tolerance = max(45, int(95 * (dpi / 300.0)))

    reconstructed_blocks: list[str] = []
    for _blk_id, b_words in sorted(blocks.items()):
        lines_dict: dict[tuple[int, int], list[dict]] = {}
        for w in b_words:
            lines_dict.setdefault((w["par_num"], w["line_num"]), []).append(w)

        sorted_keys = sorted(lines_dict.keys())
        std_lines: list[str] = []
        for k in sorted_keys:
            lw = sorted(lines_dict[k], key=lambda item: item["left"])
            std_lines.append(" ".join(item["text"] for item in lw))
        std_text = "\n".join(std_lines)

        # Detect multi-column table structure in this block
        table_summary = ""
        for k in sorted_keys[:2]:
            lw = sorted(lines_dict[k], key=lambda item: item["left"])
            col_headers: list[dict] = []
            for i in range(1, len(lw)):
                if lw[i]["text"] in ["|", "*", "-", "—", "_", "•"]:
                    continue
                gap_to_prev = lw[i]["left"] - lw[i - 1]["right"]
                if gap_to_prev >= min_gap:
                    col_headers.append(lw[i])

            if len(col_headers) >= 3:
                cols: dict[str, list[dict]] = {ch["text"]: [] for ch in col_headers}
                other_words = [
                    w for w in b_words
                    if w not in col_headers and w["text"] not in ["|", "*", "-", "—", "_"]
                ]
                for ow in other_words:
                    ow_center = (ow["left"] + ow["right"]) / 2
                    best_ch = min(
                        col_headers,
                        key=lambda ch: abs((ch["left"] + ch["right"]) / 2 - ow_center),
                    )
                    if abs((best_ch["left"] + best_ch["right"]) / 2 - ow_center) < tolerance:
                        cols[best_ch["text"]].append(ow)

                populated = sum(1 for ch in col_headers if len(cols[ch["text"]]) >= 1)
                if populated >= len(col_headers) * 0.7:
                    table_rows = ["Table Column Details:"]
                    for ch in col_headers:
                        matched = cols[ch["text"]]
                        matched.sort(key=lambda item: (item["top"], item["left"]))
                        val_str = " ".join(item["text"] for item in matched)
                        table_rows.append(f"- Column {ch['text']}: {val_str}")
                    table_summary = "\n" + "\n".join(table_rows)
                    break

        if table_summary:
            reconstructed_blocks.append(f"{std_text}\n{table_summary}")
        else:
            reconstructed_blocks.append(std_text)

    return "\n\n".join(reconstructed_blocks).strip()


def _run_ocr_page(
    page: pymupdf.Page,
    dpi: int = 300,
    language: str = "eng",
    tessdata_dir: str | None = None,
) -> str:
    """Execute local offline OCR on a single rendered page using PyMuPDF and Tesseract.

    Args:
        page: Bound PyMuPDF Page instance.
        dpi: Rendering resolution for OCR rasterization.
        language: Tesseract language code (defaults to 'eng').
        tessdata_dir: Optional explicit directory path containing traineddata files.

    Returns:
        Extracted OCR text string, or empty string if OCR produces no text or encounters an error.
    """
    kwargs: dict = {
        "dpi": dpi,
        "full": True,
        "language": language,
    }

    resolved_tessdata = _resolve_tessdata_dir(tessdata_dir)
    if resolved_tessdata:
        kwargs["tessdata"] = resolved_tessdata

    try:
        # Validate OCR engine availability via PyMuPDF binding first
        textpage_ocr = page.get_textpage_ocr(**kwargs)
        fallback_text = (page.get_text(textpage=textpage_ocr) or "").strip()

        # If tesseract CLI is available, run standalone OCR with TSV table column alignment
        tesseract_bin = shutil.which("tesseract")
        if tesseract_bin:
            try:
                pix = page.get_pixmap(dpi=dpi)
                cmd = [tesseract_bin, "stdin", "stdout", "tsv", "--psm", "3", "-l", language]
                env = os.environ.copy()
                if resolved_tessdata:
                    env["TESSDATA_PREFIX"] = resolved_tessdata
                    cmd.extend(["--tessdata-dir", resolved_tessdata])

                proc = subprocess.run(
                    cmd,
                    input=pix.tobytes("png"),
                    capture_output=True,
                    env=env,
                    check=False,
                    timeout=30.0,
                )
                if proc.returncode == 0 and proc.stdout:
                    parsed_tsv = _parse_tsv_layout_with_tables(
                        proc.stdout.decode("utf-8", errors="replace"),
                        dpi=dpi,
                    )
                    if parsed_tsv:
                        return parsed_tsv
            except Exception as cli_exc:
                logger.debug("Tesseract CLI layout parsing skipped: %s", cli_exc)

        return fallback_text
    except Exception as exc:
        logger.warning(
            "Local OCR fallback failed on page %d: %s. Preserving direct extraction.",
            page.number + 1,
            exc,
        )
        return ""


def extract_pdf_pages(
    pdf_bytes: bytes | bytearray,
    ocr_enabled: bool = True,
    ocr_dpi: int = 300,
    ocr_language: str = "eng",
    ocr_min_words: int = 3,
    tessdata_dir: str | None = None,
) -> DocumentExtractionResult:
    """Extract page-by-page text, metadata, and 1-indexed page numbers from PDF bytes.

    Uses direct PyMuPDF text stream extraction as the primary path. When a page has no
    meaningful text but contains scanned graphics or embedded images, applies local Tesseract
    OCR as a fallback.

    Args:
        pdf_bytes: Raw bytes of the PDF file.
        ocr_enabled: Whether to apply local OCR fallback on scanned/image-only pages.
        ocr_dpi: Resolution for OCR page rasterization.
        ocr_language: Tesseract language code (e.g. 'eng').
        ocr_min_words: Threshold below which pages with images attempt OCR fallback.
        tessdata_dir: Optional path to directory containing tessdata trained models.

    Returns:
        DocumentExtractionResult containing total_pages and a sequence of ExtractedPage.

    Raises:
        EmptyPDFError: If the input bytes are empty or the PDF contains zero pages.
        CorruptPDFError: If input is not bytes or the PDF is malformed/corrupted.
        PasswordProtectedPDFError: If the PDF is encrypted and requires a password.
    """
    if not isinstance(pdf_bytes, (bytes, bytearray)):
        raise CorruptPDFError("PDF data must be provided as bytes or bytearray.")

    if len(pdf_bytes) == 0:
        raise EmptyPDFError("PDF data is empty (0 bytes).")

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except pymupdf.EmptyFileError as exc:
        raise EmptyPDFError("PDF data is empty.") from exc
    except (pymupdf.FileDataError, Exception) as exc:
        raise CorruptPDFError(f"Failed to parse PDF document: {exc}") from exc

    try:
        # Check for encryption and password protection
        if doc.is_encrypted:
            # Check if default empty password allows reading
            if not doc.authenticate(""):
                raise PasswordProtectedPDFError(
                    "PDF document is password-protected and cannot be decrypted without credentials."
                )

        if getattr(doc, "needs_pass", 0):
            raise PasswordProtectedPDFError(
                "PDF document requires a password to open."
            )

        total_pages = doc.page_count
        if total_pages == 0:
            raise EmptyPDFError("PDF document contains zero pages.")

        extracted_pages: list[ExtractedPage] = []
        for page_idx in range(total_pages):
            page = doc.load_page(page_idx)
            page_number = page_idx + 1  # 1-indexed human readable

            # 1. Primary method: Direct text stream extraction
            raw_text = page.get_text("text") or ""
            text = raw_text.strip()

            # Detect embedded images and vector graphics
            image_list = page.get_images(full=True)
            has_images = len(image_list) > 0
            has_drawings = len(page.get_drawings()) > 0
            ocr_applied = False

            # 2. Fallback method: Local OCR when direct text is absent or insufficient on visual pages
            if ocr_enabled and len(text.split()) < ocr_min_words and (has_images or has_drawings):
                ocr_text = _run_ocr_page(
                    page=page,
                    dpi=ocr_dpi,
                    language=ocr_language,
                    tessdata_dir=tessdata_dir,
                )
                if len(ocr_text) > len(text):
                    text = ocr_text
                    ocr_applied = True

            char_count = len(text)
            word_count = len(text.split())

            extracted_pages.append(
                ExtractedPage(
                    page_number=page_number,
                    text=text,
                    char_count=char_count,
                    word_count=word_count,
                    has_images=has_images,
                    ocr_applied=ocr_applied,
                )
            )

        return DocumentExtractionResult(
            total_pages=total_pages,
            pages=extracted_pages,
        )
    except (EmptyPDFError, PasswordProtectedPDFError):
        raise
    except Exception as exc:
        raise CorruptPDFError(f"Error extracting pages from PDF: {exc}") from exc
    finally:
        if not doc.is_closed:
            doc.close()
