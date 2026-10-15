# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

---

## Security Guarantees & Privacy Boundary

Air-Gapped RAG is designed specifically for high-security, sovereign, and privacy-critical environments:
* **Zero Outbound Network Access:** Document processing, vector generation, and language model inference run entirely on localhost without external API requests.
* **Privacy-Compliant Logging:** Document contents and extracted text are sanitized and excluded from server log outputs.
* **Safe Ingestion:** File uploads are protected against Zip/PDF bombs, path traversal attacks, and malformed binary payloads.

---

## Reporting a Vulnerability

If you discover a security vulnerability within Air-Gapped RAG, please send an email to:

**[devasishmishra74@gmail.com](mailto:devasishmishra74@gmail.com)**

Please include:
* Description of the vulnerability and attack vector.
* Steps to reproduce the issue (proof of concept).
* Potential impact on local confidentiality, integrity, or system availability.

We will acknowledge receipt within 48 hours and work with you to remediate the vulnerability prior to public disclosure.
