"""Deterministic event-quality checks independent of storage implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
import re

REQUIRED_ENVELOPE_FIELDS = {
    "schema_version",
    "event_id",
    "event_name",
    "occurred_at",
    "module",
    "result_status",
    "source_type",
    "privacy_class",
    "payload_json",
}

RESULT_STATUSES = {"success", "failed", "partial", "cancelled", "blocked", "expired"}
SOURCE_TYPES = {"server", "ai_service", "web", "worker", "import", "system"}
PRIVACY_CLASSES = {"internal_id", "pseudonymous", "confidential", "restricted"}
TASK_STATUSES = {
    "prechecking", "blocked", "queued", "preparing", "generating", "checking",
    "ready", "partial_result", "quality_blocked", "cancel_requested", "cancelled",
    "failed", "expired", "stale_target",
}
SENSITIVE_EVENT_KEY = re.compile(
    r"^(?:email|password|access_token|refresh_token|token|cookie|ip|user_agent|ua)$",
    re.IGNORECASE,
)


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            SENSITIVE_EVENT_KEY.match(str(key)) or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


@dataclass(frozen=True)
class EventQualityIssue:
    event_index: int
    event_id: str | None
    failure_class: str
    detail: str


@dataclass
class EventQualityReport:
    inspected: int = 0
    accepted: int = 0
    duplicates: int = 0
    missing_required: int = 0
    association_failed: int = 0
    remediation_required: int = 0
    issues: list[EventQualityIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


def inspect_events(
    events: Iterable[dict[str, Any]],
    *,
    known_task_ids: set[str] | None = None,
    known_ids: dict[str, set[str]] | None = None,
    now: datetime | None = None,
) -> EventQualityReport:
    """Check duplicate, completeness, association, and compensation signals.

    This does not query the business database. The caller supplies the set of
    known task identifiers from an approved, read-only source.
    """

    report = EventQualityReport()
    seen_event_ids: set[str] = set()
    known_ids = dict(known_ids or {})
    if known_task_ids is not None:
        known_ids["ai_task_id"] = known_task_ids
    current_time = now

    for index, event in enumerate(events):
        report.inspected += 1
        event_id = event.get("event_id")
        event_name = str(event.get("event_name", ""))
        event_issues = 0

        missing = sorted(REQUIRED_ENVELOPE_FIELDS - event.keys())
        if missing:
            report.missing_required += 1
            event_issues += 1
            report.issues.append(
                EventQualityIssue(index, event_id, "missing_required", ",".join(missing))
            )

        for field_name in REQUIRED_ENVELOPE_FIELDS & event.keys():
            if event[field_name] is None or event[field_name] == "":
                report.missing_required += 1
                event_issues += 1
                report.issues.append(EventQualityIssue(index, event_id, "missing_required", field_name))

        if event.get("result_status") == "failed" and not event.get("failure_code"):
            event_issues += 1
            report.issues.append(EventQualityIssue(index, event_id, "missing_required", "failure_code"))

        if (event_name.endswith("_failed") or event_name.endswith(".failed")) and event.get("result_status") != "failed":
            event_issues += 1
            report.issues.append(EventQualityIssue(index, event_id, "invalid_event_outcome", "failed event name requires result_status=failed"))
        if event_name == "identity.session.refresh_replay_blocked" and (
            event.get("result_status") != "blocked" or not event.get("failure_code")
        ):
            event_issues += 1
            report.issues.append(EventQualityIssue(index, event_id, "invalid_event_outcome", "refresh replay block requires blocked status and failure_code"))

        if event_name.startswith(("identity.", "project.", "file.")):
            for field_name in ("trace_id", "command_id"):
                if not event.get(field_name):
                    report.missing_required += 1
                    event_issues += 1
                    report.issues.append(EventQualityIssue(index, event_id, "missing_required", field_name))

        if event_name.startswith("identity.") and _contains_sensitive_key(event.get("payload_json", {})):
            event_issues += 1
            report.issues.append(
                EventQualityIssue(index, event_id, "sensitive_payload", "identity payload contains a forbidden sensitive field")
            )

        occurred_at = event.get("occurred_at")
        if isinstance(occurred_at, str) and current_time is not None:
            try:
                parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
                if parsed > current_time + timedelta(minutes=5):
                    event_issues += 1
                    report.issues.append(EventQualityIssue(index, event_id, "invalid_time", "occurred_at is in the future"))
            except ValueError:
                event_issues += 1
                report.issues.append(EventQualityIssue(index, event_id, "invalid_time", "occurred_at is not RFC3339"))

        classifications = (
            ("result_status", RESULT_STATUSES),
            ("source_type", SOURCE_TYPES),
            ("privacy_class", PRIVACY_CLASSES),
        )
        for field_name, allowed in classifications:
            if field_name in event and event[field_name] not in allowed:
                event_issues += 1
                report.issues.append(
                    EventQualityIssue(index, event_id, "invalid_enum", field_name)
                )

        if event_name.startswith("ai.task."):
            task_status = event.get("payload_json", {}).get("task_status")
            if task_status not in TASK_STATUSES:
                event_issues += 1
                report.issues.append(
                    EventQualityIssue(index, event_id, "missing_or_invalid_task_status", "payload_json.task_status")
                )

        if event_id and event_id in seen_event_ids:
            report.duplicates += 1
            event_issues += 1
            report.issues.append(
                EventQualityIssue(index, event_id, "duplicate", "event_id already seen")
            )
        elif event_id:
            seen_event_ids.add(event_id)

        relation_values = {
            "user_id": event.get("user_id"),
            "project_id": event.get("project_id"),
            "project_version_id": event.get("project_version_id"),
            "file_version_id": event.get("payload_json", {}).get("file_version_id"),
            "ai_task_id": event.get("ai_task_id"),
        }
        for relation_name, relation_value in relation_values.items():
            authoritative_ids = known_ids.get(relation_name)
            if relation_value is not None and authoritative_ids is not None and relation_value not in authoritative_ids:
                report.association_failed += 1
                event_issues += 1
                report.issues.append(
                    EventQualityIssue(index, event_id, "association_failed", f"{relation_name} is absent from the supplied authoritative set")
                )

        if event_issues:
            report.remediation_required += 1
        else:
            report.accepted += 1

    return report


@dataclass
class CompensationQualityReport:
    inspected: int = 0
    accepted: int = 0
    rejected: int = 0
    issues: list[EventQualityIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


def inspect_compensations(
    records: Iterable[dict[str, Any]],
    *,
    known_event_ids: set[str],
) -> CompensationQualityReport:
    """Check approved correction records without mutating historical events."""

    report = CompensationQualityReport()
    seen_compensation_ids: set[str] = set()
    for index, record in enumerate(records):
        report.inspected += 1
        compensation_id = record.get("compensation_event_id")
        original_id = record.get("original_event_id")
        issue_count = 0
        if original_id not in known_event_ids:
            issue_count += 1
            report.issues.append(
                EventQualityIssue(index, compensation_id, "association_failed", "original_event_id is unknown")
            )
        if compensation_id in seen_compensation_ids:
            issue_count += 1
            report.issues.append(
                EventQualityIssue(index, compensation_id, "duplicate", "compensation_event_id already seen")
            )
        elif compensation_id:
            seen_compensation_ids.add(compensation_id)
        if not record.get("approved_by"):
            issue_count += 1
            report.issues.append(
                EventQualityIssue(index, compensation_id, "missing_required", "approved_by is required")
            )
        if issue_count:
            report.rejected += 1
        else:
            report.accepted += 1
    return report
