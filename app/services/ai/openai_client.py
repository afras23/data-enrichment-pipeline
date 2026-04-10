"""
OpenAI API wrapper with token usage, latency, and cost estimation per call.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import settings
from app.core.correlation import get_correlation_id
from app.core.exceptions import EnrichmentAIError
from app.schemas.domain import AIEnrichmentResult
from app.services.ai import prompts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAICallMetrics:
    """Telemetry for a single OpenAI request."""

    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


class OpenAIEnrichmentClient:
    """Async OpenAI client for structured JSON enrichment."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key if api_key is not None else settings.openai_api_key
        self._model = model or settings.openai_model
        self._client = AsyncOpenAI(api_key=key) if key else None

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        inp = input_tokens * settings.openai_input_cost_per_million / 1_000_000
        out = output_tokens * settings.openai_output_cost_per_million / 1_000_000
        return round(inp + out, 8)

    async def enrich_company(
        self,
        company_name: str,
        scraped_text: str,
        deterministic_hint: dict[str, object],
    ) -> tuple[AIEnrichmentResult, OpenAICallMetrics]:
        """
        Call OpenAI with versioned prompts and validate JSON into AIEnrichmentResult.

        Raises:
            EnrichmentAIError: When the API key is missing, the call fails, or JSON is invalid.
        """

        if not self._client:
            raise EnrichmentAIError("OpenAI API key is not configured")

        user_prompt = prompts.build_user_prompt(
            company_name,
            scraped_text,
            json.dumps(deterministic_hint, ensure_ascii=False)[:8000],
        )

        t0 = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=settings.openai_temperature,
                max_tokens=settings.openai_max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=settings.openai_timeout_seconds,
            )
        except Exception as exc:
            logger.error(
                "OpenAI request failed",
                extra={
                    "correlation_id": get_correlation_id(),
                    "error": str(exc),
                    "model": self._model,
                },
            )
            raise EnrichmentAIError("OpenAI request failed", details={"error": str(exc)}) from exc

        latency_ms = (time.perf_counter() - t0) * 1000.0
        choice = response.choices[0].message.content or "{}"
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = self._estimate_cost(input_tokens, output_tokens)

        try:
            payload = json.loads(choice)
        except json.JSONDecodeError as exc:
            raise EnrichmentAIError("OpenAI returned non-JSON content") from exc

        try:
            result = AIEnrichmentResult.model_validate(payload)
        except Exception as exc:
            raise EnrichmentAIError(
                "OpenAI JSON failed schema validation", details={"preview": choice[:300]}
            ) from exc

        metrics = OpenAICallMetrics(
            model=self._model,
            prompt_version=prompts.PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 2),
            cost_usd=cost,
        )
        logger.info(
            "OpenAI enrichment completed",
            extra={
                "correlation_id": get_correlation_id(),
                "model": self._model,
                "prompt_version": prompts.PROMPT_VERSION,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
                "latency_ms": round(latency_ms, 2),
            },
        )
        return result, metrics
