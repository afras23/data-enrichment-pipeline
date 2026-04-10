# Runbook: Data Extraction & Enrichment Pipeline

Operational notes for running, debugging, and extending the service in development or staging.

**Docker Compose:** from the repo root, `docker compose up --build -d` starts PostgreSQL and the API (default host ports **8001** for HTTP and **5433** for Postgres—see `docker-compose.yml`). The API entrypoint runs **`alembic upgrade head`** before Uvicorn.

---

## Health checks

| Endpoint | Purpose | Expected |
|----------|---------|----------|
| `GET {api_prefix}/health` | **Liveness** | `200`, body `{"status":"healthy","timestamp":...}` |
| `GET {api_prefix}/health/ready` | **Readiness** | `200` with `"status":"ready"` and `"database":"ok"` when DB accepts `SELECT 1` |
| `GET {api_prefix}/metrics` | **Aggregates** | Run/company metrics from DB + pool stats (`db_pool_size`, `db_pool_checked_out`) |

Default `api_prefix` is `/api/v1`. In Kubernetes-style setups, point **liveness** at `/health` and **readiness** at `/health/ready`.

---

## Common failure scenarios

| Symptom | Likely cause | What to check |
|---------|----------------|---------------|
| Ready probe **degraded**, `database` not `ok` | DB down, wrong `DATABASE_URL`, firewall | Logs, connection string, Postgres `pg_isready` |
| Run stays **pending** / never progresses | Worker not processing (API process died after `202`) | Background task runs in same process as Uvicorn—ensure long-lived workers; check logs for exceptions in `process_run` |
| Many rows **partial**, `Website could not be resolved` | Heuristic discovery missed (slug ≠ domain) | `discovery_metadata.candidates_tried` on record; consider ADR 001 search-assisted discovery |
| Rows **partial**, scrape errors | Site blocked, 404 on follow-ups, non-HTML | `scrape_bundle.fetch_errors`; reduce `MAX_PAGES_PER_COMPANY` if timeouts |
| Rows **failed**, `COST_LIMIT_EXCEEDED` | `MAX_COST_PER_RUN_USD` too low vs batch size × per-call cost | Raise cap or reduce batch size; see `total_ai_cost_usd` on run |
| **429 / timeout** from OpenAI | Rate limits, network | Retries in client (see `openai_client.py`); backoff; model/region |
| Low **quality scores** everywhere | Thin pages, wrong site, or industry mismatch | `quality_report.subscores`; `website_confidence` |

---

## Retry / recovery notes

- **Per-run retry:** Not implemented as an automatic queue. **Recovery:** submit a **new** run with a subset of company names (or re-run after fixing config). Deduplicate in the caller if needed.
- **Discovery:** Probes multiple URL candidates sequentially; **connection errors** on one candidate are skipped and the next is tried (see `WebsiteDiscoveryService`).
- **HTTP client:** `WebFetchClient` is the single place to add **retry policies**; ADR 005 describes richer retries and circuit breakers—**verify** current behaviour in `app/integrations/web_client.py` before assuming retries are enabled.
- **OpenAI:** Client wraps API errors into `EnrichmentAIError` where appropriate; failed rows are **partial** with an error code—**not** silently retried in the pipeline loop unless the client raises retryable errors internally.
- **Idempotency:** Posting the same `POST /enrichment/run` twice creates **two** runs. Avoid duplicate charges by **client-side** idempotency keys if you add them at the API layer later.

---

## How to add new extraction fields

1. **Schema** — Extend `AIEnrichmentResult` in `app/schemas/domain.py` (and any prompt examples in `app/services/ai/prompts.py`).
2. **Prompts** — Ask the model to emit the new JSON keys; keep output **valid JSON** (see OpenAI client).
3. **Persistence** — `ai_payload` is JSON; new fields are stored automatically once `model_dump()` includes them.
4. **Quality scoring** — Update `QualityScoringService.build_report` in `app/services/quality_scoring.py` (e.g. include the new field in **completeness** `total` / `filled` counts).
5. **API** — If exposed in list views, extend `CompanyRecordDetail` / summaries in `app/api/schemas.py` if you flatten fields (today full payloads are returned on detail).
6. **Tests** — Add unit tests for scoring and integration tests for the pipeline with mocked AI returning the new shape.

---

## How to adjust scoring rules

Rules live in **`app/services/quality_scoring.py`**:

- **Completeness** — fraction of populated fields among a fixed set (currently six AI-related checks).
- **Evidence strength** — derived from visible text length, page count, and fetch errors.
- **Consistency** — overlap between scraped text and industry/tech tokens from the model.
- **Final score** — weighted sum: `0.30×completeness + 0.30×evidence + 0.25×consistency + 0.15×website_confidence` (clamped to `[0,1]`).

To change behaviour:

1. Edit weights or formulas in `build_report`.
2. Add/adjust `notes` in `QualityReport` for user-visible explanations.
3. Run **`make test`** (especially `tests/unit/test_quality_scoring.py` and edge-case tests).

Thresholds for **alerting** (not the same as scoring) are in **`app/config.py`**: `ALERT_AVG_QUALITY_THRESHOLD`, `ALERT_CONSECUTIVE_FAILURE_THRESHOLD`.

---

## How to run evaluation

Offline evaluation uses the **same** `EnrichmentPipelineService` with **mocked** HTTP and OpenAI—no network or API spend.

```bash
make evaluate
```

- Inputs: **`data/sample_run/companies.yaml`**, expectations **`data/sample_run/expected_enrichment.yaml`**.
- Outputs: **`eval/reports/evaluation_report.md`**, **`eval/reports/evaluation_summary.json`** (gitignored except `.gitignore` under `eval/reports/`).
- Details: **`eval/README.md`**, diagram **`eval/pipeline-dag.mmd`**.

CLI options:

```bash
python -m eval.run_evaluation --help
```

---

## Logs and correlation

- Pass **`X-Correlation-ID`** on API requests; it is stored on the run when provided.
- Search logs by `correlation_id`, `run_id`, and company name prefix in error logs.

---

## Quick reference: env vars

See **`.env.example`** and **`app/config.py`**. Critical for production:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `MAX_COST_PER_RUN_USD`
- `PIPELINE_MAX_CONCURRENCY`
- `MAX_PAGES_PER_COMPANY`
