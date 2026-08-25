"""MVP5 Test Record validation conclusion and unified Issue commands."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError

from app.modules.confirmation.service import (
    _access,
    _canonical,
    _expected,
    _id,
    _idem_begin,
    _idem_complete,
    _iso,
    _json,
    _map_database_error,
    _mapping,
    _normal,
    _now,
    _persist_command,
    _read_access,
    _snapshot_replay,
    _sql,
    _test_record,
    _test_record_identity,
    _write_role,
)
from app.platform.database import readonly, transaction
from app.platform.errors import ApiError


ISSUE_TYPES = {"defect", "feedback", "data_anomaly", "optimization"}
PRIORITIES = {"low", "medium", "high", "urgent"}
SEVERITIES = {"low", "medium", "high", "critical"}
DISPOSITIONS = {"current_version_fix", "derive_new_version", "defer", "reject"}
TERMINAL_STATUS = {
    "current_version_fix": "routed_current_fix",
    "derive_new_version": "routed_new_version",
    "defer": "deferred",
    "reject": "rejected",
}


def _text(value: Any, field: str, maximum: int = 12000) -> str:
    value = _normal(value, field)
    if len(value) > maximum:
        raise ApiError("VALIDATION_ERROR", f"{field} is too long", 422)
    return value


def _nullable_id(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _id(value, field)


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ApiError("VALIDATION_ERROR", f"{field} is invalid", 422)
    return value


def _bug_detail(value: Any) -> dict[str, Any]:
    fields = {"reproduce_steps", "expected_result", "actual_result", "environment"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ApiError("VALIDATION_ERROR", "bug_detail fields are invalid", 422)
    environment = value["environment"]
    if environment is not None and not isinstance(environment, dict):
        raise ApiError("VALIDATION_ERROR", "bug_detail.environment must be an object or null", 422)
    return {
        "reproduce_steps": _text(value["reproduce_steps"], "bug_detail.reproduce_steps"),
        "expected_result": _text(value["expected_result"], "bug_detail.expected_result"),
        "actual_result": _text(value["actual_result"], "bug_detail.actual_result"),
        "environment": environment,
    }


def _optimization_detail(value: Any) -> dict[str, Any]:
    fields = {
        "problem_evidence",
        "hypothesis",
        "expected_outcome",
        "impact_scope",
        "need_new_version",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ApiError("VALIDATION_ERROR", "optimization_detail fields are invalid", 422)
    if not isinstance(value["need_new_version"], bool):
        raise ApiError("VALIDATION_ERROR", "need_new_version must be boolean", 422)
    return {
        "problem_evidence": _text(value["problem_evidence"], "optimization_detail.problem_evidence"),
        "hypothesis": _text(value["hypothesis"], "optimization_detail.hypothesis"),
        "expected_outcome": _text(value["expected_outcome"], "optimization_detail.expected_outcome"),
        "impact_scope": _text(value["impact_scope"], "optimization_detail.impact_scope"),
        "need_new_version": value["need_new_version"],
    }


def _classification(issue_type: str, bug: Any, optimization: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if issue_type == "defect":
        if bug is None or optimization is not None:
            raise ApiError("VALIDATION_ERROR", "defect requires only bug_detail", 422)
        return _bug_detail(bug), None
    if issue_type == "optimization":
        if optimization is None or bug is not None:
            raise ApiError("VALIDATION_ERROR", "optimization requires only optimization_detail", 422)
        return None, _optimization_detail(optimization)
    if bug is not None or optimization is not None:
        raise ApiError("VALIDATION_ERROR", "feedback and data_anomaly do not accept extension details", 422)
    return None, None


def _issue_identity(connection: Any, issue_id: int, *, lock: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock else ""
    row = _mapping(
        connection.execute(
            _sql(
                "SELECT i.*,v.project_id FROM issue i "
                "JOIN project_version v ON v.id=i.project_version_id "
                "WHERE i.id=:id AND i.archived_at IS NULL AND v.archived_at IS NULL" + suffix
            ),
            {"id": issue_id},
        )
    )
    if not row:
        raise ApiError("NOT_FOUND", "Issue was not found", 404)
    return row


def _member_guard(connection: Any, *, project_id: int, user_id: int | None) -> None:
    if user_id is None:
        return
    exists = connection.execute(
        _sql(
            "SELECT COUNT(*) FROM project_member WHERE project_id=:pid AND user_id=:uid "
            "AND status='active'"
        ),
        {"pid": project_id, "uid": user_id},
    ).scalar_one()
    if int(exists) != 1:
        raise ApiError("VALIDATION_ERROR", "user must be an active project member", 422)


def _issue(connection: Any, row: dict[str, Any]) -> dict[str, Any]:
    bug = _mapping(connection.execute(_sql("SELECT * FROM bug_detail WHERE issue_id=:id"), {"id": row["id"]}))
    optimization = _mapping(
        connection.execute(_sql("SELECT * FROM optimization_detail WHERE issue_id=:id"), {"id": row["id"]})
    )
    dispositions = (
        connection.execute(
            _sql("SELECT * FROM issue_disposition WHERE issue_id=:id ORDER BY sequence_no,id"),
            {"id": row["id"]},
        )
        .mappings()
        .all()
    )
    return {
        "id": str(row["id"]),
        "project_version_id": str(row["project_version_id"]),
        "test_record_id": str(row["test_record_id"]) if row.get("test_record_id") else None,
        "source_type": row["source_type"],
        "issue_type": row["issue_type"],
        "title": row["title"],
        "description": row["description"],
        "priority": row["priority"],
        "severity": row["severity"],
        "status": row["status"],
        "assignee_id": str(row["assignee_id"]) if row.get("assignee_id") else None,
        "row_version": int(row["row_version"]),
        "bug_detail": (
            {
                "reproduce_steps": bug["reproduce_steps"],
                "expected_result": bug["expected_result"],
                "actual_result": bug["actual_result"],
                "environment": _json(bug["environment_json"]) if bug["environment_json"] else None,
            }
            if bug
            else None
        ),
        "optimization_detail": (
            {
                "problem_evidence": optimization["problem_evidence"],
                "hypothesis": optimization["hypothesis"],
                "expected_outcome": optimization["expected_outcome"],
                "impact_scope": optimization["impact_scope"],
                "need_new_version": bool(optimization["need_new_version"]),
            }
            if optimization
            else None
        ),
        "dispositions": [
            {
                "id": str(item["id"]),
                "sequence_no": int(item["sequence_no"]),
                "disposition_type": item["disposition_type"],
                "reason": item["reason"],
                "target_project_version_id": (
                    str(item["target_project_version_id"]) if item["target_project_version_id"] else None
                ),
                "responsible_user_id": str(item["responsible_user_id"]),
                "decided_by": str(item["decided_by"]),
                "decided_at": _iso(item["decided_at"]),
            }
            for item in dispositions
        ],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _persist_issue_command(
    connection: Any,
    *,
    row: dict[str, Any],
    user_id: int,
    trace_id: str,
    operation: str,
    event_name: str,
) -> int:
    response = {"issue": _issue(connection, row)}
    return _persist_command(
        connection,
        actor_user_id=user_id,
        operation=operation,
        object_type="issue",
        object_id=int(row["id"]),
        object_version_id=int(row["row_version"]),
        trace_id=trace_id,
        command_id=f"cmd_{uuid.uuid4().hex}",
        response_data=response,
        aggregate_type="issue",
        aggregate_version=int(row["row_version"]),
        event_name=event_name,
        event_payload={"schema_version": "validation_feedback.mvp5.v1", "status": row["status"]},
        project_id=int(row["project_id"]),
        project_version_id=int(row["project_version_id"]),
    )


class ValidationService:
    def conclude_no_issue(
        self, *, record_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) != {"expected_version"}:
            raise ApiError("VALIDATION_ERROR", "ConcludeNoIssue request fields are invalid", 422)
        expected = _expected(payload["expected_version"])
        record_id = _id(record_id, "id")
        endpoint = f"concludeTestRecordNoIssue:/api/v1/test-records/{record_id}:conclude-no-issue"
        try:
            with transaction() as connection:
                identity = _test_record_identity(connection, record_id)
                roles = _access(
                    connection,
                    project_id=int(identity["project_id"]),
                    user_id=user_id,
                    allowed={"owner", "tester"},
                    lock=True,
                )
                replay = _idem_begin(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    payload={"expected_version": expected},
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                row = _test_record_identity(connection, record_id, lock=True)
                if row["submitted_at"] is None:
                    raise ApiError("TEST_RECORD_NOT_SUBMITTED", "Test Record must be submitted first", 409)
                if bool(row["no_issue_conclusion"]):
                    raise ApiError("VALIDATION_ALREADY_CONCLUDED", "Validation is already complete", 409)
                if int(row["row_version"]) != expected:
                    raise ApiError("VERSION_CONFLICT", "Test Record has changed", 409)
                issue_count = connection.execute(
                    _sql("SELECT COUNT(*) FROM issue WHERE test_record_id=:id AND archived_at IS NULL"),
                    {"id": record_id},
                ).scalar_one()
                if int(issue_count):
                    raise ApiError("TEST_RECORD_HAS_ISSUES", "Test Record already has Issue records", 409)
                now = _now()
                connection.execute(
                    _sql(
                        "UPDATE test_record SET no_issue_conclusion=1,row_version=row_version+1,"
                        "updated_at=:now,updated_by=:uid WHERE id=:id"
                    ),
                    {"now": now, "uid": user_id, "id": record_id},
                )
                updated = _test_record_identity(connection, record_id, lock=True)
                response = {"test_record": _test_record(updated)}
                audit_id = _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="test.record.validation_completed",
                    object_type="test_record",
                    object_id=record_id,
                    object_version_id=int(updated["row_version"]),
                    trace_id=trace_id,
                    command_id=f"cmd_{uuid.uuid4().hex}",
                    response_data=response,
                    audit_metadata={
                        "schema_version": "validation_feedback.mvp5.audit.v1",
                        "response_data": response,
                        "actual_role": _write_role(roles),
                    },
                    aggregate_type="test_record",
                    aggregate_version=int(updated["row_version"]),
                    event_name="test.record.validation_completed",
                    event_payload={"schema_version": "validation_feedback.mvp5.v1", "no_issue": True},
                    project_id=int(updated["project_id"]),
                    project_version_id=int(updated["project_version_id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return response
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def list_issues(
        self, *, version_id: int, user_id: int, cursor: str | None, page_size: int
    ) -> dict[str, Any]:
        version_id = _id(version_id, "version_id")
        if not 1 <= page_size <= 100:
            raise ApiError("VALIDATION_ERROR", "page_size must be between 1 and 100", 422)
        cursor_id = _id(cursor, "cursor") if cursor else None
        with readonly() as connection:
            version = _mapping(
                connection.execute(
                    _sql("SELECT id,project_id FROM project_version WHERE id=:id AND archived_at IS NULL"),
                    {"id": version_id},
                )
            )
            if not version:
                raise ApiError("NOT_FOUND", "Project version was not found", 404)
            _read_access(connection, project_id=int(version["project_id"]), user_id=user_id)
            rows = (
                connection.execute(
                    _sql(
                        "SELECT i.*,v.project_id FROM issue i JOIN project_version v ON v.id=i.project_version_id "
                        "WHERE i.project_version_id=:version_id AND i.archived_at IS NULL "
                        "AND (:cursor IS NULL OR i.id<:cursor) ORDER BY i.id DESC LIMIT :limit"
                    ),
                    {"version_id": version_id, "cursor": cursor_id, "limit": page_size + 1},
                )
                .mappings()
                .all()
            )
            has_more = len(rows) > page_size
            visible = [dict(row) for row in rows[:page_size]]
            return {
                "items": [_issue(connection, row) for row in visible],
                "next_cursor": str(visible[-1]["id"]) if has_more and visible else None,
                "has_more": has_more,
            }

    def create_issue(
        self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        fields = {
            "test_record_id",
            "issue_type",
            "title",
            "description",
            "priority",
            "severity",
            "assignee_id",
            "bug_detail",
            "optimization_detail",
        }
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ApiError("VALIDATION_ERROR", "CreateIssue request fields are invalid", 422)
        version_id = _id(version_id, "version_id")
        issue_type = _enum(payload["issue_type"], "issue_type", ISSUE_TYPES)
        bug, optimization = _classification(
            issue_type, payload["bug_detail"], payload["optimization_detail"]
        )
        request = {
            "test_record_id": _id(payload["test_record_id"], "test_record_id"),
            "issue_type": issue_type,
            "title": _text(payload["title"], "title", 200),
            "description": _text(payload["description"], "description"),
            "priority": _enum(payload["priority"], "priority", PRIORITIES),
            "severity": _enum(payload["severity"], "severity", SEVERITIES),
            "assignee_id": _nullable_id(payload["assignee_id"], "assignee_id"),
            "bug_detail": bug,
            "optimization_detail": optimization,
        }
        endpoint = f"createProjectVersionIssue:/api/v1/project-versions/{version_id}/issues"
        try:
            with transaction() as connection:
                version = _mapping(
                    connection.execute(
                        _sql("SELECT id,project_id FROM project_version WHERE id=:id AND archived_at IS NULL FOR UPDATE"),
                        {"id": version_id},
                    )
                )
                if not version:
                    raise ApiError("NOT_FOUND", "Project version was not found", 404)
                _access(
                    connection,
                    project_id=int(version["project_id"]),
                    user_id=user_id,
                    allowed={"owner", "tester"},
                    lock=True,
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                record = _test_record_identity(connection, request["test_record_id"], lock=True)
                if int(record["project_version_id"]) != version_id:
                    raise ApiError("ISSUE_VALIDATION_CONFLICT", "Test Record belongs to another Project Version", 409)
                if record["submitted_at"] is None:
                    raise ApiError("TEST_RECORD_NOT_SUBMITTED", "Test Record must be submitted first", 409)
                if bool(record["no_issue_conclusion"]):
                    raise ApiError("ISSUE_VALIDATION_CONFLICT", "No-Issue conclusion already completed validation", 409)
                _member_guard(
                    connection,
                    project_id=int(version["project_id"]),
                    user_id=request["assignee_id"],
                )
                now = _now()
                result = connection.execute(
                    _sql(
                        "INSERT INTO issue (created_at,created_by,updated_at,updated_by,row_version,"
                        "archived_at,archived_by,project_version_id,test_record_id,source_type,issue_type,"
                        "title,description,priority,severity,status,assignee_id) VALUES "
                        "(:now,:uid,:now,:uid,1,NULL,NULL,:version_id,:test_id,'test_record',:issue_type,"
                        ":title,:description,:priority,:severity,'open_needs_disposition',:assignee_id)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "version_id": version_id,
                        "test_id": request["test_record_id"],
                        "issue_type": issue_type,
                        "title": request["title"],
                        "description": request["description"],
                        "priority": request["priority"],
                        "severity": request["severity"],
                        "assignee_id": request["assignee_id"],
                    },
                )
                issue_id = int(result.lastrowid)
                self._replace_detail(connection, issue_id=issue_id, user_id=user_id, bug=bug, optimization=optimization)
                row = _issue_identity(connection, issue_id, lock=True)
                response = {"issue": _issue(connection, row)}
                audit_id = _persist_issue_command(
                    connection,
                    row=row,
                    user_id=user_id,
                    trace_id=trace_id,
                    operation="issue.created",
                    event_name="issue.created",
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return response
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def get_issue(self, *, issue_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            row = _issue_identity(connection, _id(issue_id, "issue_id"))
            _read_access(connection, project_id=int(row["project_id"]), user_id=user_id)
            return {"issue": _issue(connection, row)}

    def update_issue(
        self, *, issue_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        allowed = {
            "expected_version",
            "title",
            "description",
            "priority",
            "severity",
            "assignee_id",
            "bug_detail",
            "optimization_detail",
        }
        if not isinstance(payload, dict) or "expected_version" not in payload or not set(payload).issubset(allowed):
            raise ApiError("VALIDATION_ERROR", "UpdateIssue request fields are invalid", 422)
        expected = _expected(payload["expected_version"])
        issue_id = _id(issue_id, "issue_id")
        endpoint = f"updateIssue:/api/v1/issues/{issue_id}"
        try:
            with transaction() as connection:
                identity = _issue_identity(connection, issue_id)
                _access(
                    connection,
                    project_id=int(identity["project_id"]),
                    user_id=user_id,
                    allowed={"owner", "tester"},
                    lock=True,
                )
                replay = _idem_begin(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    payload=payload,
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                row = _issue_identity(connection, issue_id, lock=True)
                if row["status"] != "open_needs_disposition":
                    raise ApiError("ISSUE_NOT_OPEN", "Only an open Issue can be edited", 409)
                if int(row["row_version"]) != expected:
                    raise ApiError("VERSION_CONFLICT", "Issue has changed", 409)
                updates: dict[str, Any] = {}
                if "title" in payload:
                    updates["title"] = _text(payload["title"], "title", 200)
                if "description" in payload:
                    updates["description"] = _text(payload["description"], "description")
                if "priority" in payload:
                    updates["priority"] = _enum(payload["priority"], "priority", PRIORITIES)
                if "severity" in payload:
                    updates["severity"] = _enum(payload["severity"], "severity", SEVERITIES)
                if "assignee_id" in payload:
                    updates["assignee_id"] = _nullable_id(payload["assignee_id"], "assignee_id")
                    _member_guard(
                        connection,
                        project_id=int(row["project_id"]),
                        user_id=updates["assignee_id"],
                    )
                current_bug = _issue(connection, row)["bug_detail"]
                current_optimization = _issue(connection, row)["optimization_detail"]
                bug_raw = payload.get("bug_detail", current_bug)
                optimization_raw = payload.get("optimization_detail", current_optimization)
                bug, optimization = _classification(row["issue_type"], bug_raw, optimization_raw)
                if not updates and "bug_detail" not in payload and "optimization_detail" not in payload:
                    raise ApiError("VALIDATION_ERROR", "UpdateIssue has no changes", 422)
                assignments = [f"{field}=:{field}" for field in updates]
                assignments.extend(["row_version=row_version+1", "updated_at=:now", "updated_by=:uid"])
                connection.execute(
                    _sql(f"UPDATE issue SET {','.join(assignments)} WHERE id=:id"),
                    {**updates, "now": _now(), "uid": user_id, "id": issue_id},
                )
                if "bug_detail" in payload or "optimization_detail" in payload:
                    self._replace_detail(connection, issue_id=issue_id, user_id=user_id, bug=bug, optimization=optimization)
                updated = _issue_identity(connection, issue_id, lock=True)
                audit_id = _persist_issue_command(
                    connection,
                    row=updated,
                    user_id=user_id,
                    trace_id=trace_id,
                    operation="issue.updated",
                    event_name="issue.updated",
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return {"issue": _issue(connection, updated)}
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def create_disposition(
        self, *, issue_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        fields = {"expected_version", "disposition_type", "reason", "responsible_user_id"}
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ApiError("VALIDATION_ERROR", "IssueDisposition request fields are invalid", 422)
        expected = _expected(payload["expected_version"])
        disposition = _enum(payload["disposition_type"], "disposition_type", DISPOSITIONS)
        if disposition == "derive_new_version":
            raise ApiError(
                "ISSUE_VALIDATION_CONFLICT",
                "derive_new_version must use the atomic project version derive command",
                409,
            )
        request = {
            "expected_version": expected,
            "disposition_type": disposition,
            "reason": _text(payload["reason"], "reason"),
            "responsible_user_id": _id(payload["responsible_user_id"], "responsible_user_id"),
        }
        issue_id = _id(issue_id, "issue_id")
        endpoint = f"createIssueDisposition:/api/v1/issues/{issue_id}/dispositions"
        try:
            with transaction() as connection:
                identity = _issue_identity(connection, issue_id)
                _access(
                    connection,
                    project_id=int(identity["project_id"]),
                    user_id=user_id,
                    allowed={"owner"},
                    lock=True,
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                row = _issue_identity(connection, issue_id, lock=True)
                if row["status"] != "open_needs_disposition":
                    raise ApiError("ISSUE_NOT_OPEN", "Issue already has a final disposition", 409)
                if int(row["row_version"]) != expected:
                    raise ApiError("VERSION_CONFLICT", "Issue has changed", 409)
                _member_guard(
                    connection,
                    project_id=int(row["project_id"]),
                    user_id=request["responsible_user_id"],
                )
                sequence = int(
                    connection.execute(
                        _sql("SELECT COALESCE(MAX(sequence_no),0)+1 FROM issue_disposition WHERE issue_id=:id"),
                        {"id": issue_id},
                    ).scalar_one()
                )
                now = _now()
                connection.execute(
                    _sql(
                        "INSERT INTO issue_disposition "
                        "(created_at,created_by,issue_id,sequence_no,disposition_type,reason,"
                        "target_project_version_id,responsible_user_id,decided_by,decided_at) "
                        "VALUES (:now,:uid,:issue_id,:sequence,:kind,:reason,NULL,:responsible,:uid,:now)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "issue_id": issue_id,
                        "sequence": sequence,
                        "kind": disposition,
                        "reason": request["reason"],
                        "responsible": request["responsible_user_id"],
                    },
                )
                connection.execute(
                    _sql(
                        "UPDATE issue SET status=:status,row_version=row_version+1,updated_at=:now,"
                        "updated_by=:uid WHERE id=:id"
                    ),
                    {"status": TERMINAL_STATUS[disposition], "now": now, "uid": user_id, "id": issue_id},
                )
                updated = _issue_identity(connection, issue_id, lock=True)
                audit_id = _persist_issue_command(
                    connection,
                    row=updated,
                    user_id=user_id,
                    trace_id=trace_id,
                    operation="issue.disposition.created",
                    event_name="issue.disposition.created",
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return {"issue": _issue(connection, updated)}
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    @staticmethod
    def _replace_detail(
        connection: Any,
        *,
        issue_id: int,
        user_id: int,
        bug: dict[str, Any] | None,
        optimization: dict[str, Any] | None,
    ) -> None:
        connection.execute(_sql("DELETE FROM bug_detail WHERE issue_id=:id"), {"id": issue_id})
        connection.execute(_sql("DELETE FROM optimization_detail WHERE issue_id=:id"), {"id": issue_id})
        now = _now()
        if bug:
            connection.execute(
                _sql(
                    "INSERT INTO bug_detail (created_at,created_by,issue_id,reproduce_steps,expected_result,"
                    "actual_result,environment_json,fix_status,fixed_at) VALUES "
                    "(:now,:uid,:issue_id,:steps,:expected,:actual,:environment,'open',NULL)"
                ),
                {
                    "now": now,
                    "uid": user_id,
                    "issue_id": issue_id,
                    "steps": bug["reproduce_steps"],
                    "expected": bug["expected_result"],
                    "actual": bug["actual_result"],
                    "environment": _canonical(bug["environment"]) if bug["environment"] is not None else None,
                },
            )
        if optimization:
            connection.execute(
                _sql(
                    "INSERT INTO optimization_detail (created_at,created_by,issue_id,problem_evidence,"
                    "hypothesis,expected_outcome,impact_scope,need_new_version) VALUES "
                    "(:now,:uid,:issue_id,:evidence,:hypothesis,:outcome,:scope,:need_new_version)"
                ),
                {
                    "now": now,
                    "uid": user_id,
                    "issue_id": issue_id,
                    "evidence": optimization["problem_evidence"],
                    "hypothesis": optimization["hypothesis"],
                    "outcome": optimization["expected_outcome"],
                    "scope": optimization["impact_scope"],
                    "need_new_version": optimization["need_new_version"],
                },
            )


service = ValidationService()
