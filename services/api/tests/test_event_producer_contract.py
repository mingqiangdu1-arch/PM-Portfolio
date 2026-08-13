from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.modules.sprint1.service import _outbox


class _CaptureConnection:
    def __init__(self) -> None:
        self.parameters: dict[str, Any] | None = None

    def execute(self, _statement: Any, parameters: dict[str, Any]) -> None:
        self.parameters = parameters


def _schema_directory() -> Path | None:
    configured = os.getenv("AI_EVENT_SCHEMA_DIR")
    candidates = [
        Path(configured) if configured else None,
        Path(__file__).parents[3] / "services" / "ai" / "schemas" / "v0.1",
        Path(__file__).parents[4] / "ai-data" / "services" / "ai" / "schemas" / "v0.1",
    ]
    return next((path for path in candidates if path and path.exists()), None)


class EventProducerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_dir = _schema_directory()
        if schema_dir is None:
            raise unittest.SkipTest("AI-owned Sprint 1 event schema is not present")
        envelope = json.loads((schema_dir / "event-envelope.schema.json").read_text(encoding="utf-8"))
        sprint1 = json.loads(
            (schema_dir / "sprint1-business-event.schema.json").read_text(encoding="utf-8")
        )
        registry = Registry().with_resources(
            [
                (envelope["$id"], Resource.from_contents(envelope)),
                ("event-envelope.schema.json", Resource.from_contents(envelope)),
            ]
        )
        cls.validator = Draft202012Validator(sprint1, registry=registry)

    def _produce(self, **overrides: Any) -> dict[str, Any]:
        connection = _CaptureConnection()
        values = {
            "aggregate_type": "project",
            "aggregate_id": 11,
            "aggregate_version": 1,
            "event_name": "project.project.created",
            "payload": {"initial_version_id": "12"},
            "trace_id": "trace-contract-test",
            "command_id": "cmd_contract_test",
            "module": "project",
            "user_id": 7,
            "project_id": 11,
            "project_version_id": None,
            "session_id": None,
            "result_status": "success",
            "failure_code": None,
        }
        values.update(overrides)
        with patch("app.modules.sprint1.service._sql", side_effect=lambda statement: statement):
            _outbox(connection, **values)
        assert connection.parameters is not None
        return json.loads(connection.parameters["payload"])

    def test_project_file_and_identity_producers_validate_against_ai_schema(self) -> None:
        events = [
            self._produce(),
            self._produce(
                aggregate_type="stored_file",
                event_name="file.upload.completed",
                module="file",
                payload={"file_version_id": "13", "checksum_sha256": "a" * 64},
                project_version_id=None,
            ),
            self._produce(
                aggregate_type="identity_attempt",
                aggregate_id=0,
                event_name="identity.session.login_failed",
                module="identity",
                payload={"producer_component": "business_api"},
                user_id=None,
                project_id=None,
                result_status="failed",
                failure_code="INVALID_CREDENTIALS",
            ),
        ]
        for event in events:
            with self.subTest(event_name=event["event_name"]):
                self.validator.validate(event)

    def test_producer_event_id_is_uuid_and_schema_version_is_frozen(self) -> None:
        event = self._produce()
        self.validator.validate(event)
        self.assertEqual(event["schema_version"], "0.1.3")
        self.assertEqual(len(event["event_id"]), 36)
