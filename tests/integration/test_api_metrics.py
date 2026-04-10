"""API and metrics integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def sync_client(test_app: object) -> object:
    """Synchronous TestClient for background task execution."""

    with TestClient(test_app) as client:
        yield client


def test_post_run_and_list_routes(sync_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST enrichment run schedules processing and GET lists appear."""

    async def _skip_pipeline(*_a: object, **_k: object) -> None:
        """Avoid real HTTP/OpenAI during API contract test."""

    import app.api.routes.enrichment as enrichment_routes

    monkeypatch.setattr(enrichment_routes, "_run_pipeline_job", _skip_pipeline)

    resp = sync_client.post(
        "/api/v1/enrichment/run",
        json={"companies": ["Globex"]},
        headers={"X-Correlation-ID": "cid-123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body

    runs = sync_client.get("/api/v1/runs").json()
    assert runs["total"] >= 1

    companies = sync_client.get("/api/v1/companies").json()
    assert companies["total"] >= 0


def test_metrics_endpoint_returns_pipeline_fields(sync_client: TestClient) -> None:
    """Metrics include aggregate keys backed by the database."""

    metrics = sync_client.get("/api/v1/metrics").json()
    assert "runs_total" in metrics
    assert "records_total" in metrics
    assert "avg_quality_score" in metrics
    assert "system" in metrics


def test_get_company_404(sync_client: TestClient) -> None:
    """Unknown id returns 404."""

    import uuid

    rid = uuid.uuid4()
    r = sync_client.get(f"/api/v1/companies/{rid}")
    assert r.status_code == 404


def test_health_ready(sync_client: TestClient) -> None:
    """Readiness includes database check."""

    r = sync_client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"
