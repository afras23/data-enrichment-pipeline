"""Unit tests for deterministic HTML signal extraction."""

from __future__ import annotations

import pytest

from app.services.html_extraction import extract_page_signals


def test_extract_page_signals_finds_title_meta_emails_and_jsonld() -> None:
    """Parser captures core deterministic fields from representative HTML."""

    html = """
    <html><head>
    <title>Acme Labs</title>
    <meta name="description" content="We ship widgets." />
    </head><body>
    <h1>Hello</h1>
    <p>Email sales@acme.example for info.</p>
    <script type="application/ld+json">{"@type":"Organization","name":"Acme"}</script>
    </body></html>
    """
    sig = extract_page_signals(html, "https://acme.example/")
    assert sig.title == "Acme Labs"
    assert sig.meta_description == "We ship widgets."
    assert "sales@acme.example" in sig.emails
    assert sig.json_ld_blocks
    assert any(b.get("@type") == "Organization" for b in sig.json_ld_blocks)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/about-us", "about"),
        ("/contact", "contact"),
        ("/careers/jobs", "careers"),
        ("/privacy-policy", "privacy"),
    ],
)
def test_internal_nav_classification(path: str, expected: str) -> None:
    """Internal links map to standard section labels when paths match heuristics."""

    html = f'<html><body><a href="{path}">link</a></body></html>'
    sig = extract_page_signals(html, "https://corp.example{path}")
    assert expected in sig.internal_nav_links


def test_technology_hints_from_scripts_and_text() -> None:
    """Heuristic tech tokens surface from script hosts and visible copy."""

    html = """
    <html><body>
    <script src="https://cdn.example/react.min.js"></script>
    <p>We use python and django for our api.</p>
    </body></html>
    """
    sig = extract_page_signals(html, "https://app.example/")
    assert "react" in sig.technology_hints or "python" in sig.technology_hints
