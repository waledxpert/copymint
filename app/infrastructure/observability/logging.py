"""Minimal JSON logging with mandatory central redaction."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.infrastructure.observability.redaction import redact, redact_text


class RedactingFilter(logging.Filter):
    """Redact records before any formatter or handler can emit them."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg)
        if isinstance(record.args, dict):
            record.args = redact(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(redact(item) for item in record.args)
        return True


class JsonFormatter(logging.Formatter):
    """Emit a compact allowlisted JSON log record."""

    _CONTEXT_FIELDS = (
        "event",
        "correlation_id",
        "workspace_id",
        "user_id",
        "task_id",
        "chain_id",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for field in self._CONTEXT_FIELDS:
            if hasattr(record, field):
                payload[field] = redact(getattr(record, field), key=field)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the one supported root logging pipeline."""
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
