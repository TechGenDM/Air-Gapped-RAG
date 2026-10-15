# Contributing to Air-Gapped RAG

Thank you for your interest in contributing to Air-Gapped RAG! We welcome contributions that maintain the highest standards of local privacy, code quality, and verifiable evidence generation.

---

## Code of Conduct

All contributors are expected to uphold our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any violations to [devasishmishra74@gmail.com](mailto:devasishmishra74@gmail.com).

---

## Core Tenets

When contributing to this project, adhere to these fundamental principles:
1. **100% Local & Air-Gapped:** Never introduce external network calls, cloud API dependencies, telemetry, or remote tracking. All LLM inference and embeddings must run on local infrastructure (e.g. Ollama).
2. **Page & Citation Integrity:** All text extraction must strictly preserve 1-indexed physical page numbering for verifiable citations.
3. **Defense in Depth:** Enforce file size bounds, binary header validation (`%PDF-`), and path traversal sanitization on all user input.
4. **Comprehensive Test Coverage:** Every new endpoint, service method, or UI component must include corresponding unit and integration tests.

---

## Getting Started

### Fork & Clone
```bash
git clone https://github.com/TechGenDM/Air-Gapped-RAG.git
cd Air-Gapped-RAG
```

### Backend Development Setup
```bash
cd backend
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -v
```

### Frontend Development Setup
```bash
cd frontend
pnpm install
pnpm run lint
pnpm exec tsc --noEmit
pnpm run dev
```

---

## Commit Guidelines

We enforce the [Conventional Commits](https://www.conventionalcommits.org/) standard. Commit messages must follow the format:

```text
<type>(<scope>): <subject>
```

Common types:
* `feat`: A new feature
* `fix`: A bug fix
* `test`: Adding or updating test suites
* `docs`: Documentation changes
* `style`: Formatting, CSS updates
* `refactor`: Code restructuring without functional changes
* `chore`: Build tasks, package updates, tooling config
* `ci`: Continuous integration workflows

---

## Submitting Pull Requests

1. Create a descriptive feature branch: `git checkout -b feat/your-feature-name`.
2. Ensure all backend tests pass: `pytest -v` from `backend/`.
3. Ensure frontend builds and lints cleanly: `pnpm run lint && pnpm exec tsc --noEmit` from `frontend/`.
4. Submit a Pull Request following the PR template and link any relevant issues.
