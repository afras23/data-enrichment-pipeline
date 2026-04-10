"""
Async HTTP client for outbound web fetches used by the scraping pipeline.

All external web access goes through this module so tests can mock or stub it.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.core.exceptions import ScrapeError

logger = logging.getLogger(__name__)

_PRIVATE_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _host_blocked(hostname: str) -> bool:
    """Return True if hostname resolves to a blocked / private IP — best-effort without DNS."""

    if hostname in ("localhost",):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return True
        for net in _PRIVATE_NETS:
            if addr in net:
                return True
    except ValueError:
        pass
    return False


@dataclass(frozen=True)
class WebFetchResult:
    """Result of a single HTTP GET."""

    url: str
    status_code: int
    headers: dict[str, str]
    body_text: str
    body_bytes_len: int


class WebFetchClient:
    """
    Integration client wrapping httpx for scraping.

    Enforces response size limits, redirect caps, and basic SSRF protections.
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout_seconds: float | None = None,
        max_redirects: int | None = None,
        max_response_bytes: int | None = None,
    ) -> None:
        self._user_agent = user_agent or settings.http_user_agent
        self._timeout = timeout_seconds or settings.http_timeout_seconds
        self._max_redirects = (
            max_redirects if max_redirects is not None else settings.http_max_redirects
        )
        self._max_bytes = max_response_bytes or settings.http_max_response_bytes

    async def fetch(self, url: str) -> WebFetchResult:
        """
        Perform a GET request and return decoded text (truncated if over limit).

        Raises:
            ScrapeError: If URL is unsafe, or the request fails.
        """

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ScrapeError("Only http/https URLs are allowed", details={"url": url})
        if not parsed.netloc:
            raise ScrapeError("URL missing host", details={"url": url})
        if _host_blocked(parsed.hostname or ""):
            raise ScrapeError("Host blocked by policy", details={"host": parsed.hostname})

        limits = httpx.Limits(max_keepalive_connections=20, max_connections=40)
        timeout = httpx.Timeout(self._timeout)
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
            max_redirects=self._max_redirects,
            headers=headers,
        ) as client:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                logger.warning(
                    "HTTP fetch failed",
                    extra={
                        "url": url[:200],
                        "error": str(exc),
                    },
                )
                raise ScrapeError(
                    "HTTP request failed", details={"url": url, "error": str(exc)}
                ) from exc

        raw = response.content
        if len(raw) > self._max_bytes:
            raw = raw[: self._max_bytes]
        text = raw.decode(response.encoding or "utf-8", errors="replace")

        hdrs = {k.lower(): v for k, v in response.headers.items()}
        result = WebFetchResult(
            url=str(response.url),
            status_code=response.status_code,
            headers=hdrs,
            body_text=text,
            body_bytes_len=len(raw),
        )
        logger.info(
            "HTTP fetch completed",
            extra={
                "status_code": result.status_code,
                "bytes": result.body_bytes_len,
                "url": result.url[:200],
            },
        )
        return result
