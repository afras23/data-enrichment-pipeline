# Evaluation workflow

This directory holds **offline evaluation** for the Data Extraction & Enrichment Pipeline: the same production orchestration (`EnrichmentPipelineService`) runs against YAML-defined company batches while **HTTP and OpenAI are mocked**, so results are reproducible without network access or API spend.

## How to run

From the repository root:

```bash
make evaluate
```

This reads `data/sample_run/companies.yaml`, executes the pipeline, and writes:

- `eval/reports/evaluation_report.md` — human-readable summary (run outcome, per-company quality subscores, expectation checks)
- `eval/reports/evaluation_summary.json` — machine-readable summary for dashboards or CI artifacts
- `eval/reports/.evaluation.sqlite` — ephemeral SQLite DB for the run (gitignored)

Optional flags:

```bash
python -m eval.run_evaluation --help
```

## What is measured

- **Extraction completeness** — quality subscore `completeness` (six AI fields filled vs empty)
- **Quality scores** — `final_score` and subscores (`evidence_strength`, `consistency`, `website_confidence`)
- **Run outcomes** — run status (`completed` / `partial` / `failed`), per-record status, aggregate succeeded/failed counts, total mocked AI cost

Soft expectations live in `data/sample_run/expected_enrichment.yaml` and are checked at the end of the run (non-zero exit if a check fails).

## Pipeline DAG

The Mermaid source is `pipeline-dag.mmd`. Equivalent diagram:

```mermaid
flowchart TD
    subgraph init["Run initialization"]
        R[Create EnrichmentRun] --> L[Company list queued]
    end

    subgraph per["Per company (concurrent, semaphored)"]
        L --> P0[Insert record PENDING]
        P0 --> D[Website discovery<br/>probe candidate URLs]
        D --> S[Site scraping<br/>homepage + nav-linked pages]
        S --> CC{Cost limit OK?}
        CC -->|no| F1[Record FAILED / limit]
        CC -->|yes| A[AI enrichment<br/>structured JSON]
        A --> Q[Quality scoring<br/>completeness + evidence + consistency + site confidence]
        Q --> P1[Record COMPLETED]
        D -.->|no resolvable site| P2[Record PARTIAL]
        S -.->|no pages / scrape errors| P2
        A -.->|LLM / validation errors| P2
    end

    subgraph fin["Run finalization"]
        P1 --> T[Update run totals<br/>succeeded / failed / cost]
        P2 --> T
        F1 --> T
        T --> M[Optional alerting<br/>on outcome thresholds]
    end
```

## Sample inputs

Authoritative copies for tests also live under `tests/fixtures/sample_inputs/` (same schema as `data/sample_run/`).
