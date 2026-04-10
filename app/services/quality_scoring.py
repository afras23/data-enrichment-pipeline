"""
Composite data quality scoring from scrape evidence and AI output.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from app.schemas.domain import (
    AIEnrichmentResult,
    QualityReport,
    QualitySubscores,
    ScrapedSiteBundle,
)

logger = logging.getLogger(__name__)


def _overlap_score(text: str, tokens: Iterable[str]) -> float:
    t = text.lower()
    hits = sum(1 for tok in tokens if tok and tok.lower() in t)
    return min(1.0, hits / 3.0) if tokens else 0.0


class QualityScoringService:
    """Compute completeness, evidence, consistency, and final quality scores."""

    def build_report(
        self,
        *,
        website_confidence: float,
        scrape: ScrapedSiteBundle,
        ai: AIEnrichmentResult,
    ) -> QualityReport:
        """
        Produce a QualityReport with subscores and explanatory notes.

        website_confidence is expected in [0, 1] from discovery.
        """

        notes: list[str] = []

        filled = 0
        total = 6
        if ai.industry:
            filled += 1
        if ai.company_description:
            filled += 1
        if ai.company_size_band:
            filled += 1
        if ai.tech_stack:
            filled += 1
        if ai.contacts_or_signals:
            filled += 1
        if ai.evidence_summary or ai.confidence_notes:
            filled += 1
        completeness = filled / total

        text_blob = (
            scrape.combined_visible_text + "\n" + " ".join(p.title or "" for p in scrape.pages)
        ).lower()
        evidence_strength = min(1.0, len(scrape.combined_visible_text) / 3500.0)
        if len(scrape.pages) >= 2:
            evidence_strength = min(1.0, evidence_strength + 0.1)
        if scrape.fetch_errors:
            evidence_strength *= 0.85
            notes.append("Some page fetches failed; evidence may be partial.")

        industry_tokens = [t for t in (ai.industry or "").replace(",", " ").split() if len(t) > 2]
        tech_tokens = list(ai.tech_stack or [])
        consistency = 0.5 * _overlap_score(text_blob, industry_tokens) + 0.5 * _overlap_score(
            text_blob, tech_tokens
        )
        if ai.industry and ai.industry.lower() in text_blob:
            consistency = min(1.0, consistency + 0.25)

        wc = max(0.0, min(1.0, website_confidence))

        sub = QualitySubscores(
            completeness=round(completeness, 4),
            evidence_strength=round(evidence_strength, 4),
            consistency=round(consistency, 4),
            website_confidence=round(wc, 4),
        )

        final = (
            0.30 * sub.completeness
            + 0.30 * sub.evidence_strength
            + 0.25 * sub.consistency
            + 0.15 * sub.website_confidence
        )
        final = round(max(0.0, min(1.0, final)), 4)

        logger.info(
            "Quality report computed",
            extra={
                "final_score": final,
                "completeness": sub.completeness,
                "evidence_strength": sub.evidence_strength,
                "consistency": sub.consistency,
                "website_confidence": sub.website_confidence,
            },
        )
        return QualityReport(final_score=final, subscores=sub, notes=notes)
