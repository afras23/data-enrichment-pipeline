"""
Correlation ID propagation for structured logging across async call stacks.
"""

from contextvars import ContextVar

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the active correlation id or empty string."""

    return correlation_id_ctx.get()


def set_correlation_id(value: str) -> None:
    """Set correlation id for the current async context."""

    correlation_id_ctx.set(value)
