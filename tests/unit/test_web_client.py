"""WebFetchClient unit tests."""

from __future__ import annotations

import pytest

from app.core.exceptions import ScrapeError
from app.integrations.web_client import WebFetchClient, _host_blocked


@pytest.mark.parametrize(
    "host,blocked",
    [
        ("localhost", True),
        ("10.0.0.1", True),
        ("example.com", False),
    ],
)
def test_host_blocked_policy(host: str, blocked: bool) -> None:
    """Private and loopback hosts are blocked without DNS lookup."""

    assert _host_blocked(host) is blocked


@pytest.mark.asyncio
async def test_fetch_rejects_non_http_scheme() -> None:
    """Only http(s) URLs are allowed."""

    client = WebFetchClient()
    with pytest.raises(ScrapeError):
        await client.fetch("ftp://example.com/")
