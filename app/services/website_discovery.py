"""
Heuristic website discovery from a company name (mockable, no paid search API required).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.config import settings
from app.integrations.web_client import WebFetchClient

logger = logging.getLogger(__name__)


def _normalize_key(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s[:48] or "company"


def normalize_company_key(name: str) -> str:
    """Public helper for deduplication keys shared with persistence."""

    return _normalize_key(name)


@dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of website discovery for one company name."""

    website_url: str | None
    confidence: float
    candidates_tried: list[str]
    notes: str


class WebsiteDiscoveryService:
    """Probe likely apex domains derived from the company name."""

    def __init__(self, web_client: WebFetchClient | None = None) -> None:
        self._web = web_client or WebFetchClient()

    async def discover(self, company_name: str) -> DiscoveryResult:
        """
        Return a resolved https URL when a candidate responds with HTML.

        Confidence is a coarse score in [0, 1] based on HTTP success and content sniffing.
        """

        slug = _normalize_key(company_name)
        hosts = [f"{slug}.com", f"{slug}.io"]
        candidates: list[str] = []
        prefixes = ("https://www.", "https://") if settings.discovery_try_www else ("https://",)
        for host in hosts:
            for prefix in prefixes:
                url = f"{prefix}{host}/"
                candidates.append(url)
                try:
                    result = await self._web.fetch(url)
                except Exception as exc:
                    logger.info(
                        "Discovery candidate failed",
                        extra={"url": url[:120], "error": str(exc)},
                    )
                    continue
                if result.status_code >= 400:
                    continue
                ctype = result.headers.get("content-type", "")
                body = result.body_text[:500].lower()
                looks_html = "html" in ctype or "<html" in body or "<!doctype" in body
                if not looks_html:
                    continue
                conf = 0.75 if "www." in result.url else 0.65
                return DiscoveryResult(
                    website_url=result.url.split("#")[0],
                    confidence=min(1.0, conf),
                    candidates_tried=candidates,
                    notes="heuristic_domain_probe",
                )

        return DiscoveryResult(
            website_url=None,
            confidence=0.0,
            candidates_tried=candidates,
            notes="no_responsive_candidate",
        )
