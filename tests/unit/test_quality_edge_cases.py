"""
Edge-case and boundary tests for QualityScoringService (deterministic logic only).
"""

from __future__ import annotations

import pytest

from app.schemas.domain import AIEnrichmentResult, PageSignals, ScrapedSiteBundle
from app.services.quality_scoring import QualityScoringService


def _page(url: str, text: str, title: str | None = None) -> PageSignals:
    return PageSignals(
        url=url,
        title=title,
        visible_text_sample=text,
    )


@pytest.mark.parametrize(
    ("wc", "expected_wc_sub"),
    [
        (0.0, 0.0),
        (1.0, 1.0),
        (-0.5, 0.0),
        (1.5, 1.0),
    ],
)
def test_quality_report_clamps_website_confidence_to_unit_interval(
    wc: float,
    expected_wc_sub: float,
) -> None:
    """website_confidence is clamped into [0, 1] for subscores."""

    svc = QualityScoringService()
    scrape = ScrapedSiteBundle(
        base_url="https://x.example",
        pages=[_page("https://x.example/", "x" * 4000)],
        combined_visible_text="x" * 4000,
    )
    ai = AIEnrichmentResult(industry="Software", company_description="d", company_size_band="11-50")
    report = svc.build_report(website_confidence=wc, scrape=scrape, ai=ai)
    assert report.subscores.website_confidence == pytest.approx(expected_wc_sub)


def test_quality_final_score_is_within_zero_one_inclusive() -> None:
    """Composite score stays in [0, 1] for arbitrary sparse AI payloads."""

    svc = QualityScoringService()
    scrape = ScrapedSiteBundle(
        base_url="https://x.example",
        pages=[_page("https://x.example/", "a")],
        combined_visible_text="a",
    )
    ai = AIEnrichmentResult()
    report = svc.build_report(website_confidence=0.4, scrape=scrape, ai=ai)
    assert 0.0 <= report.final_score <= 1.0


def test_quality_penalizes_contradictory_industry_vs_scrape_text() -> None:
    """When industry tokens do not appear in scrape text, consistency stays low."""

    svc = QualityScoringService()
    scrape = ScrapedSiteBundle(
        base_url="https://co.example",
        pages=[
            _page("https://co.example/", "We sell artisanal bread and pastries only.", "BakeryCo"),
            _page("https://co.example/tech", "Legacy ERP consulting for banks.", "Services"),
        ],
        combined_visible_text="bread pastry bank erp",
    )
    ai = AIEnrichmentResult(
        industry="Quantum Cryptography Hardware",
        company_description="We make qubits.",
        tech_stack=["react"],
    )
    report = svc.build_report(website_confidence=0.8, scrape=scrape, ai=ai)
    assert report.subscores.consistency < 0.6
    assert report.final_score < 0.75


def test_quality_high_when_industry_string_appears_verbatim_in_scrape() -> None:
    """Production boosts consistency when industry substring matches combined text."""

    svc = QualityScoringService()
    text = "Contoso is a leading enterprise software vendor for global teams."
    scrape = ScrapedSiteBundle(
        base_url="https://contoso.example",
        pages=[_page("https://contoso.example/", text)],
        combined_visible_text=text,
    )
    ai = AIEnrichmentResult(
        industry="enterprise software",
        company_description="Vendors",
        company_size_band="501-1000",
        tech_stack=["azure"],
        contacts_or_signals=["sales@contoso.example"],
        evidence_summary="home",
        confidence_notes="ok",
    )
    report = svc.build_report(website_confidence=0.9, scrape=scrape, ai=ai)
    assert report.subscores.consistency >= 0.25
    assert report.final_score >= 0.35


def test_sparse_scrape_and_sparse_ai_yield_low_evidence_and_completeness() -> None:
    """Nearly empty pages and null AI fields produce low subscores (low-confidence path)."""

    svc = QualityScoringService()
    scrape = ScrapedSiteBundle(
        base_url="https://minimal.example",
        pages=[_page("https://minimal.example/", "ok")],
        combined_visible_text="ok",
    )
    ai = AIEnrichmentResult()
    report = svc.build_report(website_confidence=0.1, scrape=scrape, ai=ai)
    assert report.subscores.evidence_strength < 0.1
    assert report.subscores.completeness == 0.0
    assert report.final_score < 0.35
