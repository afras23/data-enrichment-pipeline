# Implementation Plan: Data Extraction & Enrichment Pipeline

**Estimated build effort:** 10–12 hours (coding and tests), aligned with the project definition.  
**Tooling note:** Implementation uses **Cursor** following `docs/AI-ENGINEERING-PLAYBOOK.md` and portfolio standards.

Each phase is sized for **1–2 hours**, ends in a **working state**, and lists **acceptance criteria** and a **recommended commit message**. Do not start a phase until the previous phase passes acceptance.

---

## Phase 1: Repository scaffold and runnable API shell

**Goal:** Reproducible project layout, tooling, and a minimal FastAPI app with health endpoint and Docker Compose (app + PostgreSQL).

**Tasks**

- [ ] Create layout per `PORTFOLIO-ENGINEERING-STANDARD.md` (adjusted names for this domain: `services/enrichment_pipeline.py`, `integrations/openai_client.py`, `integrations/http_fetcher.py`, etc.).
- [ ] Add `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `Makefile` (`help`, `dev`, `test`, `lint`, `format`, `typecheck`, `migrate`, `docker`).
- [ ] FastAPI `create_app`, `/api/v1/health`, global error handler stub, CORS as needed for local demo.
- [ ] `Dockerfile` (multi-stage, non-root) + `docker-compose.yml` with Postgres healthcheck.
- [ ] `.github/workflows/ci.yml`: install, ruff, mypy, pytest against Postgres service.
- [ ] `.env.example` with documented variables (database URL, OpenAI key placeholders, concurrency limits).

**Acceptance criteria**

- `docker compose up --build` starts **app** and **db**; `GET /api/v1/health` returns **200** with JSON status.
- CI workflow passes on a clean branch (lint + typecheck + tests with **zero tests** or a single smoke test).
- No secrets committed; `.env` ignored.

**Commit message:** `chore: initial scaffold with FastAPI, Docker, and CI`

---

## Phase 2: Configuration, logging, and database foundation

**Goal:** Validated settings, structured logging foundation, async SQLAlchemy + Alembic, initial schema for runs and jobs.

**Tasks**

- [ ] `Settings` via `pydantic-settings` (OpenAI model name, timeouts, max crawl bytes, concurrency, cost limits).
- [ ] Custom exception hierarchy (`AppError` and domain-specific subclasses).
- [ ] Async engine + session factory; dependency-injected DB session for routes.
- [ ] Alembic initial migration: `pipeline_run`, `company_job` (or equivalent) with statuses, timestamps UTC, foreign keys.
- [ ] Repository stubs for creating runs and inserting jobs.

**Acceptance criteria**

- `make migrate` (or `alembic upgrade head`) applies cleanly on empty Postgres.
- App boots with test `DATABASE_URL`; `/api/v1/health/ready` checks DB (if included this phase) or DB verified in integration test.

**Commit message:** `feat: add settings, exceptions, and initial database schema`

---

## Phase 3: Website discovery module

**Goal:** Given a normalised company name, produce a ranked website URL with confidence metadata (strategy per ADR 001).

**Tasks**

- [ ] `WebsiteDiscoveryService` with pluggable strategy (start with **search-assisted or heuristic** implementation as per ADR—mock external search in tests).
- [ ] Persist discovery candidates on `company_job` for audit.
- [ ] Unit tests with mocked HTTP; parameterised cases for ambiguous names.

**Acceptance criteria**

- Discovery returns **terminal failure** (no URL) without throwing unhandled exceptions.
- All network I/O behind an integration client interface; **tests use mocks**.

**Commit message:** `feat: add website discovery with audit metadata`

---

## Phase 4: HTTP fetch and HTML text extraction

**Goal:** Robust fetching and BeautifulSoup-based visible text extraction with strict limits.

**Tasks**

- [ ] Async `httpx` client: timeouts, redirect cap, max body size, user-agent from settings.
- [ ] SSRF protections: block private IPs and suspicious schemes (document any limitations).
- [ ] BeautifulSoup parsing: remove scripts/styles; extract text and optional meta description.
- [ ] Unit tests with HTML fixtures; integration test with `respx` or mock transport.

**Acceptance criteria**

- Malformed HTML still yields best-effort text or a controlled scrape error.
- Large responses truncated per settings before parsing.

**Commit message:** `feat: add bounded web fetch and HTML text extraction`

---

## Phase 5: OpenAI enrichment client and prompts

**Goal:** Versioned prompts, structured JSON output validated by Pydantic, cost and token tracking (ADR 002).

**Tasks**

- [ ] `EnrichmentAIService` calling OpenAI with **system/user** separation; prompt keys versioned (`company_enrichment_v1`).
- [ ] Parse and validate **industry, size, tech stack, contacts** into domain models.
- [ ] Cost estimation logged per call; respect daily budget settings.
- [ ] Prompt-injection mitigation on concatenated page text (length limit + pattern warnings per playbook).

**Acceptance criteria**

- Invalid LLM JSON → **validation error path** with logged preview (≤200 chars), no crash.
- Unit tests use **mocked** OpenAI client; no real API in CI.

**Commit message:** `feat: add OpenAI enrichment with versioned prompts and validation`

---

## Phase 6: Data quality scoring and pipeline orchestration

**Goal:** Deterministic quality score (ADR 003) and a single orchestrator that chains discovery → scrape → enrich → score.

**Tasks**

- [ ] `QualityScoringService`: weighted subscores and documented thresholds in settings.
- [ ] `EnrichmentPipelineService`: state transitions on `company_job`; structured logging with correlation id context.
- [ ] Persist final enriched payload + quality breakdown as JSON.

**Acceptance criteria**

- End-to-end **integration test** in CI: mocked HTTP + mocked OpenAI → completed job with scores.
- Row-level terminal status always set (`completed`, `failed`, `partial`).

**Commit message:** `feat: implement enrichment pipeline with quality scoring`

---

## Phase 7: Batch API and result retrieval

**Goal:** Submit batches, poll run status, list paginated results, export enriched records.

**Tasks**

- [ ] `POST /api/v1/runs` (or `/batches`) accepting company names; create `pipeline_run` and enqueue jobs.
- [ ] `GET /api/v1/runs/{id}` with progress counts; `GET /api/v1/runs/{id}/companies` with **pagination**.
- [ ] Background processing: `asyncio` worker or FastAPI `BackgroundTasks` with **bounded concurrency** (settings).
- [ ] Optional: `GET` export JSON/CSV for completed run.

**Acceptance criteria**

- Batch of **N** companies processes with observable progress; no unbounded memory growth from stored HTML.
- API responses are Pydantic models with consistent `status` / `metadata` envelope per standard.

**Commit message:** `feat: add batch run API with progress and paginated results`

---

## Phase 8: Observability hardening

**Goal:** Correlation IDs, structured JSON logs, production-grade metrics and readiness (per 10/10 addendum).

**Tasks**

- [ ] Correlation middleware; propagate to logs for pipeline steps.
- [ ] `/api/v1/metrics`: run/job counts, success rates, average quality score, OpenAI cost aggregates.
- [ ] `/api/v1/health/ready`: DB + optional OpenAI configuration check.
- [ ] Graceful shutdown: cancel or await in-flight tasks cleanly where feasible.

**Acceptance criteria**

- Single request traceable via `X-Correlation-ID` through logs for a batch operation.
- Metrics return **non-placeholder** values after processing a test batch.

**Commit message:** `feat: add correlation IDs, metrics, and readiness checks`

---

## Phase 9: Evaluation harness and test suite expansion

**Goal:** `make evaluate` and 40+ tests with coverage on core logic.

**Tasks**

- [ ] `eval/test_set.jsonl` with anonymised fixtures; `scripts/evaluate.py` computing field-level and aggregate metrics against mocked or recorded responses.
- [ ] Parameterised tests for scoring, discovery edge cases, retry classification.
- [ ] Tests: idempotency on batch submission where defined, concurrency smoke, prompt-injection case.

**Acceptance criteria**

- `pytest` passes with **≥40** tests; coverage on `services/` and scoring modules meets agreed threshold (e.g. **≥80%** on core packages).
- `make evaluate` produces a JSON report artifact under `eval/results/`.

**Commit message:** `test: add evaluation script and expand automated tests`

---

## Phase 10: Documentation and polish

**Goal:** Case-study README, runbook, CHANGELOG; pre-commit; final quality gate.

**Tasks**

- [ ] `README.md` per Engineering Standard §11 (problem, solution, architecture sketch, how to run, evaluation summary).
- [ ] `docs/runbook.md`: operations, common failures, cost limits.
- [ ] `.pre-commit-config.yaml` aligned with Makefile.
- [ ] Run 10/10 checklist from `PORTFOLIO-10-OUT-OF-10-ADDENDUM.md` for applicable items.

**Acceptance criteria**

- New developer: `cp .env.example .env`, `docker compose up`, documented curl works.
- No `TODO`/`FIXME` in code; lint + typecheck + tests green.

**Commit message:** `docs: add README, runbook, and operational polish`

---

## Phase ordering summary

1. Scaffold and CI  
2. Config + DB  
3. Website discovery  
4. Fetch + BeautifulSoup  
5. OpenAI enrichment  
6. Quality score + orchestration  
7. Batch API  
8. Observability  
9. Eval + tests  
10. README + runbook + polish  

---

## Dependency graph (high level)

```text
Phase 1 → Phase 2 → Phase 3 ─┐
              ↓              │
         Phase 4 ←───────────┘
              ↓
         Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9 → Phase 10
```

Phases 3 and 4 can overlap slightly in a single session **only if** Phase 2 is done; prefer completing Phase 3 before Phase 4 to lock discovery contracts before scrape integration.
