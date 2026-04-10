"""
FastAPI application entry point.

Scaffold stage: minimal surface so CI (lint, types, tests) can run.
"""


def scaffold_marker() -> str:
    """Return a fixed string used by smoke tests until the full app is wired."""

    return "data-enrichment-pipeline"
