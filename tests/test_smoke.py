"""Smoke tests for application wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(test_app: object) -> None:
    """Root API health returns OK."""

    with TestClient(test_app) as client:
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"
