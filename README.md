# Air-Gapped RAG

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16.4-black.svg)](https://nextjs.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-4.0-38B2AC.svg)](https://tailwindcss.com/)
[![Vector DB: LanceDB](https://img.shields.io/badge/LanceDB-Embedded-orange.svg)](https://lancedb.github.io/lancedb/)
[![Local-First](https://img.shields.io/badge/Local--First-Prototype-blue.svg)](#local-execution--network-isolation-verification-pending)

A **local-first contract PDF question-answering prototype** engineered for confidential legal contract review. Operates locally with PyMuPDF, local Tesseract OCR, LanceDB, and Ollama, without reliance on cloud LLM APIs.

Built for the **Hacktoberfest 2026 Week 2 Open-Source AI Challenge**.

---

## Problem Statement

Organizations reviewing confidential commercial agreements and contracts cannot use cloud-hosted AI APIs (OpenAI, Anthropic, Google Cloud) without risking exposure of private terms, pricing schedules, or customer NDAs. Furthermore, standard RAG frameworks suffer from critical failure modes in legal workflows:
1. **Unverifiable Citations:** Most vector pipelines arbitrarily chunk text across document pages, losing original physical page references.
2. **Scanned PDF Blindness:** Pure digital parsers silently fail on scanned or image-based pages, producing empty records.
3. **Hallucination under Uncertainty:** Cloud LLMs tend to fabricate plausible answers when evidence is missing rather than explicitly declaring absence.
4. **Cloud Leaks & Telemetry:** Many tools still phone home for analytics, hosted web fonts, or API telemetry.

**Air-Gapped RAG** addresses these challenges by combining offline-capable document extraction (PyMuPDF + Tesseract OCR), page-preserving sliding chunking, embedded vector indexing (LanceDB), and local open-weights LLM inference (Ollama + Gemma 4 12B) into a local web application using Next.js and FastAPI.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client["Frontend (Next.js 16 + React 19 + Tailwind CSS 4)"]
        UI[Interactive RAG Dashboard]
        UploadZone[Drag-and-Drop PDF Upload]
        DocView[Document & Page Inspector]
        QAPanel[Evidence-Backed Q&A Panel]
    end

    subgraph Backend["FastAPI Backend (Python 3.12)"]
        API[API Router /api/v1]
        Storage[Local File Storage /data/uploads]
        PDFService[PyMuPDF Text & Tesseract OCR Service]
        Chunker[Page-Aware Sliding Window Chunker]
        EmbedService[Local Embedding Client]
        LanceDB[(LanceDB Embedded Vector Table)]
        LLMService[Local Ollama LLM Client]
    end

    subgraph LocalEngine["Local AI Infrastructure (Ollama)"]
        EmbedModel["nomic-embed-text (Embeddings)"]
        GenModel["gemma4:12b (Local LLM Inference)"]
    end

    UploadZone -->|1. Multipart PDF Upload| API
    API -->|Save with UUID| Storage
    API -->|Extract Text & OCR Fallback| PDFService
    PDFService -->|Preserve 1-Indexed Pages| Chunker
    Chunker -->|Dense Vector Request| EmbedService
    EmbedService -->|Local Vectorization via /api/embed| EmbedModel
    EmbedService -->|Store Chunks & Embeddings| LanceDB

    QAPanel -->|2. Natural Language Query| API
    API -->|Vector Similarity Search| LanceDB
    LanceDB -->|Top K Scored Chunks| LLMService
    LLMService -->|Strict Grounding Context| GenModel
    GenModel -->|Answer with Citations| LLMService
    LLMService -->|Validate Citations Against Chunks| API
    API -->|3. Answer + Verified Page Citations| QAPanel
```

---

## Core Features

- **Local-First Architecture (Network Isolation Verification Pending):** Designed to operate within a local environment once runtime dependencies and model weights are pre-installed. Vector embeddings (`nomic-embed-text`) and inference requests (`gemma4:12b`) execute over loopback (`127.0.0.1`), with no cloud LLM API calls, hosted fonts, or remote analytics configured. Full physical air-gap isolation and zero network egress have not yet been independently verified.
- **Strict 1-Indexed Physical Page Citations:** Text chunks never span multiple physical pages. Every retrieved passage preserves original physical page numbers for auditable legal and compliance review.
- **Hybrid Digital & Scanned PDF OCR:** Automatically falls back to high-resolution (300 DPI) Tesseract OCR when digital text extraction yields insufficient content, reconstructing multi-column tabular layouts.
- **Embedded In-Process Vector Storage:** Uses LanceDB directly in-process (`backend/data/lancedb/`), eliminating separate database server processes, cloud clusters, or socket exposure.
- **Hallucination Mitigation & Citation Verification:**
  - Untrusted document chunks are quarantined inside `<document_context>` XML boundaries.
  - LLM instructions enforce strict refusal: when evidence is insufficient or question falls outside context, the system returns `"Not found in records"` with `evidence_sufficient=False` and zero citations.
  - Server-side citation validation verifies referenced chunk IDs against actual retrieved context, discarding ungrounded citations and overriding answers that lack verified textual support.
- **Streaming Upload Guard (50 MB Limit):** Streams incoming multipart uploads in 1 MB chunks, immediately aborting with HTTP 413 (`Content Too Large`) if the stream exceeds 50 MB (52,428,800 bytes) without loading the entire payload into RAM.
- **Privacy-Preserving Logging:** Raw document text, extracted strings, and LLM payloads are explicitly excluded from application logs.

---

## Open-Source AI Stack Rationale

| Component | Choice | Rationale |
|---|---|---|
| **Inference Model** | **Gemma 4 12B** | Open-weights model by Google DeepMind with instruction-following and reasoning capabilities, run locally via Ollama with structured JSON output and citation generation. |
| **Embedding Model** | **nomic-embed-text** | Open-weights 768-dimensional text embedding model with a 2,048-token context window, optimized for dense semantic retrieval across contracts and technical documentation. |
| **Vector Storage** | **LanceDB** | Disk-backed embedded vector store based on the Lance columnar format (Apache Arrow). Runs directly in-process without requiring a separate database server or daemon. |
| **Document Processing** | **PyMuPDF + Tesseract** | PyMuPDF provides digital text extraction and PDF rendering; Tesseract OCR provides offline optical character recognition with layout analysis. |

### Why We Chose Gemma 4 12B

Air-Gapped RAG uses Google's Gemma 4 12B as its local answer-generation model. We selected it for its balance of reasoning capability, long-context support, multimodal capabilities, and practical integration with Ollama for local inference.

We considered other open-weight model families, including Qwen and Kimi. Qwen 3.5 9B is a compelling alternative for resource-conscious inference, while Kimi's flagship models target much larger, compute-intensive agentic workloads.

Our choice is a project-specific engineering decision, not a claim that Gemma universally outperforms these models. Gemma is already integrated into our working RAG pipeline, and the application is designed to generate evidence-backed answers without relying on cloud AI APIs.

Model capabilities and memory requirements vary by model version, quantization, context length, and hardware. The model's performance on contract retrieval and citation accuracy must be evaluated in the context of the complete application.

References: [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4) · [Qwen 3.5 9B model card](https://huggingface.co/Qwen/Qwen3.5-9B) · [Kimi K3 model card](https://huggingface.co/moonshotai/Kimi-K3)

---

## Repository Structure

```text
Air-Gapped-RAG/
├── .github/
│   ├── ISSUE_TEMPLATE/        # Standardized issue templates
│   ├── workflows/             # GitHub Actions CI for backend & frontend
│   └── pull_request_template.md
├── backend/                   # FastAPI 3.12 backend application
│   ├── app/
│   │   ├── api/v1/            # API endpoints (documents, search, answer)
│   │   ├── core/              # Settings, configuration, custom exceptions
│   │   ├── schemas/           # Pydantic v2 data models & DTOs
│   │   ├── services/          # PDF parsing, OCR, chunking, LanceDB, Ollama
│   │   └── main.py            # FastAPI application factory
│   ├── tests/                 # Automated pytest test suite
│   └── pyproject.toml         # Packaging & dependency specifications
├── frontend/                  # Next.js 16 frontend application
│   ├── src/
│   │   ├── app/               # Next.js App Router (layout, page, styles)
│   │   ├── components/        # UI components (Viewer, Upload, QA, Cards)
│   │   └── lib/api.ts         # Type-safe API client
│   └── package.json           # Node / pnpm dependencies
├── scripts/
│   └── demo_air_gapped_rag.py # Repeatable end-to-end offline demonstration
├── data/
│   └── uploads/               # Local disk storage for ingested documents
├── CONTRIBUTING.md            # Guidelines for open-source contributors
├── CODE_OF_CONDUCT.md         # Contributor Covenant Code of Conduct
├── LICENSE                    # MIT License
├── README.md                  # Project documentation
└── SECURITY.md                # Security policy & vulnerability reporting
```

---

## Prerequisites

Before running Air-Gapped RAG, ensure your system has the following installed:

1. **Python 3.12+** and **uv** package manager:
   ```bash
   brew install uv python@3.12   # macOS
   # or on Linux: sudo apt install python3.12 python3.12-venv && curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. **Node.js 20+** and **pnpm**:
   ```bash
   brew install node pnpm         # macOS
   ```
3. **Ollama**:
   ```bash
   brew install ollama            # macOS
   # or download from https://ollama.com/download
   ```
4. **Tesseract OCR**:
   ```bash
   brew install tesseract tesseract-lang  # macOS
   # or on Linux: sudo apt install tesseract-ocr tesseract-ocr-eng
   ```

Pull the required local open-source models:
```bash
ollama pull nomic-embed-text
ollama pull gemma4:12b
```

---

## Setup & Local Execution

### 1. Backend Setup

```bash
cd backend

# Create virtual environment and install dependencies
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests
uv run pytest -v

# Start development server
uvicorn app.main:app --reload --port 8000
```

FastAPI Interactive Docs will be accessible at: [http://localhost:8000/docs](http://localhost:8000/docs).

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
pnpm install

# Run linter and typecheck
pnpm run lint
pnpm exec tsc --noEmit

# Build production bundle
pnpm run build

# Start development server
pnpm run dev
```

The Web Dashboard will be accessible at: [http://localhost:3000](http://localhost:3000).

---

## Local Execution & Network Isolation Verification (Pending)

The application is designed for local execution once dependencies and model weights are installed. Full physical air-gapped isolation and zero network egress have not yet been independently demonstrated and remain pending verification.

To test the application in an isolated environment with network interfaces disabled:

### Step 1: Pre-requisite Preparation
Ensure the local Python environment, Node packages, and Ollama models (`gemma4:12b` and `nomic-embed-text`) are pre-downloaded while connected to the internet.

### Step 2: Sever All External Network Connectivity
Turn off Wi-Fi and disconnect Ethernet:
```bash
# macOS
networksetup -setairportpower en0 off

# Linux
sudo nmcli networking off
```

### Step 3: Verify Loopback Availability
Confirm local services are responding over loopback `127.0.0.1`:
```bash
curl -s http://127.0.0.1:11434/api/tags | grep nomic-embed-text
curl -s http://127.0.0.1:8000/health
```

### Step 4: Run the Demonstration Script
Execute the demonstration script:
```bash
backend/.venv/bin/python scripts/demo_air_gapped_rag.py --local
```

### Step 5: Verify Socket Bindings
Inspect the active sockets used by local processes:
```bash
lsof -i -P -n | grep -E 'python|ollama|node'
```
*Expected Result:* All established sockets must be bound strictly to loopback addresses (`127.0.0.1` or `[::1]`). Network-isolation verification is confirmed only when no external WAN interfaces or remote IP addresses are contacted.

### Step 6: Restore Network (When Finished)
```bash
# macOS
networksetup -setairportpower en0 on

# Linux
sudo nmcli networking on
```

---

## Repeatable Demonstration

The repository includes a self-contained demonstration script (`scripts/demo_air_gapped_rag.py`) that validates the complete RAG pipeline without manual UI clicks:

1. **Generates a synthetic 3-page Master Services Agreement (MSA)** containing payment schedules, performance evaluation tiers, liability caps, confidentiality durations, and governing law.
2. **Uploads and extracts the document** via `/api/v1/documents/upload`.
3. **Indexes text chunks in LanceDB** using local `nomic-embed-text` embeddings.
4. **Executes 5 benchmark queries:**
   - **Answerable Query 1:** Limitation of liability cap under Section 4 (Verifies answer `$250,000` on Page 2).
   - **Answerable Query 2:** Governing law jurisdiction (Verifies `Delaware` on Page 3).
   - **Answerable Query 3:** Confidentiality duration (Verifies `3 years` on Page 2).
   - **Unanswerable Query 4:** Statutory penalties under Australian law (Verifies strict refusal `"Not found in records"`, `evidence_sufficient=False`, and zero citations).
   - **Unanswerable Query 5:** Personal residential address of executive (Verifies privacy refusal and zero hallucinated citations).

### Running the Demo
```bash
# Option A: In-process execution (no server startup required)
backend/.venv/bin/python scripts/demo_air_gapped_rag.py --local

# Option B: Against running backend server (port 8000)
backend/.venv/bin/python scripts/demo_air_gapped_rag.py --url http://127.0.0.1:8000
```

---

## Testing & Quality Assurance

### Backend Test Suite
The backend automated test suite covers (latest reported audit: 66 passing tests; these remain reported results until rerun in your local environment):
- PDF digital text extraction and 1-indexed page ordering.
- Tesseract OCR fallback and multi-column alignment reconstruction.
- Page-aware chunking boundaries (zero page-spanning chunks).
- Ollama `/api/embed` integration and error handling.
- LanceDB vector indexing, similarity search, and document re-indexing.
- LLM prompt isolation, citation validation, and strict refusal behavior.
- HTTP API error responses (oversized 51 MB, corrupt, and password-protected PDFs).

```bash
cd backend
uv run pytest -v
```

### Frontend Verification
```bash
cd frontend
pnpm run lint
pnpm exec tsc --noEmit
pnpm exec next build --webpack
```

---

## Known Limitations

- **Prototype Scope:** This is a local-first question-answering prototype designed for contract PDFs; it is not evaluated or certified for production use with medical, classified, or defense records.
- **Network Isolation Verification Pending:** While designed to use local endpoints without external API calls, formal verification of zero network egress in an air-gapped environment has not yet been independently completed.
- **Hardware Requirements:** Running Gemma 4 12B locally requires sufficient RAM/VRAM. Actual memory footprint and latency depend on host hardware, quantization level, and context size. No performance or speed guarantees are made without benchmarks.
- **File Formats & Sizes:** Only PDF documents (`.pdf`) up to 50 MB are supported. Encrypted or password-protected PDFs must be unlocked prior to ingestion.
- **Scanned Document DPI:** Tesseract OCR accuracy degrades if scanned documents have a resolution below 150 DPI or heavily degraded handwritten script.
- **Embedded LanceDB Scope:** The embedded LanceDB deployment is designed for single-user local execution on a workstation rather than multi-tenant horizontal clusters.

---

## Security & Privacy Boundary

- **Zero Telemetry:** Neither the backend nor the frontend contains third-party tracking scripts, analytics cookies, or phone-home requests.
- **Storage Isolation:** Uploaded files are renamed using randomly generated UUIDs, mitigating path traversal and filesystem fingerprinting.
- **Privacy-Compliant Logging:** Raw document content, extracted text strings, and vector payloads are explicitly excluded from application logs.

---

## License

This project is licensed under the [MIT License](LICENSE).
