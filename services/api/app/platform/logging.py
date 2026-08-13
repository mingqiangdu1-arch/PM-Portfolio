from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.platform.trace import current_trace_id


_RESERVED = set(logging.makeLogRecord({}).__dict__)
_SENSITIVE_FRAGMENTS = ("authorization", "cookie", "password", "secret", "token", "signed_url")


def _safe_extras(record: logging.LogRecord) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED or any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            extras[key] = value
    return extras


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": current_trace_id.get(),
        }
        payload.update(_safe_extras(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
