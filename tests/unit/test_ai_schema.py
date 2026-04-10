"""AI output schema validation tests."""

from __future__ import annotations

from app.schemas.domain import AIEnrichmentResult


def test_ai_enrichment_accepts_valid_payload() -> None:
    """Model accepts well-formed JSON-aligned payload."""

    payload = {
        "industry": "FinTech",
        "company_description": "Payments",
        "company_size_band": "11-50",
        "tech_stack": ["aws"],
        "contacts_or_signals": ["https://x.example/contact"],
        "confidence_notes": "n/a",
        "evidence_summary": "home",
    }
    m = AIEnrichmentResult.model_validate(payload)
    assert m.industry == "FinTech"


def test_ai_enrichment_rejects_invalid_size_band() -> None:
    """Unknown size bands normalize to null."""

    m = AIEnrichmentResult.model_validate({"company_size_band": "not-a-band"})
    assert m.company_size_band is None


def test_ai_enrichment_ignores_extra_keys() -> None:
    """Unknown keys are ignored (extra=forbid not used)."""

    m = AIEnrichmentResult.model_validate({"industry": "X", "extra_field": 1})
    assert m.industry == "X"
    assert "extra_field" not in m.model_dump()
