"""
Pydantic domain models for scraping, AI enrichment, and quality reporting.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PageSignals(BaseModel):
    """Deterministic signals extracted from a single HTML page."""

    url: str = Field(..., description="Final URL after redirects")
    title: str | None = Field(default=None)
    meta_description: str | None = Field(default=None)
    headings: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    social_links: list[str] = Field(default_factory=list)
    internal_nav_links: dict[str, str] = Field(
        default_factory=dict,
        description="Label or path key to absolute URL for about/contact/careers/privacy",
    )
    script_hosts: list[str] = Field(default_factory=list, description="Hosts from script[src]")
    technology_hints: list[str] = Field(
        default_factory=list,
        description="Heuristic tech tokens from scripts and visible text",
    )
    json_ld_blocks: list[dict[str, object]] = Field(
        default_factory=list,
        description="Parsed JSON-LD objects",
    )
    visible_text_sample: str = Field(
        default="",
        description="Truncated visible text for AI and quality scoring",
    )


class ScrapedSiteBundle(BaseModel):
    """Aggregated multi-page scrape for one company site."""

    base_url: str
    pages: list[PageSignals] = Field(default_factory=list)
    combined_visible_text: str = Field(
        default="", description="Bounded concatenation for LLM input"
    )
    total_bytes_fetched: int = Field(default=0, ge=0)
    fetch_errors: list[str] = Field(default_factory=list)


_ALLOWED_SIZE_BANDS = frozenset(
    {"1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"},
)


class AIEnrichmentResult(BaseModel):
    """Structured output from the LLM after validation."""

    model_config = ConfigDict(extra="ignore")

    industry: str | None = None
    company_description: str | None = None
    company_size_band: str | None = Field(
        default=None,
        description="One of the allowed size band labels or null",
    )
    tech_stack: list[str] = Field(default_factory=list)
    contacts_or_signals: list[str] = Field(default_factory=list)
    confidence_notes: str | None = None
    evidence_summary: str | None = None

    @field_validator("company_size_band")
    @classmethod
    def normalize_size_band(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v in _ALLOWED_SIZE_BANDS:
            return v
        return None


class QualitySubscores(BaseModel):
    """Decomposed quality dimensions in [0, 1]."""

    completeness: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    consistency: float = Field(ge=0.0, le=1.0)
    website_confidence: float = Field(ge=0.0, le=1.0)


class QualityReport(BaseModel):
    """Final quality assessment for an enriched company record."""

    final_score: float = Field(ge=0.0, le=1.0)
    subscores: QualitySubscores
    notes: list[str] = Field(default_factory=list)
