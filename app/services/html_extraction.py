"""
Deterministic HTML parsing: titles, meta, headings, contacts, JSON-LD, tech hints.

Pure functions operating on HTML strings for straightforward unit testing.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.schemas.domain import PageSignals

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}(?:[\s.-]?\d{1,4})?"
)
_SOCIAL_HOSTS = (
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "github.com",
)
_TECH_KEYWORDS = (
    "react",
    "vue",
    "angular",
    "next.js",
    "nextjs",
    "node",
    "python",
    "django",
    "flask",
    "fastapi",
    "ruby",
    "rails",
    "php",
    "wordpress",
    "shopify",
    "stripe",
    "hubspot",
    "salesforce",
    "segment",
    "google-analytics",
    "googletagmanager",
    "gtag",
    "mixpanel",
    "datadog",
    "newrelic",
)


def _normalize_url(base: str, href: str | None) -> str | None:
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    return urljoin(base, href)


def _classify_nav_link(path: str) -> str | None:
    p = path.lower()
    if any(x in p for x in ("/about", "about-us", "our-story")):
        return "about"
    if any(x in p for x in ("/contact", "contact-us", "get-in-touch")):
        return "contact"
    if any(x in p for x in ("/career", "jobs", "hiring")):
        return "careers"
    if "privacy" in p or "policy" in p:
        return "privacy"
    return None


def extract_page_signals(
    html: str, page_url: str, *, text_sample_max_chars: int = 12_000
) -> PageSignals:
    """
    Parse HTML and extract deterministic signals for one page.

    Args:
        html: Raw HTML string.
        page_url: Canonical URL for this document (for resolving relative links).
        text_sample_max_chars: Max length of visible_text_sample stored.
    """

    soup = BeautifulSoup(html, "html.parser")

    json_ld_blocks: list[dict[str, object]] = []
    for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (sc.string or sc.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                json_ld_blocks.append(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        json_ld_blocks.append(item)
        except json.JSONDecodeError:
            logger.debug("JSON-LD parse skipped", extra={"preview": raw[:120]})

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if isinstance(title_tag, Tag) else None

    meta_desc = None
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if isinstance(md, Tag) and md.get("content"):
        meta_desc = str(md.get("content", "")).strip()
    og = soup.find("meta", property="og:description")
    if not meta_desc and isinstance(og, Tag) and og.get("content"):
        meta_desc = str(og.get("content", "")).strip()

    headings: list[str] = []
    for hx in soup.find_all(["h1", "h2", "h3"]):
        t = hx.get_text(" ", strip=True)
        if t:
            headings.append(t)

    visible_text = soup.get_text("\n", strip=True)
    text_sample = visible_text[:text_sample_max_chars]

    emails = sorted(set(_EMAIL_RE.findall(visible_text)))

    phones: list[str] = []
    for m in _PHONE_RE.finditer(visible_text):
        chunk = m.group(0).strip()
        if len(chunk) >= 8:
            phones.append(chunk)
    phones = sorted(set(phones))[:20]

    social_links: list[str] = []
    internal_nav: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        abs_url = _normalize_url(page_url, a.get("href"))
        if not abs_url:
            continue
        host = (urlparse(abs_url).hostname or "").lower()
        if any(s in host for s in _SOCIAL_HOSTS):
            social_links.append(abs_url)
        same = host == (urlparse(page_url).hostname or "").lower()
        if same:
            path = urlparse(abs_url).path or "/"
            label = _classify_nav_link(path)
            if label and label not in internal_nav:
                internal_nav[label] = abs_url

    script_hosts: list[str] = []
    for sc in soup.find_all("script", src=True):
        joined = urljoin(page_url, sc["src"])
        h = urlparse(joined).hostname
        if h:
            script_hosts.append(h.lower())
    script_hosts = sorted(set(script_hosts))

    tech_hints: list[str] = []
    blob = (visible_text + " " + " ".join(script_hosts)).lower()
    for kw in _TECH_KEYWORDS:
        if kw in blob:
            tech_hints.append(kw)

    return PageSignals(
        url=page_url,
        title=title,
        meta_description=meta_desc,
        headings=headings[:40],
        emails=emails[:30],
        phone_numbers=phones,
        social_links=sorted(set(social_links))[:30],
        internal_nav_links=internal_nav,
        script_hosts=script_hosts[:40],
        technology_hints=sorted(set(tech_hints)),
        json_ld_blocks=json_ld_blocks[:20],
        visible_text_sample=text_sample,
    )
