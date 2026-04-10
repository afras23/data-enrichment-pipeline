"""
API-level edge cases (validation and HTTP contracts); external I/O stubbed where needed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def sync_client(test_app: object) -> object:
    """Synchronous TestClient with lifespan."""

    with TestClient(test_app) as client:
        yield client


def test_post_enrichment_run_rejects_empty_company_list(sync_client: TestClient) -> None:
    """Pydantic min_length=1 on companies rejects an empty list with 422."""

    resp = sync_client.post("/api/v1/enrichment/run", json={"companies": []})
    assert resp.status_code == 422
    detail = resp.json().get("detail", [])
    assert isinstance(detail, list)
    assert any("companies" in str(item).lower() for item in detail)


@pytest.mark.parametrize("bad_body", [{}, {"companies": None}, {"companies": "not-a-list"}])
def test_post_enrichment_run_rejects_malformed_body(
    sync_client: TestClient,
    bad_body: object,
) -> None:
    """Malformed JSON bodies fail validation before scheduling work."""

    resp = sync_client.post("/api/v1/enrichment/run", json=bad_body)
    assert resp.status_code == 422
