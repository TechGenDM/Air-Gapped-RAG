"""Integration tests for FastAPI document upload and extraction API."""

from io import BytesIO
from pathlib import Path

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings, get_settings
from app.main import app


def test_successful_multipage_pdf_upload(client, temp_upload_dir, create_multipage_pdf):
    """Verify successful upload of a multi-page contract PDF with page-mapped text."""
    pages_text = [
        "Confidential Non-Disclosure Agreement\nParty A and Party B agree to terms.",
        "Section 2: Scope of Confidentiality.\nStandard proprietary information clauses.",
        "Section 3: Termination and Return of Assets.\nEffective within 10 days of notice.",
    ]
    pdf_bytes = create_multipage_pdf(pages_text)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("master_agreement.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    # 1. Verify response metadata
    assert data["filename"] == "master_agreement.pdf"
    assert "document_id" in data
    document_id = data["document_id"]
    assert data["total_pages"] == 3
    assert len(data["pages"]) == 3

    # 2. Verify exact 1-indexed page mapping and text fidelity
    for idx, expected_text in enumerate(pages_text):
        page = data["pages"][idx]
        assert page["page_number"] == idx + 1
        assert page["text"] == expected_text
        assert page["char_count"] == len(expected_text)
        assert page["word_count"] == len(expected_text.split())
        assert page["has_images"] is False

    # 3. Verify disk persistence uses UUID, not original filename
    stored_file = temp_upload_dir / f"{document_id}.pdf"
    assert stored_file.exists()
    assert stored_file.read_bytes() == pdf_bytes

    # Ensure untrusted filename was not written to filesystem
    assert not (temp_upload_dir / "master_agreement.pdf").exists()


def test_upload_empty_pdf_returns_bad_request(client):
    """Verify that uploading a 0-byte file returns HTTP 400."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("empty.pdf", BytesIO(b""), "application/pdf")},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in response.json()["detail"].lower()


def test_upload_corrupt_file_returns_bad_request(client):
    """Verify that uploading corrupt bytes with a .pdf extension returns HTTP 400."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("corrupt.pdf", BytesIO(b"%PDF-corrupt_body_no_structure"), "application/pdf")},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "corrupt" in response.json()["detail"].lower() or "invalid" in response.json()["detail"].lower()


def test_upload_non_pdf_content_with_pdf_extension_returns_bad_request(client):
    """Verify that files lacking the %PDF- magic header return HTTP 400."""
    fake_pdf = b"This is plain text pretending to be a PDF."
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("fake.pdf", BytesIO(fake_pdf), "application/pdf")},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "missing %pdf- header" in response.json()["detail"].lower()


def test_upload_password_protected_pdf_returns_unprocessable(client, create_encrypted_pdf):
    """Verify that password-protected PDFs return HTTP 422 Unprocessable Content."""
    pdf_bytes = create_encrypted_pdf(
        text="Classified military contract",
        password="SuperSecretPassword!",
    )

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("secure.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "password-protected" in response.json()["detail"].lower()


def test_upload_unsupported_file_extension_returns_unsupported_media_type(client):
    """Verify that non-PDF file extensions return HTTP 415."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract.docx", BytesIO(b"dummy data"), "application/vnd.openxmlformats-officedocument")},
    )
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "only pdf documents" in response.json()["detail"].lower()


def test_upload_unsupported_mime_type_returns_unsupported_media_type(client):
    """Verify that unsupported MIME types return HTTP 415."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract.pdf", BytesIO(b"%PDF-1.4 test"), "image/png")},
    )
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "unsupported media type" in response.json()["detail"].lower()


def test_upload_size_limit_enforced(temp_upload_dir, create_multipage_pdf):
    """Verify that files exceeding the configured maximum size return HTTP 413."""
    # Set small upload limit of 500 bytes for deterministic test
    custom_settings = Settings(
        upload_dir=temp_upload_dir,
        max_upload_size_bytes=500,
    )
    app.dependency_overrides[get_settings] = lambda: custom_settings

    pdf_bytes = create_multipage_pdf(["Text that produces a PDF exceeding 500 bytes."])
    assert len(pdf_bytes) > 500

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/documents/upload",
                files={"file": ("large_doc.pdf", BytesIO(pdf_bytes), "application/pdf")},
            )
            assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
            assert "exceeds the maximum limit" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_upload_realistic_51mb_oversized_pdf_returns_413(client):
    """Verify that a realistic 51 MB multipart upload is aborted with HTTP 413 under default 50 MB limits."""
    # 51 MB payload with valid %PDF- magic prefix
    oversized_data = b"%PDF-1.4\n" + (b"0" * (51 * 1024 * 1024))
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("oversized_51mb.pdf", BytesIO(oversized_data), "application/pdf")},
    )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert "File size exceeds the maximum limit of 50 MB." in response.json()["detail"]


def test_safe_handling_of_path_traversal_filename(client, temp_upload_dir, create_multipage_pdf):
    """Verify that directory traversal sequences in filename are sanitized and ignored."""
    pdf_bytes = create_multipage_pdf(["Safe file mapping."])

    traversal_filename = "../../../../etc/passwd.pdf"
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (traversal_filename, BytesIO(pdf_bytes), "application/pdf")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    # Client filename should be sanitized to basename only
    assert data["filename"] == "passwd.pdf"
    document_id = data["document_id"]

    # File must be stored strictly as {document_id}.pdf inside temp_upload_dir
    expected_path = temp_upload_dir / f"{document_id}.pdf"
    assert expected_path.exists()
    assert expected_path.read_bytes() == pdf_bytes

    # Ensure no file was created outside temp_upload_dir
    assert not (temp_upload_dir.parent / "passwd.pdf").exists()


def test_safe_handling_of_empty_or_special_character_filename(client, temp_upload_dir, create_multipage_pdf):
    """Verify that filenames with special characters or whitespace default safely."""
    pdf_bytes = create_multipage_pdf(["Contract with unusual name."])

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("   .pdf", BytesIO(pdf_bytes), "application/pdf")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["filename"] == ".pdf" or data["filename"] == "document.pdf"
