# Air-Gapped RAG Backend

Python 3.12 backend service for local-first, air-gapped document processing, PDF extraction, vector indexing, and evidence-backed question answering.

---

## Architecture & Design Principles

* **100% Local & Air-Gapped:** All parsing, storage, and processing execute locally without external network calls.
* **Verifiable Page Mapping:** PyMuPDF extracts text page-by-page preserving strict 1-indexed physical page numbers for citation accuracy.
* **Zero Trust Filename Handling:** Client-supplied filenames and paths are sanitized. Files are stored on disk strictly using UUID identifiers (`data/uploads/{document_id}.pdf`).
* **Privacy-Compliant Logging:** Raw document contents and extracted text are never written to server logs.
* **Controlled Ingestion:** Enforces a 50 MB upload limit and validates binary file headers (`%PDF-`) rather than trusting client MIME types.

---

## Prerequisites

* **Python 3.12** (managed via Homebrew or `uv`)
* **uv** (v0.12+)

---

## Setup & Installation

From the `backend/` directory:

```bash
# 1. Create a Python 3.12 virtual environment
uv venv --python 3.12

# 2. Activate the environment
source .venv/bin/activate

# 3. Install backend dependencies and testing tools
uv pip install -e ".[dev]"
```

---

## Running the Application

To start the local development server:

```bash
uvicorn app.main:app --reload --port 8000
```

* API Docs (Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)
* Alternative Docs (ReDoc): [http://localhost:8000/redoc](http://localhost:8000/redoc)
* Health Check: [http://localhost:8000/health](http://localhost:8000/health)

---

## Running the Automated Test Suite

Run all unit and integration tests using pytest:

```bash
# Run complete test suite
pytest -v

# Run tests with output logging
pytest -v -s
```

The test suite covers:
* Multi-page PDF text extraction and 1-indexed page mapping.
* Embedded raster/vector image detection per page.
* Handling of blank and empty pages without data loss.
* Safe handling of malformed, corrupt, or truncated PDFs.
* Detection and rejection of password-protected/encrypted PDFs.
* Rejection of unsupported extensions and non-PDF magic byte streams.
* Enforcement of file upload size limits (413 Content Too Large).
* Filename sanitization against path traversal attacks (`../../etc/passwd`).

---

## API Endpoints

### 1. `GET /health`
Returns system status and application version.

**Response (200 OK):**
```json
{
  "status": "ok",
  "app": "air-gapped-rag-backend",
  "version": "0.1.0"
}
```

### 2. `POST /api/v1/documents/upload`
Accepts a multipart file upload (`file`), validates file header integrity, extracts structured page content, and stores the file locally.

**Form Data:**
* `file`: Multipart PDF file (max 50 MB)

**Response (201 Created):**
```json
{
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "filename": "contract.pdf",
  "total_pages": 3,
  "pages": [
    {
      "page_number": 1,
      "text": "Master Services Agreement...",
      "char_count": 524,
      "word_count": 82,
      "has_images": false
    }
  ]
}
```

**HTTP Errors:**
* `400 Bad Request`: Empty file, invalid PDF header, or corrupted PDF stream.
* `413 Content Too Large`: File exceeds the 50 MB limit.
* `415 Unsupported Media Type`: File does not have a `.pdf` extension or has an incompatible MIME type.
* `422 Unprocessable Content`: Document is password-protected or encrypted.

---

### 3. `POST /api/v1/documents/{document_id}/index?reindex=false`
Chunks extracted pages, computes dense embeddings using the local Ollama instance (`nomic-embed-text`), and stores chunks and vectors in LanceDB under `backend/data/lancedb/`.

**Query Parameters:**
* `reindex` (bool, default `false`): When `false`, returns `409 Conflict` if the document is already indexed to prevent accidental duplication. When `true`, purges old chunks and overwrites the index.

**Response (200 OK):**
```json
{
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "filename": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d.pdf",
  "total_pages": 3,
  "total_chunks": 6,
  "reindexed": false,
  "message": "Successfully indexed 6 chunks from 3 pages."
}
```

---

### 4. `POST /api/v1/search`
Performs nearest-neighbor semantic vector search across indexed chunks using local embeddings.

**Request Body:**
```json
{
  "query": "What are the payment terms and invoicing schedule?",
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "limit": 3
}
```

**Response (200 OK):**
```json
{
  "query": "What are the payment terms and invoicing schedule?",
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "total_results": 1,
  "results": [
    {
      "chunk_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d_p2_c0",
      "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "filename": "contract.pdf",
      "page_number": 2,
      "chunk_index": 0,
      "text": "SECTION 2: FEES AND INVOICING...",
      "score": 0.8412,
      "distance": 0.1887
    }
  ]
}
```

---

### 5. `POST /api/v1/answer`
Performs end-to-end evidence-backed question answering over indexed documents using local Gemma 4 12B via Ollama. It retrieves top semantic chunks from LanceDB, provides isolated prompt contexts, enforces non-extrapolation, and validates used source citations server-side.

**Request Body:**
```json
{
  "query": "What is the notice period for contract termination?",
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "limit": 4
}
```

**Response (200 OK — Evidence Found):**
```json
{
  "question": "What is the notice period for contract termination?",
  "answer": "Either party may terminate the agreement for convenience upon ninety (90) days prior written notice.",
  "sources": [
    {
      "chunk_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d_p2_c0",
      "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "filename": "contract.pdf",
      "page_number": 2,
      "excerpt": "SECTION 2: Term and Termination. Either party may terminate this Agreement for convenience upon ninety (90) days prior written notice..."
    }
  ],
  "evidence_sufficient": true,
  "model": "gemma4:12b",
  "elapsed_seconds": 1.42
}
```

**Response (200 OK — Insufficient Evidence / Out of Scope):**
```json
{
  "question": "What is the remote work policy?",
  "answer": "Not found in records",
  "sources": [],
  "evidence_sufficient": false,
  "model": "gemma4:12b",
  "elapsed_seconds": 0.85
}
```

**Citation Integrity & Privacy Guarantees:**
* **Prompt Isolation:** Untrusted document excerpts are enclosed in guarded context boundaries; instructions contained within document text are ignored.
* **Server-Side Validation:** The LLM returns source IDs which the backend strictly maps against the retrieved chunks. Hallucinated IDs are discarded.
* **Refusal Discipline:** If retrieved chunks lack factual basis for the query, the model returns `"Not found in records"` with `evidence_sufficient: false`.


