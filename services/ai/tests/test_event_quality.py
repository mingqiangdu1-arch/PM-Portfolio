import json
from datetime import UTC, datetime
from pathlib import Path

from app.data_quality import inspect_compensations, inspect_events

ROOT = Path(__file__).resolve().parents[1]


def valid_events() -> list[dict]:
    return json.loads((ROOT / "examples" / "events" / "valid-events.json").read_text(encoding="utf-8"))


def test_valid_events_pass_with_authoritative_task_relation() -> None:
    events = valid_events()
    report = inspect_events(events, known_task_ids={events[0]["ai_task_id"]})
    assert report.passed
    assert report.accepted == 2


def test_duplicate_missing_and_relation_failures_require_compensation() -> None:
    events = valid_events()
    duplicate = dict(events[0])
    missing = {"event_id": "66666666-6666-4666-8666-666666666666", "payload_json": {}}
    orphan = json.loads(json.dumps(events[1]))
    orphan["event_id"] = "77777777-7777-4777-8777-777777777777"
    orphan["ai_task_id"] = "888"
    report = inspect_events(
        [events[0], duplicate, missing, orphan],
        known_task_ids={events[0]["ai_task_id"]},
    )
    assert report.duplicates == 1
    assert report.missing_required == 1
    assert report.association_failed == 1
    assert report.remediation_required == 3


def test_approved_compensation_links_without_rewriting_original_event() -> None:
    original_event_id = valid_events()[0]["event_id"]
    record = {
        "schema_version": "0.1.3",
        "original_event_id": original_event_id,
        "compensation_event_id": "99999999-9999-4999-8999-999999999999",
        "compensation_type": "correct",
        "reason": "approved fixture correction",
        "replacement_payload": {"result_status": "success", "task_status": "queued"},
        "approved_by": "9",
    }
    report = inspect_compensations([record], known_event_ids={original_event_id})
    assert report.passed
    assert report.accepted == 1


def test_compensation_rejects_unknown_original_duplicate_and_missing_approval() -> None:
    record = {
        "original_event_id": "00000000-0000-4000-8000-000000000000",
        "compensation_event_id": "99999999-9999-4999-8999-999999999999",
        "approved_by": "",
    }
    report = inspect_compensations([record, record], known_event_ids=set())
    failure_classes = {issue.failure_class for issue in report.issues}
    assert failure_classes == {"association_failed", "duplicate", "missing_required"}
    assert report.rejected == 2


def test_task_status_is_nested_and_public_enums_are_strict() -> None:
    event = valid_events()[0]
    event["result_status"] = "queued"
    event["payload_json"].pop("task_status")
    report = inspect_events([event], known_task_ids={event["ai_task_id"]})
    assert {issue.failure_class for issue in report.issues} == {
        "invalid_enum",
        "missing_or_invalid_task_status",
    }


def test_sprint1_events_pass_all_authoritative_relations() -> None:
    events = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))
    report = inspect_events(
        events,
        known_ids={
            "user_id": {"10"},
            "project_id": {"20"},
            "project_version_id": {"21", "22"},
            "file_version_id": {"31"},
        },
        now=datetime(2026, 7, 29, 11, 0, tzinfo=UTC),
    )
    assert report.passed
    assert report.accepted == 10


def test_sprint1_duplicate_missing_and_orphan_events_are_unusable() -> None:
    events = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))
    duplicate = json.loads(json.dumps(events[1]))
    orphan = json.loads(json.dumps(events[3]))
    orphan["event_id"] = "10200000-0000-4000-8000-000000000002"
    missing = json.loads(json.dumps(events[2]))
    missing["event_id"] = "10200000-0000-4000-8000-000000000003"
    missing["trace_id"] = ""
    report = inspect_events(
        [events[1], duplicate, orphan, missing],
        known_ids={
            "user_id": {"10"},
            "project_id": {"20"},
            "project_version_id": {"21", "22"},
            "file_version_id": set(),
        },
        now=datetime(2026, 7, 29, 11, 0, tzinfo=UTC),
    )
    assert report.duplicates == 1
    assert report.association_failed == 1
    assert any(issue.failure_class == "missing_required" and issue.detail == "trace_id" for issue in report.issues)
    assert report.accepted == 1


def test_identity_event_rejects_sensitive_payload_at_any_depth() -> None:
    event = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))[0]
    event["payload_json"]["details"] = {"email": "must-not-be-recorded@example.invalid"}
    report = inspect_events([event], known_ids={"user_id": {"10"}})
    assert any(issue.failure_class == "sensitive_payload" for issue in report.issues)


def test_identity_failure_name_requires_failed_outcome_and_failure_code() -> None:
    event = json.loads((ROOT / "examples" / "events" / "sprint1-valid-events.json").read_text(encoding="utf-8"))[5]
    event["result_status"] = "success"
    event.pop("failure_code")
    report = inspect_events([event])
    assert any(issue.failure_class == "invalid_event_outcome" for issue in report.issues)
