"""Exception classes for Air-Gapped RAG PDF document processing."""


class PDFExtractionError(Exception):
    """Base exception for all PDF extraction and parsing failures."""
    pass


class EmptyPDFError(PDFExtractionError):
    """Raised when PDF bytes are empty or document contains zero pages."""
    pass


class CorruptPDFError(PDFExtractionError):
    """Raised when byte stream cannot be parsed as a valid PDF document."""
    pass


class PasswordProtectedPDFError(PDFExtractionError):
    """Raised when PDF is encrypted or password-protected."""
    pass


class OllamaError(Exception):
    """Base exception for local Ollama embedding operations."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when the local Ollama instance cannot be reached."""
    pass


class OllamaModelNotFoundError(OllamaError):
    """Raised when the requested embedding model is not present in local Ollama."""
    pass


class VectorStoreError(Exception):
    """Base exception for local vector database operations."""
    pass


class DocumentNotFoundError(VectorStoreError):
    """Raised when attempting to access a document that does not exist."""
    pass


class DocumentAlreadyIndexedError(VectorStoreError):
    """Raised when a document has already been indexed and reindex=false."""
    pass

