"""
Application logging: optional JSON lines for production-style structured logs.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.config import settings
from app.core.correlation import get_correlation_id


class CorrelationIdFilter(logging.Filter):
    """Inject correlation_id from context into every log record when present."""

    def filter(self, record: logging.LogRecord) -> bool:
        cid = get_correlation_id()
        if cid and not getattr(record, "correlation_id", None):
            record.correlation_id = cid
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line; includes correlation_id when set on the record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        cid = getattr(record, "correlation_id", None) or get_correlation_id()
        if cid:
            payload["correlation_id"] = cid
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key in ("env", "run_id", "company"):
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None:
                    payload[key] = val
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configure root logger once (text or JSON per settings)."""

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(CorrelationIdFilter())
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
