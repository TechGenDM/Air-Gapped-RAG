"""Application configuration and settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Base project root directory (Air-Gapped RAG root)
_DEFAULT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_UPLOAD_DIR = _DEFAULT_ROOT / "data" / "uploads"


class Settings(BaseSettings):
    """Air-Gapped RAG backend configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="AIR_GAPPED_",
        env_file=".env",
        extra="ignore",
    )

    project_name: str = "Air-Gapped RAG API"
    version: str = "0.1.0"
    api_v1_str: str = "/api/v1"

    # Upload controls
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    upload_dir: Path = _DEFAULT_UPLOAD_DIR

    # Local Vector Database & Embeddings
    lancedb_dir: Path = _DEFAULT_ROOT / "backend" / "data" / "lancedb"
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    embedding_timeout_seconds: float = 30.0

    # Local LLM (Gemma 4 12B)
    llm_model: str = "gemma4:12b"
    llm_timeout_seconds: float = 60.0

    # Chunking controls
    chunk_target_words: int = 400
    chunk_overlap_words: int = 50

    # OCR controls (Offline local fallback for scanned/image pages)
    ocr_enabled: bool = True
    ocr_dpi: int = 300
    ocr_language: str = "eng"
    ocr_tessdata_dir: str | None = None

    # Allowed CORS origins
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
