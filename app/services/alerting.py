"""
Alert integrations for pipeline health (mockable for tests and local dev).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class AlertChannel(StrEnum):
    """Supported notifier channels (mock implementations in tests)."""

    MOCK_EMAIL = "mock_email"
    MOCK_SLACK = "mock_slack"


@dataclass
class AlertEvent:
    """Structured alert payload."""

    title: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AlertNotifier(ABC):
    """Abstract notifier — swap for real SES/Slack webhooks without changing callers."""

    @abstractmethod
    async def send(self, channel: AlertChannel, event: AlertEvent) -> None:
        """Send alert to the given channel."""


class MockCompositeNotifier(AlertNotifier):
    """
    Records alert invocations for assertions; logs structured events.

    Real deployments would replace with email + Slack webhook clients.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[AlertChannel, AlertEvent]] = []

    async def send(self, channel: AlertChannel, event: AlertEvent) -> None:
        self.calls.append((channel, event))
        logger.warning(
            "Alert dispatched (mock)",
            extra={
                "channel": channel.value,
                "title": event.title,
                "body_preview": event.body[:200],
            },
        )


class AlertEvaluationService:
    """Decide when to raise alerts based on run-level aggregates."""

    def __init__(
        self,
        notifier: AlertNotifier,
        *,
        failure_streak_threshold: int,
        avg_quality_threshold: float,
    ) -> None:
        self._notifier = notifier
        self._failure_streak_threshold = failure_streak_threshold
        self._avg_quality_threshold = avg_quality_threshold

    async def maybe_alert_on_run_outcome(
        self,
        *,
        run_id: str,
        failed_count: int,
        total_count: int,
        avg_quality: float | None,
    ) -> None:
        """Send mock alerts when thresholds are breached."""

        if total_count == 0:
            return

        if failed_count >= self._failure_streak_threshold:
            await self._notifier.send(
                AlertChannel.MOCK_SLACK,
                AlertEvent(
                    title="Enrichment failures threshold",
                    body=(
                        f"Run {run_id} has {failed_count} failed companies "
                        f"(threshold {self._failure_streak_threshold}) out of {total_count}."
                    ),
                    metadata={"run_id": run_id},
                ),
            )

        if (
            avg_quality is not None
            and avg_quality < self._avg_quality_threshold
            and total_count >= 2
        ):
            await self._notifier.send(
                AlertChannel.MOCK_EMAIL,
                AlertEvent(
                    title="Low average enrichment quality",
                    body=(
                        f"Run {run_id} average quality {avg_quality:.2f} "
                        f"is below threshold {self._avg_quality_threshold:.2f}."
                    ),
                    metadata={"run_id": run_id, "avg_quality": avg_quality},
                ),
            )
