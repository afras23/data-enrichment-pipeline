"""Quality scoring unit tests."""

from __future__ import annotations

import pytest

from app.schemas.domain import AIEnrichmentResult, PageSignals, ScrapedSiteBundle
from app.services.quality_scoring import QualityScoringService


def _bundle() -> ScrapedSiteBundle:
    page = PageSignals(
        url="https://co.example/",
        title="Co",
        meta_description="desc",
        headings=["H"],
        visible_text_sample="software company building tools" * 50,
    )
    return ScrapedSiteBundle(
        base_url="https://co.example",
        pages=[page],
        combined_visible_text=page.visible_text_sample,
        total_bytes_fetched=5000,
    )


def test_quality_report_increases_with_full_ai_payload() -> None:
    """More populated AI fields raise completeness subscore."""

    svc = QualityScoringService()
    ai = AIEnrichmentResult(
        industry="Software",
        company_description="We build tools.",
        company_size_band="51-200",
        tech_stack=["python"],
        contacts_or_signals=["sales@co.example"],
        evidence_summary="about page",
        confidence_notes="ok",
    )
    report = svc.build_report(website_confidence=0.9, scrape=_bundle(), ai=ai)
    assert report.final_score >= 0.4
    assert report.subscores.website_confidence == pytest.approx(0.9)


def test_quality_penalizes_fetch_errors() -> None:
    """Fetch errors reduce evidence strength."""

    svc = QualityScoringService()
    b = _bundle()
    b.fetch_errors.append("https://co.example/contact: timeout")
    ai = AIEnrichmentResult(industry="Software")
    report = svc.build_report(website_confidence=0.5, scrape=b, ai=ai)
    assert any("fetch" in n.lower() for n in report.notes)
