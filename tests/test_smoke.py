"""Smoke tests for scaffold — expanded in later implementation phases."""

from app.main import scaffold_marker


def test_scaffold_marker() -> None:
    """Application package imports and exposes a stable scaffold string."""

    assert scaffold_marker() == "data-enrichment-pipeline"
