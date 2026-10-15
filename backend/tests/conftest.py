from pathlib import Path
from fastapi.testclient import TestClient
import pymupdf
import pytest

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def temp_upload_dir(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary directory for document uploads."""
    upload_path = tmp_path / "uploads"
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


@pytest.fixture
def temp_lancedb_dir(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary directory for LanceDB."""
    db_path = tmp_path / "lancedb"
    db_path.mkdir(parents=True, exist_ok=True)
    return db_path


class MockEmbeddingService:
    """Deterministic in-memory embedding service for testing without Ollama."""

    def __init__(self, vector_dim: int = 768) -> None:
        self.vector_dim = vector_dim

    async def embed_query(self, query: str) -> list[float]:
        return self._make_vector(query)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._make_vector(t) for t in texts]

    def _make_vector(self, text: str) -> list[float]:
        import hashlib
        import math

        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [float(b) / 255.0 for b in h]
        vec = (vec * (self.vector_dim // len(vec) + 1))[:self.vector_dim]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [round(x / norm, 6) for x in vec]


@pytest.fixture
def mock_embedding_service() -> MockEmbeddingService:
    """Fixture returning a mock embedding generator."""
    return MockEmbeddingService(vector_dim=768)


class MockLLMService:
    """Mock LLM service for testing Q&A synthesis without requiring local Ollama."""

    def __init__(
        self,
        answer: str = "The contract specifies a 30-day notice period for termination.",
        verified_chunks_indices: list[int] | None = None,
        sufficient: bool = True,
    ) -> None:
        self.answer = answer
        self.verified_chunks_indices = verified_chunks_indices
        self.sufficient = sufficient

    async def generate_answer(self, query: str, chunks: list) -> tuple[str, list, bool]:
        if not self.sufficient or not chunks:
            return "Not found in records", [], False
        if self.verified_chunks_indices is not None:
            chosen = [chunks[i] for i in self.verified_chunks_indices if i < len(chunks)]
        else:
            chosen = [chunks[0]] if chunks else []
        return self.answer, chosen, self.sufficient


@pytest.fixture
def mock_llm_service() -> MockLLMService:
    """Fixture returning a configurable mock LLM service."""
    return MockLLMService()


@pytest.fixture
def client(
    temp_upload_dir: Path,
    temp_lancedb_dir: Path,
    mock_embedding_service: MockEmbeddingService,
    mock_llm_service: MockLLMService,
):
    """Fixture providing a FastAPI TestClient configured with isolated storage, mock embeddings, and mock LLM."""
    from app.services.embedding_service import get_embedding_service
    from app.services.llm_service import get_llm_service

    test_settings = Settings(
        upload_dir=temp_upload_dir,
        lancedb_dir=temp_lancedb_dir,
        max_upload_size_bytes=50 * 1024 * 1024,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_embedding_service] = lambda: mock_embedding_service
    app.dependency_overrides[get_llm_service] = lambda: mock_llm_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()




@pytest.fixture
def create_multipage_pdf():
    """Factory fixture to create an in-memory PDF with specified pages of text."""

    def _create(pages_text: list[str]) -> bytes:
        doc = pymupdf.open()
        for text in pages_text:
            page = doc.new_page()
            if text:
                # Insert text at standard margins
                page.insert_text((50, 72), text, fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    return _create


@pytest.fixture
def create_image_pdf():
    """Factory fixture to create an in-memory PDF with an embedded image."""

    def _create(with_text: str = "Document with diagram") -> bytes:
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), with_text, fontsize=12)

        # Create a small 20x20 RGB pixmap
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
        page.insert_image(pymupdf.Rect(50, 70, 150, 170), pixmap=pix)

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    return _create


@pytest.fixture
def create_encrypted_pdf():
    """Factory fixture to create an in-memory encrypted/password-protected PDF."""

    def _create(text: str = "Confidential contract", password: str = "secretpass") -> bytes:
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=12)

        pdf_bytes = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=password,
            owner_pw=password + "_owner",
        )
        doc.close()
        return pdf_bytes

    return _create
