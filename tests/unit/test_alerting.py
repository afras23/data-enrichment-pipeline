"""Alert evaluation unit tests."""

from __future__ import annotations

import pytest

from app.services.alerting import (
    AlertChannel,
    AlertEvaluationService,
    MockCompositeNotifier,
)


@pytest.mark.asyncio
async def test_alert_on_many_failures() -> None:
    """Notifier receives Slack alert when failed count crosses threshold."""

    notifier = MockCompositeNotifier()
    svc = AlertEvaluationService(notifier, failure_streak_threshold=2, avg_quality_threshold=0.1)
    await svc.maybe_alert_on_run_outcome(
        run_id="run-1",
        failed_count=3,
        total_count=5,
        avg_quality=0.5,
    )
    assert any(ch == AlertChannel.MOCK_SLACK for ch, _ in notifier.calls)


@pytest.mark.asyncio
async def test_alert_on_low_average_quality() -> None:
    """Notifier receives email alert when average quality is very low."""

    notifier = MockCompositeNotifier()
    svc = AlertEvaluationService(notifier, failure_streak_threshold=100, avg_quality_threshold=0.5)
    await svc.maybe_alert_on_run_outcome(
        run_id="run-2",
        failed_count=0,
        total_count=3,
        avg_quality=0.2,
    )
    assert any(
        ch == AlertChannel.MOCK_EMAIL for ch, ev in notifier.calls if "quality" in ev.title.lower()
    )


@pytest.mark.asyncio
async def test_no_alert_when_healthy() -> None:
    """No alerts when metrics are within thresholds."""

    notifier = MockCompositeNotifier()
    svc = AlertEvaluationService(notifier, failure_streak_threshold=5, avg_quality_threshold=0.2)
    await svc.maybe_alert_on_run_outcome(
        run_id="run-3",
        failed_count=1,
        total_count=4,
        avg_quality=0.9,
    )
    assert notifier.calls == []
