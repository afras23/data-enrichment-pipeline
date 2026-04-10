"""
Unit tests for OpenAIEnrichmentClient — validation and error paths (SDK fully mocked).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.core.exceptions import EnrichmentAIError
from app.services.ai.openai_client import OpenAIEnrichmentClient


def _mock_completion(
    content: str, *, prompt_tokens: int = 10, completion_tokens: int = 10
) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return resp


@pytest.mark.asyncio
async def test_enrich_company_raises_enrichment_ai_error_when_openai_returns_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-JSON assistant content surfaces as EnrichmentAIError (production path)."""

    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)
    client = OpenAIEnrichmentClient(api_key="sk-test")
    client._client = MagicMock()
    client._client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("this is not json {")
    )

    with pytest.raises(EnrichmentAIError, match="non-JSON"):
        await client.enrich_company("Acme Corp", "some text", {})


@pytest.mark.asyncio
async def test_enrich_company_raises_when_payload_fails_pydantic_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema mismatch after JSON parse raises EnrichmentAIError with validation message."""

    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)
    bad = '{"tech_stack": "must_be_list_not_string"}'
    client = OpenAIEnrichmentClient(api_key="sk-test")
    client._client = MagicMock()
    client._client.chat.completions.create = AsyncMock(return_value=_mock_completion(bad))

    with pytest.raises(EnrichmentAIError, match="schema validation"):
        await client.enrich_company("Acme Corp", "some text", {})


@pytest.mark.asyncio
async def test_enrich_company_succeeds_with_valid_minimal_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: valid JSON object maps to AIEnrichmentResult and returns metrics."""

    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)
    payload = (
        '{"industry": "Software", "company_description": null, "company_size_band": null, '
        '"tech_stack": [], "contacts_or_signals": [], "confidence_notes": null, "evidence_summary": null}'
    )
    client = OpenAIEnrichmentClient(api_key="sk-test")
    client._client = MagicMock()
    client._client.chat.completions.create = AsyncMock(return_value=_mock_completion(payload))

    result, metrics = await client.enrich_company("Acme", "x", {"hint": True})
    assert result.industry == "Software"
    assert metrics.input_tokens == 10
    assert metrics.cost_usd >= 0.0


@pytest.mark.asyncio
async def test_enrich_company_propagates_sdk_exception_as_enrichment_ai_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network/SDK failures are wrapped without calling the real OpenAI network."""

    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)
    client = OpenAIEnrichmentClient(api_key="sk-test")
    client._client = MagicMock()
    client._client.chat.completions.create = AsyncMock(side_effect=TimeoutError("upstream"))

    with pytest.raises(EnrichmentAIError, match="OpenAI request failed"):
        await client.enrich_company("Acme", "text", {})
