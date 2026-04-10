# Data Extraction & Enrichment Pipeline

Batch pipeline: given company names, **discover** a website, **scrape** key pages, **enrich** with structured LLM output (industry, size band, tech stack, contacts), **score** data quality, and **persist** enriched records.

Stack: Python 3.12+, FastAPI, SQLAlchemy (async), OpenAI API, BeautifulSoup, PostgreSQL (or SQLite for dev/tests).

## Quick start

Install dependencies (see `requirements.txt` and `requirements-dev.txt`), configure environment (see `.env.example` if present), run migrations if using PostgreSQL, then start the API with Uvicorn as documented in the project docs.

## Demo and evaluation

For a **repeatable offline run** against sample company lists (mocked web + AI, no external calls):

1. Review sample inputs under `data/sample_run/` (`companies.yaml`, `expected_enrichment.yaml`).
2. Run **`make evaluate`** to execute the production pipeline on that batch and generate Markdown and JSON reports under `eval/reports/`.
3. See **`eval/README.md`** for the evaluation workflow, optional CLI flags, and the pipeline dependency diagram (`eval/pipeline-dag.mmd`).

Mirror copies of the sample YAML files are kept in `tests/fixtures/sample_inputs/` for tests and CI.

## Documentation

Design and architecture notes live under `docs/` (problem definition, architecture, ADRs, implementation plan).
