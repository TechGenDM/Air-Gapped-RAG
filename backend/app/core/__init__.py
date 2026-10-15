"""Core modules, settings, and exception declarations."""

from app.core.config import Settings, get_settings
from app.core.errors import (
    CorruptPDFError,
    DocumentAlreadyIndexedError,
    DocumentNotFoundError,
    EmptyPDFError,
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    PasswordProtectedPDFError,
    PDFExtractionError,
    VectorStoreError,
)

__all__ = [
    "Settings",
    "get_settings",
    "PDFExtractionError",
    "EmptyPDFError",
    "CorruptPDFError",
    "PasswordProtectedPDFError",
    "OllamaError",
    "OllamaConnectionError",
    "OllamaModelNotFoundError",
    "VectorStoreError",
    "DocumentNotFoundError",
    "DocumentAlreadyIndexedError",
]
