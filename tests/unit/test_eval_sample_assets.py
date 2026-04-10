"""Sanity checks for evaluation/demo YAML fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sample_inputs"


def test_sample_companies_yaml_structure() -> None:
    raw = yaml.safe_load((FIXTURES / "companies.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "companies" in raw
    companies = raw["companies"]
    assert isinstance(companies, list)
    assert len(companies) >= 1
    for row in companies:
        assert isinstance(row, dict)
        assert "name" in row


def test_sample_expected_yaml_structure() -> None:
    raw = yaml.safe_load((FIXTURES / "expected_enrichment.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    ex = raw.get("expectations")
    assert isinstance(ex, list)
    for row in ex:
        assert isinstance(row, dict)
        assert "company_name" in row


@pytest.mark.parametrize(
    "filename",
    ["companies.yaml", "expected_enrichment.yaml"],
)
def test_fixtures_match_data_sample_run(filename: str) -> None:
    """Keep demo data/ and tests/fixtures/sample_inputs/ in sync for evaluation."""

    fixture_path = FIXTURES / filename
    data_path = REPO_ROOT / "data" / "sample_run" / filename
    assert data_path.read_text(encoding="utf-8") == fixture_path.read_text(encoding="utf-8")
