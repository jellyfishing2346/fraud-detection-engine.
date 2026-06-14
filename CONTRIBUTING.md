# Contributing to Fraud Detection Engine

Thank you for your interest in contributing. This is a production-grade financial system — contributions are held to a high standard. Please read this guide **in full** before opening an issue or pull request. PRs that do not follow these guidelines will be closed without review.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Before You Start](#before-you-start)
- [Development Setup](#development-setup)
- [Branch Naming](#branch-naming)
- [Commit Messages](#commit-messages)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [Security Vulnerabilities](#security-vulnerabilities)
- [What We Will Not Accept](#what-we-will-not-accept)

---

## Code of Conduct

All contributors are expected to be respectful, professional, and constructive. Harassment, discrimination, or bad-faith behaviour of any kind will result in permanent removal from the project. By contributing, you agree to uphold these standards in all project spaces — issues, pull requests, discussions, and code reviews.

---

## Before You Start

- **Search first.** Check [open issues](../../issues) and [open pull requests](../../pulls) before starting work. Duplicate efforts will be closed.
- **Open an issue before a PR.** For any non-trivial change (new feature, architectural change, significant refactor), open an issue to discuss the approach first. Work begun without prior discussion may be declined regardless of quality.
- **Small, focused PRs only.** One logical change per PR. A PR that mixes a bug fix with a refactor with a new feature will be closed and asked to be split.
- **No unsolicited refactors.** Do not refactor code unrelated to your change. Keep the diff minimal and on-topic.

---

## Development Setup

### Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Python | 3.12 |
| PostgreSQL | 16 |
| Redis | 7 |
| Apache Kafka | 3.7 (KRaft mode) |
| pre-commit | 3.x |

### Steps

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/fraud-detection-engine.git
cd fraud-detection-engine

# 2. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Copy and configure environment variables
cp .env.example .env
# Edit .env with your local credentials — never commit .env

# 5. Install pre-commit hooks (mandatory)
pip install pre-commit
pre-commit install

# 6. Verify pre-commit hooks run cleanly
pre-commit run --all-files
```

Pre-commit hooks run automatically on every commit. They enforce formatting, linting, and security checks. **Do not bypass them with `--no-verify`.** If a hook fails, fix the underlying issue.

---

## Branch Naming

All branches must follow this pattern:

```
<type>/<short-description>
```

| Type | When to use |
|------|-------------|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `test/` | Adding or improving tests |
| `refactor/` | Code restructuring with no behaviour change |
| `chore/` | Dependency bumps, CI changes, tooling |
| `security/` | Security-related changes |

**Examples:**

```
feat/velocity-feature-ttl
fix/redis-fallback-timeout
docs/kafka-setup-guide
test/score-endpoint-edge-cases
```

Branches that do not match this pattern will have their PR closed with a request to rename.

---

## Commit Messages

This project uses the [Conventional Commits](https://www.conventionalcommits.org/) specification. Every commit **must** follow this format:

```
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```

### Rules

- **Subject line:** 72 characters max, imperative mood, no trailing period.
- **Body:** Wrap at 72 characters. Explain *why*, not *what* — the diff already shows what.
- **Footer:** Reference issues with `Closes #<n>` or `Refs #<n>`.
- **No merge commits** in your branch. Rebase onto `main` before opening a PR.

### Valid types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Test additions or changes |
| `refactor` | Code change with no functional effect |
| `perf` | Performance improvement |
| `chore` | Tooling, dependencies, CI |
| `security` | Security fix or hardening |

### Valid scopes

`api`, `ml`, `kafka`, `redis`, `db`, `auth`, `frontend`, `infra`, `ci`, `deps`

### Examples

```
feat(ml): add SHAP explainability to score endpoint

Exposes per-feature attribution in the /score response so reviewers
can understand why a transaction was flagged without inspecting model
internals manually.

Closes #42
```

```
fix(redis): wrap velocity feature reads with graceful fallback

Redis connection errors previously caused the entire scoring pipeline
to raise 500. Now falls back to a zero-velocity assumption so scoring
remains available during cache outages.

Refs #38
```

Commits that do not follow this format will be squashed or the PR will be asked to rebase and reword.

---

## Coding Standards

### Python style

- **Formatter:** `ruff format` (configured in `pyproject.toml`). All code must be formatted before committing.
- **Linter:** `ruff check` with the rule sets in `pyproject.toml` (`E`, `W`, `F`, `I`, `B`, `UP`). Zero warnings allowed.
- **Line length:** 88 characters (enforced by ruff).
- **Imports:** `isort`-compatible ordering enforced by `ruff --select I`. Stdlib → third-party → local, each group separated by a blank line.
- **Type hints:** All public function signatures must include type hints. Use `from __future__ import annotations` where needed.
- **No `print()` in production code.** Use the project's logging setup (`import logging`).
- **No commented-out code.** Remove dead code before opening a PR.
- **No hardcoded secrets, credentials, or environment-specific values** anywhere in the codebase. Use environment variables and `.env.example` for documentation.

### FastAPI conventions

- All route handlers must declare proper response models (`response_model=`).
- HTTP status codes must be explicit (`status_code=200`, not left as default where non-obvious).
- Dependency injection via `Depends()` — do not instantiate clients inside route handlers.
- Errors must be raised as `HTTPException` with a clear `detail` string.

### ML / data conventions

- Trained artefacts (`.pkl`, `.joblib`, `.json` model files) must **never** be committed to the repository. They belong in object storage or a model registry.
- Notebooks under `backend/notebooks/` are exploratory only and are explicitly excluded from linting. Do not import notebook code into the main application.
- Feature engineering logic lives in `backend/ml/` and must have corresponding unit tests.

### Security-sensitive areas

Changes to any of the following require extra scrutiny and explicit maintainer sign-off:

- Authentication / authorisation logic
- Kafka consumer offset management
- Database migrations (`alembic/`)
- `.env.example` (ensure no real values are ever added)
- Any code that handles raw transaction data

---

## Testing Requirements

**No PR that adds or changes application logic will be merged without tests.**

### Coverage requirements

| Area | Minimum coverage |
|------|-----------------|
| `backend/api/` | 90% |
| `backend/ml/` | 85% |
| `backend/kafka_pipeline/` | 75% |
| Overall | 80% |

### Running tests

```bash
# Run the full test suite
pytest backend/tests/ -v

# Run with coverage report
pytest backend/tests/ --cov=backend --cov-report=term-missing

# Run a specific test file
pytest backend/tests/test_score.py -v
```

### Test standards

- Tests live in `backend/tests/` and mirror the module structure they test.
- Test file names must be `test_<module>.py`.
- Test function names must be `test_<behaviour>_<condition>` — e.g., `test_score_returns_high_risk_for_velocity_spike`.
- Do not test implementation details; test observable behaviour and contracts.
- Use `pytest` fixtures for shared setup. Do not use `unittest.TestCase`.
- External services (Redis, Kafka, PostgreSQL) must be mocked in unit tests using `pytest-mock` or `unittest.mock`. Integration tests that require live services must be tagged `@pytest.mark.integration` and are excluded from the default test run.
- Tests must be deterministic. No random seeds, no time-dependent behaviour without mocking.

---

## Pull Request Process

### Checklist — every PR must satisfy all of these

- [ ] Branch name follows the naming convention
- [ ] All commits follow Conventional Commits format
- [ ] `pre-commit run --all-files` passes with zero errors
- [ ] `pytest backend/tests/` passes with zero failures
- [ ] Coverage thresholds are met (run `pytest --cov`)
- [ ] No new linting warnings (`ruff check backend/`)
- [ ] No hardcoded secrets or credentials
- [ ] No commented-out code
- [ ] PR description explains *why* the change is needed, not just *what* it does
- [ ] Relevant documentation updated (API.md, ARCHITECTURE.md, etc.) if behaviour changed
- [ ] Issue number referenced in the PR description (`Closes #n` or `Refs #n`)

### PR description template

When you open a pull request, fill in this template:

```markdown
## Summary
<!-- Why is this change needed? What problem does it solve? -->

## Changes
<!-- Bullet-point summary of what changed -->

## Testing
<!-- How did you test this? What edge cases did you consider? -->

## Related Issues
<!-- Closes #n -->

## Checklist
- [ ] pre-commit passes
- [ ] Tests pass and coverage thresholds met
- [ ] Documentation updated if needed
- [ ] No secrets or credentials in the diff
```

### Review process

- All PRs require at least **one approving review** from a maintainer before merge.
- Address every review comment before requesting re-review. Do not dismiss comments without a written response.
- If a review comment is marked `[BLOCKING]`, it must be resolved before the PR can proceed.
- Do not merge your own PRs.
- Maintainers reserve the right to close any PR that does not meet the standards in this guide without further explanation.

### After approval

- Rebase onto `main` if there are merge conflicts (do not use merge commits).
- The maintainer will squash-merge the PR. Your individual commits do not need to be perfectly clean, but the PR title must be a valid Conventional Commit subject line — it becomes the squash commit message.

---

## Reporting Issues

### Bug reports

Use the **Bug Report** issue template. A valid bug report must include:

1. **Environment:** Python version, OS, relevant service versions.
2. **Steps to reproduce:** Exact steps, minimal and complete.
3. **Expected behaviour:** What should happen.
4. **Actual behaviour:** What actually happens, including full error tracebacks.
5. **Logs:** Relevant log output (redact any real transaction data or credentials).

Issues missing any of these will be labelled `needs-info` and closed after 7 days without a response.

### Feature requests

Use the **Feature Request** issue template. Include:

1. The problem you are trying to solve (not just the feature you want).
2. Why existing functionality does not address it.
3. Any alternative approaches you have considered.

Feature requests without a clear problem statement will be closed.

### Stale issues

Issues with no activity for 30 days will be labelled `stale` and closed after a further 7 days unless there is renewed discussion.

---

## Security Vulnerabilities

**Do not open a public issue for security vulnerabilities.**

This is a financial fraud detection system — security issues are treated with the highest priority. If you discover a security vulnerability:

1. Email the maintainer directly at **faizanakhan2003@gmail.com** with the subject line `[SECURITY] <brief description>`.
2. Include a description of the vulnerability, steps to reproduce, and potential impact.
3. Allow up to 72 hours for an initial response before any public disclosure.
4. Do not publish details of the vulnerability until a fix has been released and you have been notified.

Responsible disclosure is appreciated and will be credited in the release notes.

---

## What We Will Not Accept

The following will be closed immediately:

- PRs that add features not discussed in an issue first
- PRs that mix unrelated changes
- PRs with failing tests or linting errors
- PRs with hardcoded credentials, API keys, or environment-specific values
- PRs with commented-out code or debug `print()` statements
- PRs that bypass pre-commit hooks (`--no-verify`)
- PRs without a proper description
- PRs that do not reference an issue
- Commits with messages like `fix`, `wip`, `update`, `changes`, or similar non-descriptive text
- Branches named `fix-bug`, `my-feature`, `patch`, or anything not following the naming convention
- Any code that stores, logs, or transmits real transaction data or PII without explicit maintainer approval

---

## Questions

If you are unsure about anything in this guide, open a [Discussion](../../discussions) rather than an issue. Issues are reserved for confirmed bugs and approved feature requests.

---

*This contributing guide is enforced strictly. The bar is high because this is a financial system where correctness and security matter. We appreciate the time you put into contributing — making sure it meets these standards is how we respect that effort.*
