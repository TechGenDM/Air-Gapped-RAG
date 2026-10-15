## Description

Please provide a summary of the changes and the related issue/motivation.

Fixes #(issue)

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] CI/CD or tooling enhancement

## Quality Checklist

- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] All new and existing tests pass locally (`uv run pytest -v` in `backend/`)
- [ ] Frontend builds and passes linter (`pnpm run lint` & `pnpm exec tsc --noEmit` in `frontend/`)
- [ ] **Air-Gap Verification**: No external network requests, third-party analytics, or remote API endpoints have been added.
