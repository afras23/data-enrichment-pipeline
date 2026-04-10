# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Documentation

- Rewrote **`README.md`** as a case study (problem, solution, architecture, features, stack, run, config, API, evaluation, testing, future work).
- Expanded **`docs/architecture.md`** with system context diagram, detailed **sequence diagram** for the batch pipeline, and alignment with implemented table names (`enrichment_runs`, `enrichment_records`).
- Polished **`docs/problem-definition.md`** and cross-linked **`docs/runbook.md`**.
- Added **`docs/runbook.md`** (health checks, failures, retries, extending fields, scoring, evaluation).
- Updated **ADR 004** and **ADR 005** with **implementation notes** reflecting the current codebase.
- Introduced this **`CHANGELOG.md`**.

## [0.1.0] — 2026-04-10

### Added

- FastAPI service with enrichment batch API, health/ready/metrics routes.
- Pipeline: website discovery, multi-page scraping, OpenAI enrichment, quality scoring, PostgreSQL/SQLite persistence.
- Alembic migration for enrichment tables; async SQLAlchemy repositories.
- Test suite (unit + integration) with mocked external services.
- Offline evaluation workflow (`eval/`, `make evaluate`) and sample data under `data/sample_run/`.
