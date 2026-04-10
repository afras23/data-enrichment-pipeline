"""
Offline evaluation: run the production pipeline against sample YAML with mocked HTTP/AI.

Produces a Markdown report under eval/reports/ focused on extraction completeness,
quality scores, and per-record outcomes. No external network or live OpenAI calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.db.session as session_module
from app.db.base import Base
from app.integrations.web_client import WebFetchResult
from app.models.enrichment import EnrichmentRecord, EnrichmentRun
from app.repositories.enrichment_repository import EnrichmentRepository
from app.schemas.domain import AIEnrichmentResult
from app.services.ai.openai_client import OpenAICallMetrics
from app.services.enrichment_pipeline import EnrichmentPipelineService
from app.services.site_scraper import SiteScraperService
from app.services.website_discovery import WebsiteDiscoveryService

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPANIES = PROJECT_ROOT / "data" / "sample_run" / "companies.yaml"
DEFAULT_EXPECTED = PROJECT_ROOT / "data" / "sample_run" / "expected_enrichment.yaml"
DEFAULT_REPORT = PROJECT_ROOT / "eval" / "reports" / "evaluation_report.md"
DEFAULT_JSON = PROJECT_ROOT / "eval" / "reports" / "evaluation_summary.json"
DEFAULT_SQLITE = PROJECT_ROOT / "eval" / "reports" / ".evaluation.sqlite"

HTML_RICH = """
<!doctype html>
<html><head>
<title>Eval Full Co — Home</title>
<meta name="description" content="We build data enrichment tools for revenue teams." />
<script src="https://www.googletagmanager.com/gtag/js?id=G-EVAL"></script>
</head><body>
<h1>Eval Full Co</h1>
<p>We are a software company. Contact sales@evalfullco.example or +1 415-555-0199.</p>
<a href="/contact">Contact</a>
<a href="https://www.linkedin.com/company/evalfullco">LinkedIn</a>
<script type="application/ld+json">
{"@type":"Organization","name":"Eval Full Co","email":"sales@evalfullco.example"}
</script>
</body></html>
"""

HTML_THIN = """
<!doctype html>
<html><head><title>Eval Thin Co</title></head><body><p>Hello.</p></body></html>
"""


def _repo_path() -> Path:
    return PROJECT_ROOT


def _load_yaml(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        msg = f"Expected mapping at root in {path}"
        raise ValueError(msg)
    return data


def _mock_web_fetch(companies_cfg: Sequence[Mapping[str, object]]) -> MagicMock:
    """Route fetch behavior by discovered hostname (aligned with sample company slugs)."""

    names = [str(c.get("name", "")) for c in companies_cfg]

    async def _fetch(url: str) -> WebFetchResult:
        host = (urlparse(url).hostname or "").lower()
        if "evalnositezzz" in host:
            raise OSError("simulated discovery failure (no responsive host)")
        body = HTML_THIN if "evalthinco" in host else HTML_RICH
        return WebFetchResult(
            url=url,
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body_text=body,
            body_bytes_len=len(body.encode()),
        )

    client = MagicMock()
    client.fetch = AsyncMock(side_effect=_fetch)
    if names:
        logger.info("Mock web fetch configured for companies: %s", names)
    return client


def _mock_openai(companies_cfg: Sequence[Mapping[str, object]]) -> MagicMock:
    """Return structured AI payloads keyed by company name prefix/scenario."""

    async def _enrich(
        company_name: str,
        _text: str,
        _hint: dict[str, object],
    ) -> tuple[AIEnrichmentResult, OpenAICallMetrics]:
        metrics = OpenAICallMetrics(
            model="gpt-4o-mini",
            prompt_version="company_enrichment_v1",
            input_tokens=100,
            output_tokens=60,
            latency_ms=40.0,
            cost_usd=0.00008,
        )
        if "Thin" in company_name:
            result = AIEnrichmentResult(
                industry="Software",
                company_description="Minimal visible content.",
                company_size_band="1-10",
                tech_stack=["python"],
                contacts_or_signals=[],
                confidence_notes="thin page fixture",
                evidence_summary="homepage only",
            )
            return result, metrics
        result = AIEnrichmentResult(
            industry="Software",
            company_description="Eval Full Co provides batch enrichment for sales teams.",
            company_size_band="51-200",
            tech_stack=["python", "postgresql", "react"],
            contacts_or_signals=["sales@evalfullco.example"],
            confidence_notes="eval fixture",
            evidence_summary="homepage and structured data",
        )
        return result, metrics

    mock = MagicMock()
    mock.enrich_company = AsyncMock(side_effect=_enrich)
    return mock


async def _records_for_run(session: AsyncSession, run_id: UUID) -> list[EnrichmentRecord]:
    stmt = (
        select(EnrichmentRecord)
        .where(EnrichmentRecord.run_id == run_id)
        .order_by(EnrichmentRecord.company_name)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


def _check_expectation(
    exp: Mapping[str, object],
    rec: EnrichmentRecord,
) -> tuple[bool, list[str]]:
    ok = True
    messages: list[str] = []
    name = str(exp.get("company_name", ""))
    if rec.company_name != name:
        return False, [f"name mismatch (expected {name}, got {rec.company_name})"]

    want_status = str(exp.get("record_status", "")).lower()
    if want_status and rec.status.lower() != want_status:
        ok = False
        messages.append(f"status: want {want_status}, got {rec.status}")

    qr = rec.quality_report or {}
    final = qr.get("final_score")
    sub = qr.get("subscores") or {}
    completeness = sub.get("completeness")

    if (
        "min_final_score" in exp
        and exp["min_final_score"] is not None
        and isinstance(final, int | float)
    ):
        min_f = float(cast(int | float, exp["min_final_score"]))
        if float(final) < min_f:
            ok = False
            messages.append(f"final_score {final} < min {min_f}")

    if (
        "max_final_score" in exp
        and exp["max_final_score"] is not None
        and isinstance(final, int | float)
    ):
        max_f = float(cast(int | float, exp["max_final_score"]))
        if float(final) > max_f:
            ok = False
            messages.append(f"final_score {final} > max {max_f}")

    if (
        "min_completeness" in exp
        and exp["min_completeness"] is not None
        and isinstance(completeness, int | float)
    ):
        min_c = float(cast(int | float, exp["min_completeness"]))
        if float(completeness) < min_c:
            ok = False
            messages.append(f"completeness {completeness} < min {min_c}")

    ai = rec.ai_payload or {}
    industry = ai.get("industry")
    want_industry = exp.get("ai_industry_not_null")
    if want_industry is True and not industry:
        ok = False
        messages.append("expected industry in AI payload")
    if want_industry is False and industry:
        ok = False
        messages.append("expected no AI industry for this scenario")

    return ok, messages


async def run_evaluation(
    *,
    companies_path: Path,
    expected_path: Path,
    report_path: Path,
    json_path: Path,
    sqlite_path: Path,
) -> int:
    companies_doc = _load_yaml(companies_path)
    raw_list = companies_doc.get("companies")
    if not isinstance(raw_list, list):
        raise ValueError("companies.yaml must contain a 'companies' list")
    companies_cfg: list[Mapping[str, object]] = [c for c in raw_list if isinstance(c, dict)]
    names = [str(c["name"]) for c in companies_cfg if "name" in c]

    expected_doc = _load_yaml(expected_path)
    raw_exp = expected_doc.get("expectations")
    expectations: list[Mapping[str, object]] = (
        [e for e in raw_exp if isinstance(e, dict)] if isinstance(raw_exp, list) else []
    )

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()

    url = f"sqlite+aiosqlite:///{sqlite_path}"
    engine = create_async_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    session_module.async_session_factory = factory
    session_module.engine = engine

    web = _mock_web_fetch(companies_cfg)
    openai_mock = _mock_openai(companies_cfg)

    pipeline = EnrichmentPipelineService(
        factory,
        discovery=WebsiteDiscoveryService(web_client=web),
        scraper=SiteScraperService(web_client=web),
        ai_client=openai_mock,
        alerts=None,
    )

    run_cfg = companies_doc.get("run")
    cid = None
    if isinstance(run_cfg, dict) and run_cfg.get("correlation_id"):
        cid = str(run_cfg["correlation_id"])

    async with factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=len(names), correlation_id=cid)
        await session.commit()
        run_id = run.id

    await pipeline.process_run(run_id, names)

    async with factory() as session:
        run_row = await session.get(EnrichmentRun, run_id)
        records = await _records_for_run(session, run_id)

    report_lines: list[str] = [
        "# Enrichment pipeline evaluation (offline)",
        "",
        f"- **Companies file**: `{companies_path.relative_to(_repo_path())}`",
        f"- **Expectations file**: `{expected_path.relative_to(_repo_path())}`",
        f"- **SQLite (ephemeral)**: `{sqlite_path.name}`",
        "",
        "## Run outcome",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]

    if run_row:
        avg_q = None
        qualities: list[float] = []
        for r in records:
            qr = r.quality_report or {}
            fs = qr.get("final_score")
            if isinstance(fs, int | float) and r.status == "completed":
                qualities.append(float(fs))
        if qualities:
            avg_q = sum(qualities) / len(qualities)
        report_lines.extend(
            [
                f"| Run status | `{run_row.status}` |",
                f"| Total companies | {run_row.total_companies} |",
                f"| Succeeded | {run_row.succeeded_count} |",
                f"| Failed | {run_row.failed_count} |",
                f"| Total AI cost (USD) | {run_row.total_ai_cost_usd:.6f} |",
                f"| Avg quality (completed only) | {avg_q if avg_q is not None else 'n/a'} |",
                "",
            ]
        )

    report_lines.extend(
        [
            "## Per-company results",
            "",
            "| Company | Status | Final score | Completeness | Evidence | Consistency | Industry |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    summary_rows: list[dict[str, object]] = []

    for r in records:
        qr = r.quality_report or {}
        sub = qr.get("subscores") or {}
        ai_payload = r.ai_payload or {}
        final = qr.get("final_score")
        ind = ai_payload.get("industry")
        report_lines.append(
            f"| {r.company_name} | `{r.status}` | {final} | "
            f"{sub.get('completeness')} | {sub.get('evidence_strength')} | "
            f"{sub.get('consistency')} | {ind or ''} |"
        )
        summary_rows.append(
            {
                "company_name": r.company_name,
                "status": r.status,
                "final_score": final,
                "completeness": sub.get("completeness"),
                "evidence_strength": sub.get("evidence_strength"),
                "consistency": sub.get("consistency"),
                "industry": ind,
                "error_code": r.error_code,
            }
        )

    report_lines.extend(["", "## Expectation checks", ""])

    exp_by_name = {str(e.get("company_name")): e for e in expectations}
    all_pass = True
    for r in records:
        exp = exp_by_name.get(r.company_name)
        if not exp:
            report_lines.append(f"- **{r.company_name}**: _(no expected row)_")
            continue
        ok, msgs = _check_expectation(exp, r)
        all_pass = all_pass and ok
        status = "PASS" if ok else "FAIL"
        detail = "; ".join(msgs) if msgs else "ok"
        report_lines.append(f"- **{r.company_name}**: {status} — {detail}")

    report_lines.extend(["", "---", "", "_Generated by `make evaluate` (mocked HTTP + AI)._", ""])

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    payload = {
        "run_id": str(run_id),
        "run_status": run_row.status if run_row else None,
        "succeeded": run_row.succeeded_count if run_row else None,
        "failed": run_row.failed_count if run_row else None,
        "total_cost_usd": run_row.total_ai_cost_usd if run_row else None,
        "companies": summary_rows,
        "expectations_all_passed": all_pass,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    await engine.dispose()

    return 0 if all_pass else 1


async def main() -> None:
    parser = argparse.ArgumentParser(description="Offline enrichment evaluation (mocked I/O).")
    parser.add_argument(
        "--companies",
        type=Path,
        default=DEFAULT_COMPANIES,
        help="YAML batch definition (default: data/sample_run/companies.yaml)",
    )
    parser.add_argument(
        "--expected",
        type=Path,
        default=DEFAULT_EXPECTED,
        help="YAML soft expectations (default: data/sample_run/expected_enrichment.yaml)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Output Markdown report path",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=DEFAULT_JSON,
        dest="json_out",
        help="Output JSON summary path",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=DEFAULT_SQLITE,
        help="Ephemeral SQLite file for this run",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    code = await run_evaluation(
        companies_path=args.companies.resolve(),
        expected_path=args.expected.resolve(),
        report_path=args.report.resolve(),
        json_path=args.json_out.resolve(),
        sqlite_path=args.sqlite.resolve(),
    )
    raise SystemExit(code)


if __name__ == "__main__":
    asyncio.run(main())
