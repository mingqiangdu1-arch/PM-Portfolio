from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
import logging
import re
from typing import Any


_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|password|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)",
    re.IGNORECASE,
)


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        if _SENSITIVE_KEY.search(str(key)):
            redacted[str(key)] = "[REDACTED]"
        elif isinstance(item, Mapping):
            redacted[str(key)] = redact_mapping(item)
        elif isinstance(item, list):
            redacted[str(key)] = [
                redact_mapping(entry) if isinstance(entry, Mapping) else entry
                for entry in item
            ]
        else:
            redacted[str(key)] = item
    return redacted


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": getattr(record, "service", "ai-api"),
            "environment": getattr(record, "environment", "local"),
            "product_release": getattr(record, "product_release", "dev"),
            "logger": record.name,
            "event": getattr(record, "event", "application.log"),
            "message": record.getMessage(),
        }
        for field in (
            "trace_id", "request_id", "command_id", "task_id", "call_id",
            "duration_ms", "result_status", "error_code", "retryable",
            "capability", "mode", "round_no", "provider", "model",
            "validation_subtype", "validation_field", "validation_rule",
        ):
            item = getattr(record, field, None)
            if item is not None:
                payload[field] = item
        return json.dumps(redact_mapping(payload), ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
