"""
Shared pytest fixtures: in-memory SQLite, patched session factory, FastAPI client.
"""

from __future__ import annotations

import os

# Tests must force SQLite before any application imports instantiate the async engine.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAI_API_KEY"] = "sk-test-key-for-ci"

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.db.session as session_module
from app.db.base import Base


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[Any, None]:
    """In-memory SQLite engine shared across a test's sessions."""

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def patch_session_factory(
    sqlite_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    """Point application session factory at the test SQLite engine."""

    factory = async_sessionmaker(
        sqlite_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    monkeypatch.setattr(session_module, "async_session_factory", factory)
    monkeypatch.setattr(session_module, "engine", sqlite_engine)
    return factory


@pytest.fixture
def test_app(patch_session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """Fresh FastAPI app wired to the test database."""

    from app.main import create_app

    return create_app()


@pytest.fixture
async def async_client(test_app: Any) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client against the ASGI app."""

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_openai_enrichment() -> MagicMock:
    """Return a patched OpenAIEnrichmentClient-compatible mock."""

    mock = MagicMock()

    async def _enrich(*_a: object, **_k: object) -> tuple[object, object]:
        from app.schemas.domain import AIEnrichmentResult
        from app.services.ai.openai_client import OpenAICallMetrics

        result = AIEnrichmentResult(
            industry="Software",
            company_description="TestCo builds widgets.",
            company_size_band="51-200",
            tech_stack=["python", "react"],
            contacts_or_signals=["contact@testco.example"],
            confidence_notes="fixture",
            evidence_summary="homepage",
        )
        metrics = OpenAICallMetrics(
            model="gpt-4o-mini",
            prompt_version="company_enrichment_v1",
            input_tokens=120,
            output_tokens=80,
            latency_ms=50.0,
            cost_usd=0.0001,
        )
        return result, metrics

    mock.enrich_company = AsyncMock(side_effect=_enrich)
    return mock


@pytest.fixture
def mock_web_fetch() -> MagicMock:
    """Return deterministic HTML for discovery and scraping."""

    from app.integrations.web_client import WebFetchResult

    html = """
    <!doctype html>
    <html><head>
    <title>TestCo — About</title>
    <meta name="description" content="We build widgets for teams." />
    <script src="https://www.googletagmanager.com/gtag/js?id=G-TEST"></script>
    </head><body>
    <h1>About TestCo</h1>
    <p>Contact us at hello@testco.example or call +1 415-555-0100.</p>
    <a href="/contact">Contact</a>
    <a href="https://www.linkedin.com/company/testco">LinkedIn</a>
    <script type="application/ld+json">
    {"@type":"Organization","name":"TestCo","email":"hello@testco.example"}
    </script>
    </body></html>
    """

    async def _fetch(url: str) -> WebFetchResult:
        return WebFetchResult(
            url=url,
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body_text=html,
            body_bytes_len=len(html.encode()),
        )

    client = MagicMock()
    client.fetch = AsyncMock(side_effect=_fetch)
    return client
