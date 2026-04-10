"""
Multi-page site scraping orchestration using WebFetchClient and html extraction.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from app.config import settings
from app.integrations.web_client import WebFetchClient
from app.schemas.domain import PageSignals, ScrapedSiteBundle
from app.services.html_extraction import extract_page_signals

logger = logging.getLogger(__name__)


class SiteScraperService:
    """Fetch homepage and linked common pages; aggregate deterministic signals."""

    def __init__(self, web_client: WebFetchClient | None = None) -> None:
        self._web = web_client or WebFetchClient()

    async def scrape_site(self, website_url: str) -> ScrapedSiteBundle:
        """
        Scrape homepage and a bounded set of internal pages discovered from nav links.

        Args:
            website_url: Resolved company website (http/https).

        Returns:
            ScrapedSiteBundle with per-page signals and combined text for downstream AI.
        """

        parsed = urlparse(website_url)
        if not parsed.scheme:
            website_url = "https://" + website_url.lstrip("/")
        base = website_url if website_url.endswith("/") else website_url
        origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"

        pages: list[PageSignals] = []
        errors: list[str] = []
        total_bytes = 0
        to_fetch: list[str] = [base.rstrip("/") or base]
        seen: set[str] = set()

        max_pages = settings.max_pages_per_company
        while to_fetch and len(pages) < max_pages:
            url = to_fetch.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                result = await self._web.fetch(url)
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                logger.warning(
                    "Page fetch skipped",
                    extra={"url": url[:200], "error": str(exc)},
                )
                continue

            total_bytes += result.body_bytes_len
            if result.status_code >= 400:
                errors.append(f"{url}: HTTP {result.status_code}")
                continue
            ctype = result.headers.get("content-type", "")
            if "html" not in ctype and result.body_text.strip().startswith("<") is False:
                errors.append(f"{url}: non-html content-type {ctype}")
                continue

            signals = extract_page_signals(result.body_text, result.url)
            pages.append(signals)

            if len(pages) == 1:
                for key in ("about", "contact", "careers", "privacy"):
                    link = signals.internal_nav_links.get(key)
                    if link and link not in seen and len(seen) + len(to_fetch) < max_pages:
                        to_fetch.append(link)
                for h in ("about", "contact", "careers", "privacy"):
                    candidate = urljoin(origin + "/", h)
                    if candidate not in seen and candidate not in to_fetch:
                        to_fetch.append(candidate)

        combined_parts: list[str] = []
        for p in pages:
            header = f"--- PAGE: {p.url} ---\n"
            combined_parts.append(header + p.visible_text_sample)
        combined = "\n\n".join(combined_parts)[:80_000]

        bundle = ScrapedSiteBundle(
            base_url=origin,
            pages=pages,
            combined_visible_text=combined,
            total_bytes_fetched=total_bytes,
            fetch_errors=errors,
        )
        logger.info(
            "Site scrape finished",
            extra={
                "pages": len(pages),
                "bytes": total_bytes,
                "errors": len(errors),
            },
        )
        return bundle
