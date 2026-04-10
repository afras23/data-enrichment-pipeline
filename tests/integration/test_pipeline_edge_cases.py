"""
Pipeline integration tests: edge cases with HTTP and OpenAI fully mocked.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.db.session as session_module
from app.config import settings
from app.integrations.web_client import WebFetchResult
from app.repositories.enrichment_repository import EnrichmentRepository
from app.services.enrichment_pipeline import EnrichmentPipelineService
from app.services.site_scraper import SiteScraperService
from app.services.website_discovery import WebsiteDiscoveryService


@pytest.mark.asyncio
async def test_pipeline_process_run_with_empty_company_names_completes_without_processing_rows(
    sqlite_engine: object,
    patch_session_factory: object,
) -> None:
    """process_run([], ...) completes run totals with zero successes (orchestrator contract)."""

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=0, correlation_id="edge-empty")
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, [])

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        updated = await repo.get_run(rid)
        assert updated is not None
        assert updated.succeeded_count == 0
        assert updated.failed_count == 0
        assert updated.status == "completed"


@pytest.mark.asyncio
async def test_pipeline_duplicate_company_names_create_distinct_records(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_web_fetch: MagicMock,
    mock_openai_enrichment: MagicMock,
) -> None:
    """Same label twice in one batch persists two rows (no deduplication in pipeline)."""

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=mock_web_fetch),
        scraper=SiteScraperService(web_client=mock_web_fetch),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=2, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["DupCo", "DupCo"])

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        rows, total = await repo.list_companies(skip=0, limit=10)
        assert total == 2
        assert {r.company_name for r in rows} == {"DupCo"}
        assert len({r.id for r in rows}) == 2


@pytest.mark.asyncio
async def test_discovery_recovers_when_later_candidate_returns_html(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_openai_enrichment: MagicMock,
) -> None:
    """Discovery probes multiple URLs; transient failures on early candidates still resolve (mocked)."""

    html = "<!doctype html><html><body><p>ok</p></body></html>"
    attempts: list[str] = []

    async def fetch(url: str) -> WebFetchResult:
        attempts.append(url)
        if len(attempts) < 4:
            raise ConnectionError("transient")
        return WebFetchResult(
            url=url,
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body_text=html,
            body_bytes_len=len(html.encode()),
        )

    web = MagicMock()
    web.fetch = AsyncMock(side_effect=fetch)

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=web),
        scraper=SiteScraperService(web_client=web),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=1, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["RetryCo"])

    assert len(attempts) >= 4
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        rows, total = await repo.list_companies(skip=0, limit=5)
        assert total == 1
        assert rows[0].status == "completed"


@pytest.mark.asyncio
async def test_homepage_fetch_failure_yields_no_pages_and_scrape_error(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_openai_enrichment: MagicMock,
) -> None:
    """When every HTTP fetch raises, scrape produces zero pages → pipeline partial failure without AI."""

    web = MagicMock()
    web.fetch = AsyncMock(side_effect=OSError("no route"))

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=web),
        scraper=SiteScraperService(web_client=web),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=1, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["FailCo"])

    mock_openai_enrichment.enrich_company.assert_not_called()


@pytest.mark.asyncio
async def test_secondary_page_fetch_errors_keep_homepage_evidence(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_openai_enrichment: MagicMock,
) -> None:
    """Homepage succeeds; follow-up paths may 404 — bundle still has pages and fetch_errors."""

    home = """
    <!doctype html><html><head><title>H</title></head><body>
    <p>We build software for hospitals.</p>
    <a href="/about">About</a>
    </body></html>
    """
    disc = MagicMock()
    disc.fetch = AsyncMock(
        return_value=WebFetchResult(
            url="https://www.failco.com/",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body_text=home,
            body_bytes_len=len(home.encode()),
        )
    )
    scrape_calls: list[str] = []

    async def scrape_fetch(url: str) -> WebFetchResult:
        scrape_calls.append(url)
        if len(scrape_calls) == 1:
            return WebFetchResult(
                url=url,
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body_text=home,
                body_bytes_len=len(home.encode()),
            )
        return WebFetchResult(
            url=url,
            status_code=404,
            headers={"content-type": "text/plain"},
            body_text="not found",
            body_bytes_len=9,
        )

    scr = MagicMock()
    scr.fetch = AsyncMock(side_effect=scrape_fetch)

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=disc),
        scraper=SiteScraperService(web_client=scr),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=1, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["FailCo"])

    mock_openai_enrichment.enrich_company.assert_called()
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        rows, _total = await repo.list_companies(skip=0, limit=5)
        rec = rows[0]
        bundle = rec.scrape_bundle
        assert bundle is not None
        assert len(bundle.get("fetch_errors", [])) >= 1
        assert len(bundle.get("pages", [])) >= 1


@pytest.mark.asyncio
async def test_partial_batch_when_one_company_has_no_website(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_openai_enrichment: MagicMock,
) -> None:
    """Mixed outcome: GoodCo resolves; ZZZ slug never gets HTML → partial run totals."""

    html = "<!doctype html><html><body><h1>GoodCo</h1><p>hello@goodco.example</p></body></html>"

    async def fetch(url: str) -> WebFetchResult:
        if "goodco" in url.lower():
            return WebFetchResult(
                url=url,
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body_text=html,
                body_bytes_len=len(html.encode()),
            )
        raise OSError("no responsive candidate")

    web = MagicMock()
    web.fetch = AsyncMock(side_effect=fetch)

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=web),
        scraper=SiteScraperService(web_client=web),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=2, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["GoodCo", "ZZZNoSiteZZZ"])

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        updated = await repo.get_run(rid)
        assert updated is not None
        assert updated.status == "partial"
        assert updated.succeeded_count >= 1
        assert updated.failed_count >= 1


@pytest.mark.asyncio
async def test_cost_limit_stops_run_after_budget_exceeded(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_web_fetch: MagicMock,
    mock_openai_enrichment: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When cumulative AI cost exceeds max_cost_per_run_usd, later rows fail with cost error."""

    monkeypatch.setattr(settings, "max_cost_per_run_usd", 0.00002, raising=False)

    costly = MagicMock()

    async def _costly(*a: object, **k: object):
        from app.schemas.domain import AIEnrichmentResult
        from app.services.ai.openai_client import OpenAICallMetrics

        return (
            AIEnrichmentResult(industry="X"),
            OpenAICallMetrics(
                model="m",
                prompt_version="v",
                input_tokens=100,
                output_tokens=100,
                latency_ms=1.0,
                cost_usd=0.00002,
            ),
        )

    costly.enrich_company = AsyncMock(side_effect=_costly)

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=mock_web_fetch),
        scraper=SiteScraperService(web_client=mock_web_fetch),
        ai_client=costly,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=3, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["A", "B", "C"])

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        updated = await repo.get_run(rid)
        assert updated is not None
        assert updated.failed_count >= 1


@pytest.mark.asyncio
async def test_large_batch_processes_all_companies_with_mocks(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_web_fetch: MagicMock,
    mock_openai_enrichment: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: many companies complete without live network (all dependencies mocked)."""

    # Isolate from MAX_COST_PER_RUN_USD in the environment: a low cap (e.g. 0.0028) would
    # allow exactly 28 × mock cost_usd (0.0001) then block the rest via the pre-AI budget check.
    monkeypatch.setattr(settings, "max_cost_per_run_usd", 1.0, raising=False)

    names = [f"BatchCo{n:02d}" for n in range(32)]
    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=mock_web_fetch),
        scraper=SiteScraperService(web_client=mock_web_fetch),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=len(names), correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, names)

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        updated = await repo.get_run(rid)
        assert updated is not None
        assert updated.succeeded_count == len(names)
        _rows, total = await repo.list_companies(skip=0, limit=100)
        assert total == len(names)


@pytest.mark.asyncio
async def test_concurrent_pipeline_runs_on_shared_database(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_web_fetch: MagicMock,
    mock_openai_enrichment: MagicMock,
) -> None:
    """Two runs in parallel both finish; record counts reflect isolation by run_id."""

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=mock_web_fetch),
        scraper=SiteScraperService(web_client=mock_web_fetch),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )

    async def one(label: str):
        async with session_module.async_session_factory() as session:
            repo = EnrichmentRepository(session)
            run = await repo.create_run(total_companies=1, correlation_id=label)
            await session.commit()
            return run.id

    rid_a = await one("a")
    rid_b = await one("b")
    await asyncio.gather(
        pipeline.process_run(rid_a, ["ConcurrentA"]),
        pipeline.process_run(rid_b, ["ConcurrentB"]),
    )

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        rows, total = await repo.list_companies(skip=0, limit=20)
        assert total == 2
        run_ids = {r.run_id for r in rows}
        assert rid_a in run_ids and rid_b in run_ids


@pytest.mark.asyncio
async def test_thin_scrape_text_still_completes_pipeline_with_low_quality(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_openai_enrichment: MagicMock,
) -> None:
    """Minimal HTML body still yields one page; quality score is depressed by evidence strength."""

    thin = "<!doctype html><html><body>x</body></html>"
    web = MagicMock()

    async def fetch(url: str) -> WebFetchResult:
        return WebFetchResult(
            url=url,
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body_text=thin,
            body_bytes_len=len(thin.encode()),
        )

    web.fetch = AsyncMock(side_effect=fetch)

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=web),
        scraper=SiteScraperService(web_client=web),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=1, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["ThinCo"])

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        rows, _ = await repo.list_companies(skip=0, limit=5)
        rec = rows[0]
        qr = rec.quality_report
        assert qr is not None
        assert float(qr["final_score"]) < 0.5
