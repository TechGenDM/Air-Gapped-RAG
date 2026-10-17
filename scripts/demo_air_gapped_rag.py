"""Air-Gapped RAG — Local-First Contract Q&A Prototype Demonstration Script.

Generates a synthetic multi-page commercial contract, uploads it to the local
Air-Gapped RAG backend, indexes chunks in LanceDB, and evaluates both answerable
and unanswerable queries to verify:
  1. Grounded answers with exact physical page citations.
  2. Strict refusal ("Not found in records") for unanswerable/out-of-scope questions.
  3. Local execution over loopback endpoints without cloud LLM APIs.
"""

import argparse
import io
import sys
import time
from pathlib import Path

import httpx
import pymupdf


def generate_synthetic_contract_pdf() -> bytes:
    """Generate a 3-page synthetic Master Services Agreement with tables and clauses."""
    doc = pymupdf.open()

    # --- Page 1: Engagement, Scope & Payment Schedule ---
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 60), "MASTER SERVICES AGREEMENT", fontsize=16, fontname="helv")
    p1.insert_text((50, 85), "Document Identifier: MSA-2026-SYNTH-001", fontsize=9, fontname="helv")
    p1.insert_text(
        (50, 115),
        "This Master Services Agreement ('Agreement') is entered into as of October 1, 2026,\n"
        "by and between Meridian Dynamics Corp ('Client') and Nexus Robotics LLC ('Contractor').",
        fontsize=10,
        fontname="helv",
    )
    p1.insert_text((50, 160), "1. SCOPE OF SERVICES", fontsize=12, fontname="helv")
    p1.insert_text(
        (50, 180),
        "Contractor agrees to design, manufacture, and deliver autonomous industrial inspection units\n"
        "as specified in Exhibit A. All deliverables must satisfy ISO-9001 quality criteria.",
        fontsize=10,
        fontname="helv",
    )
    p1.insert_text((50, 230), "2. PAYMENT TERMS AND SCHEDULE", fontsize=12, fontname="helv")
    p1.insert_text(
        (50, 250),
        "Total contract consideration is $850,000 USD payable across milestone deliverables:\n"
        "- Milestone 1 (Design Approval): $250,000 payable net 30 days from sign-off.\n"
        "- Milestone 2 (Prototype Validation): $350,000 payable net 30 days from laboratory test.\n"
        "- Milestone 3 (Final Site Deployment): $250,000 payable net 45 days from commissioning.",
        fontsize=10,
        fontname="helv",
    )
    p1.insert_text((50, 340), "3. PERFORMANCE EVALUATION TIERS", fontsize=12, fontname="helv")
    p1.insert_text(
        (50, 360),
        "Deliverables are audited using the standard quality rating matrix:\n"
        "Tier A: Exceptional (Grade Point 10) - 100% test pass rate with zero defect log.\n"
        "Tier B: Above Standard (Grade Point 8) - Minor cosmetic variance remediated within 48h.\n"
        "Tier C: Standard Acceptable (Grade Point 6) - Functional adherence under standard tolerances.\n"
        "Tier D: Unsatisfactory (Grade Point 2) - Mandatory re-engineering at Contractor expense.",
        fontsize=10,
        fontname="helv",
    )

    # --- Page 2: Liability, Indemnification & Confidentiality ---
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 60), "4. LIMITATION OF LIABILITY & INDEMNIFICATION", fontsize=12, fontname="helv")
    p2.insert_text(
        (50, 85),
        "Except for gross negligence or willful misconduct, neither party shall be liable for indirect,\n"
        "incidental, special, or consequential damages. Under Section 4.2, the aggregate liability cap\n"
        "of Contractor under this Agreement is strictly limited to $250,000 USD or the total fees paid\n"
        "by Client in the preceding twelve (12) months, whichever amount is lesser.",
        fontsize=10,
        fontname="helv",
    )
    p2.insert_text((50, 165), "5. CONFIDENTIALITY AND NON-DISCLOSURE", fontsize=12, fontname="helv")
    p2.insert_text(
        (50, 190),
        "Each party agrees to maintain in confidence all proprietary and technical information disclosed.\n"
        "Under Section 5.3, the confidentiality obligations shall survive termination and remain binding\n"
        "for a duration of three (3) years following the Effective Date of this Agreement.",
        fontsize=10,
        fontname="helv",
    )
    p2.insert_text((50, 270), "6. INTELLECTUAL PROPERTY RIGHTS", fontsize=12, fontname="helv")
    p2.insert_text(
        (50, 295),
        "All custom software and CAD schematics developed specifically for Client constitute work made\n"
        "for hire and belong exclusively to Client upon receipt of full milestone payment.",
        fontsize=10,
        fontname="helv",
    )

    # --- Page 3: Governing Law, Dispute Resolution & Signatures ---
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((50, 60), "7. GOVERNING LAW AND JURISDICTION", fontsize=12, fontname="helv")
    p3.insert_text(
        (50, 85),
        "This Agreement and all disputes arising hereunder shall be construed and governed in accordance\n"
        "with the laws of the State of Delaware, without regard to conflict of law principles.\n"
        "The parties submit to the exclusive jurisdiction of the state and federal courts in New Castle County.",
        fontsize=10,
        fontname="helv",
    )
    p3.insert_text((50, 160), "8. DISPUTE RESOLUTION AND ARBITRATION", fontsize=12, fontname="helv")
    p3.insert_text(
        (50, 185),
        "Any unresolved claim shall be submitted to confidential, binding commercial arbitration\n"
        "conducted in Wilmington, Delaware, under the rules of the American Arbitration Association (AAA).",
        fontsize=10,
        fontname="helv",
    )
    p3.insert_text((50, 260), "9. EXECUTION AND SIGNATURES", fontsize=12, fontname="helv")
    p3.insert_text(
        (50, 285),
        "IN WITNESS WHEREOF, the authorized representatives of the parties have executed this Agreement:\n\n"
        "For Meridian Dynamics Corp:                     For Nexus Robotics LLC:\n"
        "Signature: [Signed / Eleanor Vance]            Signature: [Signed / Marcus Thorne]\n"
        "Title: Chief Executive Officer                 Title: Managing Director\n"
        "Date: October 1, 2026                          Date: October 1, 2026",
        fontsize=10,
        fontname="helv",
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


DEMO_QUESTIONS = [
    {
        "category": "ANSWERABLE (Clause & Monetary Figure)",
        "query": "What is the limitation of liability cap under Section 4?",
        "expected_substring": "$250,000",
        "expected_page": 2,
        "expect_sufficient": True,
    },
    {
        "category": "ANSWERABLE (Legal Jurisdiction)",
        "query": "Which jurisdiction's laws govern this Agreement?",
        "expected_substring": "Delaware",
        "expected_page": 3,
        "expect_sufficient": True,
    },
    {
        "category": "ANSWERABLE (Time Duration)",
        "query": "What is the duration of the confidentiality obligations?",
        "expected_substring": "3",
        "expected_page": 2,
        "expect_sufficient": True,
    },
    {
        "category": "UNANSWERABLE (Absent Foreign Law / Safe Refusal)",
        "query": "What is the statutory penalty for contract breach under Australian commercial law?",
        "expected_substring": "Not found in records",
        "expected_page": None,
        "expect_sufficient": False,
    },
    {
        "category": "UNANSWERABLE (Private Personal Data / Safe Refusal)",
        "query": "What is Eleanor Vance's personal residential address and phone number?",
        "expected_substring": "Not found in records",
        "expected_page": None,
        "expect_sufficient": False,
    },
]


def run_demo(base_url: str = "http://127.0.0.1:8000", local_mode: bool = False):
    """Execute end-to-end demonstration against local FastAPI backend or in-process TestClient."""
    print("=" * 80)
    print(" AIR-GAPPED RAG: LOCAL-FIRST CONTRACT Q&A PROTOTYPE DEMONSTRATION")
    print("=" * 80)
    print("Testing local execution, exact page citations, and hallucination refusal.\n")

    client = None
    if not local_mode:
        try:
            http_client = httpx.Client(base_url=base_url, timeout=90.0)
            health_res = http_client.get("/health")
            if health_res.status_code == 200:
                client = http_client
                print(f"[✓] Connected to live backend at {base_url}: {health_res.json()}")
        except Exception:
            print(f"[*] Live backend at {base_url} not reachable. Switching to direct in-process mode...")

    if client is None:
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        health_res = client.get("/health")
        print(f"[✓] Initialized in-process FastAPI TestClient: {health_res.json()}")

    # 2. Generate and upload synthetic contract PDF
    print("\n[1/3] Generating synthetic 3-page Master Services Agreement...")
    pdf_bytes = generate_synthetic_contract_pdf()
    print(f"      Generated PDF: {len(pdf_bytes)} bytes, 3 pages.")

    print("\n[2/3] Uploading and extracting PDF via /api/v1/documents/upload...")
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("Master_Services_Agreement_2026.pdf", pdf_bytes, "application/pdf")},
    )
    if upload_res.status_code != 201:
        print(f"[✗] Upload failed ({upload_res.status_code}): {upload_res.text}")
        sys.exit(1)

    doc_data = upload_res.json()
    doc_id = doc_data["document_id"]
    print(f"      Assigned Document ID: {doc_id}")
    print(f"      Total Extracted Pages: {doc_data['total_pages']}")
    for p in doc_data["pages"]:
        print(f"      - Page {p['page_number']}: {p['word_count']} words, {p['char_count']} chars (ocr={p.get('ocr_applied', False)})")

    # 3. Index document in LanceDB
    print(f"\n[3/3] Vectorizing and indexing document chunks in LanceDB via Ollama nomic-embed-text...")
    index_res = client.post(f"/api/v1/documents/{doc_id}/index?reindex=true")
    if index_res.status_code != 200:
        print(f"[✗] Indexing failed ({index_res.status_code}): {index_res.text}")
        sys.exit(1)
    print(f"      Indexed: {index_res.json()['total_chunks']} chunks stored in local vector table.")

    # 4. Evaluate queries
    print("\n" + "=" * 80)
    print(" EVALUATING TEST QUERIES (CITATION INTEGRITY & SAFE REFUSAL)")
    print("=" * 80)

    all_passed = True
    for idx, item in enumerate(DEMO_QUESTIONS, 1):
        print(f"\n--- [Query {idx}/5] {item['category']} ---")
        print(f"Question: \"{item['query']}\"")

        t0 = time.perf_counter()
        ans_res = client.post(
            "/api/v1/answer",
            json={"query": item["query"], "document_id": doc_id},
        )
        latency = time.perf_counter() - t0

        if ans_res.status_code != 200:
            print(f"  [✗] Request failed with HTTP {ans_res.status_code}: {ans_res.text}")
            all_passed = False
            continue

        resp = ans_res.json()
        answer = resp.get("answer", "")
        sufficient = resp.get("evidence_sufficient", False)
        sources = resp.get("sources", [])

        print(f"  Answer:                \"{answer}\"")
        print(f"  Evidence Sufficient:   {sufficient} (Expected: {item['expect_sufficient']})")
        print(f"  Inference Latency:     {latency:.2f}s")

        # Validation
        passed = True
        if item["expect_sufficient"]:
            if not sufficient:
                print(f"  [FAIL] Expected sufficient evidence, but model flagged insufficient.")
                passed = False
            if item["expected_substring"].lower() not in answer.lower():
                print(f"  [FAIL] Missing expected keyword '{item['expected_substring']}' in answer.")
                passed = False
            if not sources:
                print(f"  [FAIL] Expected source citations, but got none.")
                passed = False
            else:
                cited_pages = [s["page_number"] for s in sources]
                print(f"  Verified Citations:    Page(s) {cited_pages} (Expected Page: {item['expected_page']})")
                if item["expected_page"] not in cited_pages:
                    print(f"  [FAIL] Did not cite expected physical Page {item['expected_page']}.")
                    passed = False
                for s in sources:
                    print(f"    - Citation: Page {s['page_number']} of '{s['filename']}'")
                    excerpt_text = s.get("excerpt", s.get("passage", ""))
                    print(f"      Excerpt: \"{excerpt_text[:90]}...\"")
        else:
            if sufficient:
                print(f"  [FAIL] Hallucination detected! Unanswerable query marked as sufficient.")
                passed = False
            if answer != "Not found in records":
                print(f"  [FAIL] Expected strict refusal 'Not found in records', got: '{answer}'")
                passed = False
            if sources:
                print(f"  [FAIL] Fabricated sources detected on refusal: {sources}")
                passed = False
            else:
                print(f"  Verified Safe Refusal: 0 citations fabricated (sources=[])")

        if passed:
            print(f"  Result: [PASS ✓]")
        else:
            print(f"  Result: [FAIL ✗]")
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print(" ALL 5 DEMONSTRATION VERIFICATIONS PASSED!")
        print(" Local contract question-answering prototype with citation integrity verified.")
    else:
        print(" SOME DEMO CHECKS ENCOUNTERED ISSUES. Review output above.")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Air-Gapped RAG local contract demonstration.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="FastAPI backend base URL")
    parser.add_argument("--local", action="store_true", help="Force direct in-process mode via FastAPI TestClient")
    args = parser.parse_args()
    run_demo(base_url=args.url, local_mode=args.local)
