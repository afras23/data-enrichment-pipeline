"""
Batch enrichment orchestrator: discovery → scrape → AI → quality → persistence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from statistics import mean
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.correlation import get_correlation_id
from app.core.exceptions import CostLimitExceeded, EnrichmentAIError, ScrapeError
from app.models.enrichment import EnrichmentRecord, EnrichmentRecordStatus, EnrichmentRunStatus
from app.repositories.enrichment_repository import EnrichmentRepository
from app.schemas.domain import ScrapedSiteBundle
from app.services.ai.openai_client import OpenAIEnrichmentClient
from app.services.alerting import AlertEvaluationService
from app.services.quality_scoring import QualityScoringService
from app.services.site_scraper import SiteScraperService
from app.services.website_discovery import WebsiteDiscoveryService, normalize_company_key

logger = logging.getLogger(__name__)


def _deterministic_hint_bundle(bundle: ScrapedSiteBundle) -> dict[str, object]:
    first = bundle.pages[0] if bundle.pages else None
    ld_types: list[str] = []
    for block in first.json_ld_blocks if first else []:
        t = block.get("@type")
        if isinstance(t, str):
            ld_types.append(t)
        elif isinstance(t, list):
            ld_types.extend(str(x) for x in t if isinstance(x, str))
    return {
        "page_titles": [p.title for p in bundle.pages if p.title],
        "emails": first.emails if first else [],
        "phones": first.phone_numbers if first else [],
        "social_links": first.social_links if first else [],
        "technology_hints": sorted({h for p in bundle.pages for h in p.technology_hints}),
        "json_ld_types": ld_types[:20],
    }


class EnrichmentPipelineService:
    """Coordinates end-to-end processing for all companies in a run."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        discovery: WebsiteDiscoveryService | None = None,
        scraper: SiteScraperService | None = None,
        ai_client: OpenAIEnrichmentClient | None = None,
        quality: QualityScoringService | None = None,
        alerts: AlertEvaluationService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._discovery = discovery or WebsiteDiscoveryService()
        self._scraper = scraper or SiteScraperService()
        self._ai = ai_client or OpenAIEnrichmentClient()
        self._quality = quality or QualityScoringService()
        self._alerts = alerts

    async def process_run(self, run_id: UUID, company_names: list[str]) -> None:
        """
        Execute the pipeline for each company and finalize run aggregates.

        Intended for background execution after a run row is created.
        """

        async with self._session_factory() as session:
            repo = EnrichmentRepository(session)
            run_row = await repo.get_run(run_id)
            if run_row:
                run_row.status = EnrichmentRunStatus.RUNNING.value
                run_row.started_at = datetime.now(UTC)
                await session.commit()

        sem = asyncio.Semaphore(settings.pipeline_max_concurrency)
        counter_lock = asyncio.Lock()
        run_cost = 0.0
        succeeded = 0
        failed = 0
        qualities: list[float] = []

        async def one(name: str) -> None:
            nonlocal run_cost, succeeded, failed

            async with sem:
                async with self._session_factory() as session:
                    repo = EnrichmentRepository(session)
                    record = EnrichmentRecord(
                        run_id=run_id,
                        company_name=name,
                        normalized_name_key=normalize_company_key(name),
                        status=EnrichmentRecordStatus.PENDING.value,
                    )
                    await repo.add_record(record)
                    await session.commit()
                    record_id = record.id

                async with self._session_factory() as session:
                    repo = EnrichmentRepository(session)
                    rec = await repo.get_company(record_id)
                    if not rec:
                        return

                    try:
                        disc = await self._discovery.discover(name)
                        rec.website_url = disc.website_url
                        rec.website_confidence = disc.confidence
                        rec.discovery_metadata = {
                            "notes": disc.notes,
                            "candidates_tried": disc.candidates_tried,
                        }

                        if not disc.website_url:
                            raise ScrapeError("Website could not be resolved")

                        bundle = await self._scraper.scrape_site(disc.website_url)
                        rec.scrape_bundle = bundle.model_dump(mode="json")

                        if not bundle.pages:
                            raise ScrapeError("No HTML pages could be fetched")

                        async with counter_lock:
                            if run_cost >= settings.max_cost_per_run_usd:
                                raise CostLimitExceeded(run_cost, settings.max_cost_per_run_usd)

                        hint = _deterministic_hint_bundle(bundle)
                        ai, metrics = await self._ai.enrich_company(
                            name,
                            bundle.combined_visible_text,
                            hint,
                        )

                        async with counter_lock:
                            run_cost += metrics.cost_usd
                            if run_cost > settings.max_cost_per_run_usd:
                                raise CostLimitExceeded(run_cost, settings.max_cost_per_run_usd)

                        rec.ai_payload = ai.model_dump(mode="json")
                        rec.prompt_version = metrics.prompt_version
                        rec.model = metrics.model
                        rec.input_tokens = metrics.input_tokens
                        rec.output_tokens = metrics.output_tokens
                        rec.ai_cost_usd = metrics.cost_usd
                        rec.ai_latency_ms = metrics.latency_ms

                        report = self._quality.build_report(
                            website_confidence=disc.confidence,
                            scrape=bundle,
                            ai=ai,
                        )
                        rec.quality_report = report.model_dump(mode="json")
                        rec.status = EnrichmentRecordStatus.COMPLETED.value
                        async with counter_lock:
                            qualities.append(report.final_score)
                            succeeded += 1

                    except CostLimitExceeded as exc:
                        rec.status = EnrichmentRecordStatus.FAILED.value
                        rec.error_code = exc.error_code
                        rec.error_message = exc.message
                        async with counter_lock:
                            failed += 1
                    except (ScrapeError, EnrichmentAIError) as exc:
                        rec.status = EnrichmentRecordStatus.PARTIAL.value
                        rec.error_code = exc.error_code
                        rec.error_message = exc.message
                        async with counter_lock:
                            failed += 1
                    except Exception as exc:
                        logger.exception(
                            "Unexpected pipeline error",
                            extra={
                                "correlation_id": get_correlation_id(),
                                "company": name[:120],
                            },
                        )
                        rec.status = EnrichmentRecordStatus.FAILED.value
                        rec.error_code = "UNEXPECTED"
                        rec.error_message = str(exc)[:2000]
                        async with counter_lock:
                            failed += 1

                    rec.updated_at = datetime.now(UTC)
                    await session.commit()

        await asyncio.gather(*(one(n) for n in company_names))

        avg_q = mean(qualities) if qualities else None
        async with self._session_factory() as session:
            repo = EnrichmentRepository(session)
            status = EnrichmentRunStatus.COMPLETED
            if failed == len(company_names) and company_names:
                status = EnrichmentRunStatus.FAILED
            elif failed > 0:
                status = EnrichmentRunStatus.PARTIAL

            await repo.update_run_totals(
                run_id,
                status=status,
                succeeded=succeeded,
                failed=failed,
                total_cost=run_cost,
                error_message=None,
            )
            await session.commit()

        if self._alerts:
            await self._alerts.maybe_alert_on_run_outcome(
                run_id=str(run_id),
                failed_count=failed,
                total_count=len(company_names),
                avg_quality=avg_q,
            )

        logger.info(
            "Enrichment run completed",
            extra={
                "correlation_id": get_correlation_id(),
                "run_id": str(run_id),
                "succeeded": succeeded,
                "failed": failed,
                "total_cost_usd": round(run_cost, 6),
            },
        )
