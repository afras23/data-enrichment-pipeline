"""End-to-end pipeline tests with mocked HTTP and AI."""

from __future__ import annotations

import pytest

import app.db.session as session_module
from app.repositories.enrichment_repository import EnrichmentRepository
from app.services.alerting import AlertEvaluationService, MockCompositeNotifier
from app.services.enrichment_pipeline import EnrichmentPipelineService
from app.services.site_scraper import SiteScraperService
from app.services.website_discovery import WebsiteDiscoveryService


@pytest.mark.asyncio
async def test_pipeline_processes_company_with_mocks(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_web_fetch: object,
    mock_openai_enrichment: object,
) -> None:
    """Full flow persists a completed record when discovery, scrape, and AI succeed."""

    notifier = MockCompositeNotifier()
    alerts = AlertEvaluationService(
        notifier,
        failure_streak_threshold=50,
        avg_quality_threshold=0.01,
    )
    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=mock_web_fetch),
        scraper=SiteScraperService(web_client=mock_web_fetch),
        ai_client=mock_openai_enrichment,
        alerts=alerts,
    )

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=1, correlation_id="test-cid")
        await session.commit()
        run_id = run.id

    await pipeline.process_run(run_id, ["TestCo"])

    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        updated = await repo.get_run(run_id)
        assert updated is not None
        assert updated.succeeded_count >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("names", [["A"], ["Foo", "Bar"]])
async def test_pipeline_parameterized_companies(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_web_fetch: object,
    mock_openai_enrichment: object,
    names: list[str],
) -> None:
    """Pipeline handles single and multi-company batches without crashing."""

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


@pytest.mark.asyncio
async def test_pipeline_failure_when_no_website(
    sqlite_engine: object,
    patch_session_factory: object,
    mock_openai_enrichment: object,
) -> None:
    """Discovery failure marks partial/failed without calling AI."""

    from unittest.mock import AsyncMock, MagicMock

    from app.integrations.web_client import WebFetchResult

    failing = MagicMock()

    async def _fail(_url: str) -> WebFetchResult:
        raise OSError("network")

    failing.fetch = AsyncMock(side_effect=_fail)

    pipeline = EnrichmentPipelineService(
        session_module.async_session_factory,
        discovery=WebsiteDiscoveryService(web_client=failing),
        scraper=SiteScraperService(web_client=failing),
        ai_client=mock_openai_enrichment,
        alerts=None,
    )
    async with session_module.async_session_factory() as session:
        repo = EnrichmentRepository(session)
        run = await repo.create_run(total_companies=1, correlation_id=None)
        await session.commit()
        rid = run.id

    await pipeline.process_run(rid, ["ZZZUnknownBrandZZZ"])

    mock_openai_enrichment.enrich_company.assert_not_called()
