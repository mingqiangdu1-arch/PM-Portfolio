import json
import logging

import pytest

from app.core.config import Settings
from app.core.logging import JsonFormatter, redact_mapping


def test_flow_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FLOW_ENABLED", raising=False)
    monkeypatch.delenv("AI_ENVIRONMENT", raising=False)
    assert Settings.from_env().flow_enabled is False


def test_production_rejects_stub_modes(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENVIRONMENT", "production")
    monkeypatch.setenv("AI_PROVIDER_MODE", "stub")
    monkeypatch.setenv("AI_CONTEXT_MODE", "business_api")
    with pytest.raises(ValueError, match="production cannot start"):
        Settings.from_env()


def test_ci_rejects_non_stub_provider(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENVIRONMENT", "ci")
    monkeypatch.setenv("AI_PROVIDER_MODE", "openai_compatible")
    monkeypatch.setenv("AI_CONTEXT_MODE", "stub")
    with pytest.raises(ValueError, match="CI must use Provider Stub"):
        Settings.from_env()


def test_secret_keys_are_redacted_recursively() -> None:
    assert redact_mapping({"api_key": "secret", "nested": {"password": "secret"}}) == {
        "api_key": "[REDACTED]",
        "nested": {"password": "[REDACTED]"},
    }


def test_formatter_uses_trace_fields_without_secrets() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "done", (), None)
    record.trace_id = "trace-1"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["trace_id"] == "trace-1"
    assert "secret" not in payload
