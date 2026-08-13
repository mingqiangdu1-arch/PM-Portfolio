import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "v0.1"


def schemas() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_DIR.glob("*.schema.json")
    }


def validator(name: str) -> Draft202012Validator:
    loaded = schemas()
    schema = loaded[name]
    registry = Registry().with_resources(
        (item["$id"], Resource.from_contents(item)) for item in loaded.values()
    )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def test_every_schema_is_valid_draft_2020_12() -> None:
    for schema in schemas().values():
        Draft202012Validator.check_schema(schema)


def test_examples_match_public_envelope_and_ai_outbox() -> None:
    events = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))
    envelope = validator("event-envelope.schema.json")
    outbox = validator("ai-outbox-event.schema.json")
    for event in events:
        envelope.validate(event)
        outbox.validate(event)


def test_sprint1_examples_match_business_event_schema() -> None:
    events = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))
    business_event = validator("sprint1-business-event.schema.json")
    for event in events:
        business_event.validate(event)


def test_sprint1_negative_required_fixture_is_rejected() -> None:
    cases = json.loads((ROOT / "examples" / "events" / "sprint1-invalid-events.json").read_text(encoding="utf-8"))["cases"]
    missing = cases[0]["event"]
    assert list(validator("sprint1-business-event.schema.json").iter_errors(missing))


def test_identity_schema_rejects_sensitive_payload_and_audit_projection() -> None:
    event = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))[0]
    event["payload_json"]["email"] = "must-not-be-recorded@example.invalid"
    assert list(validator("sprint1-business-event.schema.json").iter_errors(event))


def test_identity_login_failure_requires_failed_status_and_failure_code() -> None:
    event = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))[5]
    event["result_status"] = "success"
    event.pop("failure_code")
    assert list(validator("sprint1-business-event.schema.json").iter_errors(event))
    event["event_name"] = "audit.operation.recorded"
    event["module"] = "audit"
    assert list(validator("sprint1-business-event.schema.json").iter_errors(event))


def test_failed_public_event_requires_failure_code() -> None:
    event = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))[1]
    event["result_status"] = "failed"
    assert list(validator("event-envelope.schema.json").iter_errors(event))
    event["failure_code"] = "PROJECT_CREATE_FAILED"
    validator("event-envelope.schema.json").validate(event)


def test_sensitive_context_is_not_an_envelope_field() -> None:
    event = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))[0]
    event["ingested_at"] = "2026-07-29T09:00:01Z"
    errors = list(validator("event-envelope.schema.json").iter_errors(event))
    assert errors


def test_idempotency_hint_is_optional_but_event_id_is_required() -> None:
    event = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))[0]
    event.pop("idempotency_key")
    validator("event-envelope.schema.json").validate(event)
    event.pop("event_id")
    assert list(validator("event-envelope.schema.json").iter_errors(event))


def test_outbox_rejects_noncanonical_ai_event_name() -> None:
    event = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))[0]
    event["event_name"] = "ai.task.accepted"
    assert list(validator("ai-outbox-event.schema.json").iter_errors(event))


def test_compensation_is_approved_correction_not_delivery_retry() -> None:
    record = {
        "schema_version": "0.1.3",
        "original_event_id": "11111111-1111-4111-8111-111111111111",
        "compensation_event_id": "99999999-9999-4999-8999-999999999999",
        "compensation_type": "correct",
        "reason": "approved correction",
        "replacement_payload": {"result_status": "success", "task_status": "ready"},
        "approved_by": "9",
    }
    schema_validator = validator("event-compensation.schema.json")
    schema_validator.validate(record)
    record["attempt"] = 1
    assert list(schema_validator.iter_errors(record))


def test_audit_maps_existing_operation_audit_log_without_new_uuid() -> None:
    record = {
        "schema_version": "0.1.3",
        "actor_user_id": "9",
        "actor_type": "user",
        "operation_name": "ai.candidate.accepted",
        "object_type": "flow",
        "object_id": "3",
        "object_version_id": "4",
        "result_status": "success",
        "failure_code": None,
        "reason_summary": None,
        "trace_id": "trace-1",
        "command_id": "command-1",
        "occurred_at": "2026-07-29T09:00:00Z",
        "metadata_json": {},
    }
    schema_validator = validator("operation-audit.schema.json")
    schema_validator.validate(record)
    record["audit_id"] = "99999999-9999-4999-8999-999999999999"
    assert list(schema_validator.iter_errors(record))


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("result_status", "queued"),
        ("source_type", "ai_api"),
        ("privacy_class", "internal"),
    ],
)
def test_public_envelope_rejects_nonformal_enums(field, invalid_value) -> None:
    event = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))[0]
    event[field] = invalid_value
    assert list(validator("event-envelope.schema.json").iter_errors(event))


def test_public_envelope_rejects_module_longer_than_varchar_32() -> None:
    event = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))[0]
    event["module"] = "m" * 33
    assert list(validator("event-envelope.schema.json").iter_errors(event))


def test_call_and_result_events_require_non_null_relations() -> None:
    events = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))
    call_event = json.loads(json.dumps(events[0]))
    call_event["event_name"] = "ai.call.started"
    call_event["source_type"] = "worker"
    assert list(validator("ai-outbox-event.schema.json").iter_errors(call_event))
    call_event["ai_call_id"] = "6"
    validator("ai-outbox-event.schema.json").validate(call_event)

    result_event = events[1]
    result_event["ai_result_id"] = None
    assert list(validator("ai-outbox-event.schema.json").iter_errors(result_event))


def test_task_event_requires_task_status_inside_payload() -> None:
    event = json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))[0]
    event["payload_json"].pop("task_status")
    assert list(validator("ai-outbox-event.schema.json").iter_errors(event))


def test_objectless_system_audit_and_null_metadata_are_valid() -> None:
    record = {
        "schema_version": "0.1.3",
        "actor_user_id": None,
        "actor_type": "system",
        "operation_name": "system.health.checked",
        "object_type": "health_check",
        "object_id": None,
        "object_version_id": None,
        "result_status": "success",
        "failure_code": None,
        "reason_summary": None,
        "trace_id": "trace-1",
        "command_id": "command-1",
        "occurred_at": "2026-07-29T09:00:00Z",
        "metadata_json": None,
    }
    validator("operation-audit.schema.json").validate(record)

    record["object_type"] = None
    assert list(validator("operation-audit.schema.json").iter_errors(record))


def test_compensation_allows_null_replacement_payload() -> None:
    record = {
        "schema_version": "0.1.3",
        "original_event_id": "11111111-1111-4111-8111-111111111111",
        "compensation_event_id": "99999999-9999-4999-8999-999999999999",
        "compensation_type": "redact",
        "reason": "approved removal",
        "replacement_payload": None,
        "approved_by": "9",
    }
    validator("event-compensation.schema.json").validate(record)


def test_context_persistence_schema_rejects_unconfirmed_runtime_fields() -> None:
    record = {
        "schema_version": "0.1.3",
        "ai_call_id": "6",
        "sequence_no": 1,
        "source_type": "formal_document",
        "source_id": "7",
        "retrieval_method": "direct",
        "was_injected": True,
        "content_fingerprint": "a" * 64,
        "source_role": "authoritative",
    }
    assert list(validator("ai-context-usage.schema.json").iter_errors(record))
