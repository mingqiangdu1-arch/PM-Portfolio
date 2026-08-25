"""MVP3 implementation-plan and confirmation business commands.

The public OpenAPI surface is materialised by Package 1.  This module owns the
ten hidden adapter commands behind that surface and deliberately uses the
existing foundation tables, audit log, outbox and idempotency record.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError

from app.modules.sprint1.service import _outbox
from app.platform.database import readonly, transaction
from app.platform.errors import ApiError

_ID = re.compile(r"^[1-9][0-9]*$")
_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_PLAN_SECTIONS = (
    "features",
    "business_rules",
    "state_requirements",
    "exceptions",
    "interactions",
    "dependencies",
    "acceptance_scope",
)
_PLAN_ITEM_SECTIONS = set(_PLAN_SECTIONS)
_PLAN_VERSION = "implementation_plan.mvp3.v1"
_READINESS_VERSION = "implementation_confirmation.readiness.mvp3.v1"


def _sql(statement: str) -> Any:
    from sqlalchemy import text

    return text(statement)


def _mapping(result: Any) -> dict[str, Any] | None:
    row = result.mappings().first()
    return dict(row) if row else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value else None


def _normal(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ApiError("VALIDATION_ERROR", f"{field} must be a string", 422)
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if not value:
        raise ApiError("VALIDATION_ERROR", f"{field} must not be blank", 422)
    return value


def _id(value: Any, field: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or not _ID.fullmatch(str(value))
    ):
        raise ApiError("VALIDATION_ERROR", f"{field} must be a positive ID", 422)
    return int(value)


def _body_id(value: Any, field: str) -> int:
    if not isinstance(value, str):
        raise ApiError("VALIDATION_ERROR", f"{field} must be a string ID", 422)
    return _id(value, field)


def _expected(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ApiError("VALIDATION_ERROR", "expected_version must be a positive integer", 422)
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _normalize_tree(value: Any, *, path: str = "") -> Any:
    if value is None:
        raise ApiError("VALIDATION_ERROR", f"{path or 'value'} must not be null", 422)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n").strip())
    if isinstance(value, bool) or isinstance(value, (int, float)):
        raise ApiError(
            "VALIDATION_ERROR", f"{path or 'value'} must not contain numeric values", 422
        )
    if isinstance(value, list):
        return [_normalize_tree(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ApiError("VALIDATION_ERROR", f"{path or 'value'} contains a non-string key", 422)
        return {
            key: _normalize_tree(item, path=f"{path}.{key}" if path else key)
            for key, item in value.items()
        }
    raise ApiError("VALIDATION_ERROR", f"{path or 'value'} has an invalid type", 422)


def _plan_content(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", *_PLAN_SECTIONS}:
        raise ApiError("VALIDATION_ERROR", "content_json does not match the frozen schema", 422)
    content = _normalize_tree(raw)
    if content["schema_version"] != _PLAN_VERSION:
        raise ApiError("VALIDATION_ERROR", "schema_version is invalid", 422)
    seen_keys: set[str] = set()
    for section in _PLAN_SECTIONS:
        values = content[section]
        if not isinstance(values, list):
            raise ApiError("VALIDATION_ERROR", f"{section} has an invalid item count", 422)
        minimum = 1 if section in {"features", "acceptance_scope"} else 0
        if not minimum <= len(values) <= 200:
            raise ApiError("VALIDATION_ERROR", f"{section} has an invalid item count", 422)
        seen_descriptions: set[str] = set()
        for item in values:
            if not isinstance(item, dict) or set(item) != {"key", "description"}:
                raise ApiError("VALIDATION_ERROR", f"{section} contains an invalid item", 422)
            key, description = item["key"], item["description"]
            if not isinstance(key, str) or not _KEY.fullmatch(key):
                raise ApiError("VALIDATION_ERROR", f"{section}.key is invalid", 422)
            if key in seen_keys:
                raise ApiError(
                    "VALIDATION_ERROR", "Plan item keys must be unique across sections", 422
                )
            if not isinstance(description, str) or not 1 <= len(description) <= 4000:
                raise ApiError("VALIDATION_ERROR", f"{section}.description is invalid", 422)
            if description in seen_descriptions:
                raise ApiError("VALIDATION_ERROR", f"Descriptions must be unique in {section}", 422)
            seen_keys.add(key)
            seen_descriptions.add(description)
    if len(_canonical(content).encode("utf-8")) > 262144:
        raise ApiError("VALIDATION_ERROR", "content_json exceeds 262144 UTF-8 bytes", 422)
    return content


def _readiness(raw: Any) -> dict[str, Any]:
    try:
        raw = _json(raw)
    except (TypeError, ValueError):
        raise ApiError(
            "VALIDATION_ERROR", "readiness_json does not match the frozen schema", 422
        ) from None
    required = {
        "schema_version",
        "scope_status",
        "implementation_status",
        "configuration_status",
        "data_change_status",
        "known_blockers",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ApiError("VALIDATION_ERROR", "readiness_json does not match the frozen schema", 422)
    value = _normalize_tree(raw)
    enums = {
        "scope_status": {"ready", "not_ready"},
        "implementation_status": {"ready", "not_ready"},
        "configuration_status": {"ready", "not_ready", "not_applicable"},
        "data_change_status": {"ready", "not_ready", "not_applicable"},
    }
    if value["schema_version"] != _READINESS_VERSION:
        raise ApiError("VALIDATION_ERROR", "readiness schema_version is invalid", 422)
    for field, allowed in enums.items():
        if value[field] not in allowed:
            raise ApiError("VALIDATION_ERROR", f"{field} is invalid", 422)
    blockers = value["known_blockers"]
    if (
        not isinstance(blockers, list)
        or len(blockers) > 50
        or any(not isinstance(item, str) or not 1 <= len(item) <= 500 for item in blockers)
        or len(set(blockers)) != len(blockers)
    ):
        raise ApiError("VALIDATION_ERROR", "known_blockers is invalid", 422)
    return value


def _summary(value: Any) -> str:
    value = _normal(value, "implementation_summary")
    if not 20 <= len(value) <= 8000:
        raise ApiError(
            "VALIDATION_ERROR", "implementation_summary must contain 20 to 8000 code points", 422
        )
    return value


def _exact(payload: Any, fields: set[str], operation: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ApiError("VALIDATION_ERROR", f"{operation} request fields are invalid", 422)
    return payload


def _json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _project_version(connection: Any, version_id: int) -> dict[str, Any]:
    row = _mapping(
        connection.execute(
            _sql("SELECT id,project_id FROM project_version WHERE id=:id AND archived_at IS NULL"),
            {"id": version_id},
        )
    )
    if not row:
        raise ApiError("NOT_FOUND", "Project version was not found", 404)
    return row


def _roles(connection: Any, project_id: int, user_id: int, *, lock: bool = False) -> list[str]:
    suffix = " FOR UPDATE" if lock else ""
    rows = (
        connection.execute(
            _sql(
                "SELECT role_code FROM project_member "
                "WHERE project_id=:project_id AND user_id=:user_id AND status='active'"
                f"{suffix}"
            ),
            {"project_id": project_id, "user_id": user_id},
        )
        .mappings()
        .all()
    )
    if not rows:
        raise ApiError("NOT_FOUND", "Project resource was not found", 404)
    return [str(row["role_code"]) for row in rows]


def _access(
    connection: Any, *, project_id: int, user_id: int, allowed: set[str], lock: bool = False
) -> list[str]:
    roles = _roles(connection, project_id, user_id, lock=lock)
    if not allowed.intersection(roles):
        raise ApiError("FORBIDDEN", "Project role does not allow this action", 403)
    return roles


def _write_role(roles: list[str]) -> str:
    """Return the deterministic role that authorized a Test Record write."""
    if "owner" in roles:
        return "owner"
    if "tester" in roles:
        return "tester"
    raise ApiError("FORBIDDEN", "Project role does not allow this action", 403)


def _read_access(connection: Any, *, project_id: int, user_id: int) -> list[str]:
    return _roles(connection, project_id, user_id)


def _source_binding_guard(
    connection: Any,
    *,
    project_version_id: int,
    source_prd_version_id: int,
    source_review_id: int,
    lock: bool = False,
) -> dict[str, dict[str, Any]]:
    suffix = " FOR UPDATE" if lock else ""
    source = _mapping(
        connection.execute(
            _sql(f"""
        SELECT pv.id AS source_version_id,pv.prd_id,pv.content_hash,pv.is_effective,
               p.project_version_id AS prd_project_version_id,p.status AS prd_status,
               p.current_version_id AS prd_current_version_id,p.archived_at AS prd_archived_at
        FROM prd_version pv JOIN prd p ON p.id=pv.prd_id
        WHERE pv.id=:source_prd_version_id{suffix}
    """),
            {"source_prd_version_id": source_prd_version_id},
        )
    )
    review = _mapping(
        connection.execute(
            _sql(
                "SELECT id,project_version_id,status,archived_at "
                f"FROM design_review WHERE id=:id{suffix}"
            ),
            {"id": source_review_id},
        )
    )
    if not source or not review:
        raise ApiError("SOURCE_BINDING_MISMATCH", "Frozen source binding does not match", 409)
    scopes = (
        connection.execute(
            _sql(f"""SELECT object_type,object_id,object_version_id,content_hash
        FROM design_review_scope WHERE design_review_id=:review_id{suffix}"""),
            {"review_id": source_review_id},
        )
        .mappings()
        .all()
    )
    exact = [
        dict(scope)
        for scope in scopes
        if scope["object_type"] == "PRD"
        and scope["object_id"] == source["prd_id"]
        and scope["object_version_id"] == source_prd_version_id
        and scope["content_hash"] == source["content_hash"]
    ]
    if len(exact) != 1:
        raise ApiError("SOURCE_BINDING_MISMATCH", "PRD belongs to another project version", 409)
    if (
        int(source["prd_project_version_id"]) != project_version_id
        or int(review["project_version_id"]) != project_version_id
    ):
        raise ApiError("SOURCE_BINDING_MISMATCH", "Source belongs to another project version", 409)
    return {"source": source, "review": review, "scope": exact[0]}


def _source_live_guard(
    connection: Any, *, project_version_id: int, source_prd_version_id: int, source_review_id: int
) -> None:
    binding = _source_binding_guard(
        connection,
        project_version_id=project_version_id,
        source_prd_version_id=source_prd_version_id,
        source_review_id=source_review_id,
        lock=True,
    )
    source, review = binding["source"], binding["review"]
    if (
        source["prd_archived_at"] is not None
        or source["prd_status"] != "confirmed"
        or source["prd_current_version_id"] != source_prd_version_id
        or not bool(source["is_effective"])
    ):
        raise ApiError(
            "SOURCE_PRD_NOT_CONFIRMED", "Source PRD version is not confirmed and effective", 409
        )
    if review["archived_at"] is not None or review["status"] != "passed":
        raise ApiError("SOURCE_REVIEW_NOT_PASSED", "Source design review is not passed", 409)


def _plan_row(row: dict[str, Any], versions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    current = row.get("current_version_id")
    effective = next((v["id"] for v in (versions or []) if v.get("is_effective")), None)
    if effective is None and row.get("id") is not None:
        effective = row.get("effective_version_id")
    state = (
        "not_ready"
        if effective is None
        else ("confirmed" if row.get("confirmed_effective") else "needs_confirmation")
    )
    if effective is not None and row.get("has_history") and not row.get("confirmed_effective"):
        state = "needs_reconfirmation"
    result = {
        "id": str(row["id"]),
        "project_version_id": str(row["project_version_id"]),
        "source_prd_version_id": str(row["source_prd_version_id"]),
        "source_design_review_id": str(row["source_design_review_id"]),
        "name": row["name"],
        "status": row.get("status") or ("active" if effective else "draft"),
        "row_version": int(row["row_version"]),
        "confirmation_state": state,
    }
    if current is not None:
        result["current_version_id"] = str(current)
    if effective is not None:
        result["effective_version_id"] = str(effective)
    if versions is not None:
        result["versions"] = versions
    return result


def _version(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "implementation_plan_id": str(row["implementation_plan_id"]),
        "source_version_id": str(row["source_version_id"])
        if row.get("source_version_id") is not None
        else None,
        "version_no": str(row["version_no"]),
        "review_id": str(row["review_id"]),
        "content_json": _json(row["content_json"]),
        "content_hash": row["content_hash"],
        "change_note": row["change_note"],
        "is_effective": bool(row["is_effective"]),
        "created_by": str(row["created_by"]) if row.get("created_by") is not None else None,
        "created_at": _iso(row["created_at"]),
    }


def _round(row: dict[str, Any]) -> dict[str, Any]:
    result = {
        "id": str(row["id"]),
        "implementation_plan_id": str(row["implementation_plan_id"]),
        "plan_version_id": str(row["plan_version_id"]),
        "round_no": int(row["round_no"]),
        "status": row["status"],
        "implementation_summary": row["implementation_summary"],
        "readiness_json": _json(row["readiness_json"]),
        "row_version": int(row["row_version"]),
        "is_effective": bool(row["is_effective"]),
    }
    for key in ("source_round_id", "confirmed_by"):
        if row.get(key) is not None:
            result[key] = str(row[key])
    if row.get("confirm_status") is not None:
        result["confirm_status"] = row["confirm_status"]
    for key in ("confirmed_at", "superseded_at"):
        if row.get(key) is not None:
            result[key] = _iso(row[key])
    return result


def _test_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ApiError("VALIDATION_ERROR", f"{field} must be a string", 422)
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _test_environment(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"name", "preconditions"}:
        raise ApiError("VALIDATION_ERROR", "environment fields are invalid", 422)
    name = _test_text(value["name"], "environment.name")
    preconditions = value["preconditions"]
    if not isinstance(preconditions, list) or any(not isinstance(item, str) for item in preconditions):
        raise ApiError("VALIDATION_ERROR", "environment.preconditions must be a string array", 422)
    return {
        "name": name,
        "preconditions": [
            unicodedata.normalize("NFC", item.replace("\r\n", "\n").replace("\r", "\n")).strip()
            for item in preconditions
        ],
    }


def _test_title(value: Any) -> str:
    title = _normal(value, "title")
    if len(title) > 200:
        raise ApiError("VALIDATION_ERROR", "title must contain 1 to 200 characters", 422)
    return title


def _test_steps(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ApiError("VALIDATION_ERROR", "steps must be a string array", 422)
    return [
        unicodedata.normalize("NFC", item.replace("\r\n", "\n").replace("\r", "\n")).strip()
        for item in value
    ]


def _test_result_status(value: Any) -> str:
    if value not in {"success", "failed", "partial"}:
        raise ApiError("VALIDATION_ERROR", "result_status is invalid", 422)
    return value


def _test_record(row: dict[str, Any]) -> dict[str, Any]:
    submitted_at = row.get("submitted_at")
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "project_version_id": str(row["project_version_id"]),
        "confirmation_round_id": str(row["confirmation_round_id"]),
        "title": row["title"],
        "test_type": "manual",
        "scope": row["scope"],
        "environment": _json(row["environment_json"]),
        "steps": _json(row["steps_json"]),
        "expected_result": row["expected_result"],
        "actual_result": row["actual_result"],
        "result_status": row["result_status"],
        "no_issue_conclusion": bool(row.get("no_issue_conclusion", False)),
        "tester_id": str(row["tester_id"]),
        "status": "submitted" if submitted_at is not None else "draft",
        "submitted_at": _iso(submitted_at),
        "row_version": int(row["row_version"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _test_source_guard(
    connection: Any, round_id: int, *, lock: bool = False, validate: bool = True
) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock else ""
    row = _mapping(
        connection.execute(
            _sql(
                "SELECT r.id AS round_id,r.status AS round_status,r.confirm_status,"
                "r.is_effective AS round_effective,r.plan_version_id,"
                "p.id AS plan_id,p.project_version_id,p.status AS plan_status,"
                "p.current_version_id,pv.implementation_plan_id AS plan_version_plan_id,"
                "pv.is_effective AS plan_version_effective,"
                "v.project_id "
                "FROM confirmation_round r "
                "JOIN implementation_plan p ON p.id=r.implementation_plan_id "
                "JOIN implementation_plan_version pv ON pv.id=r.plan_version_id "
                "JOIN project_version v ON v.id=p.project_version_id "
                "WHERE r.id=:round_id AND p.archived_at IS NULL AND v.archived_at IS NULL"
                f"{suffix}"
            ),
            {"round_id": round_id},
        )
    )
    if not row:
        raise ApiError("NOT_FOUND", "Confirmation round was not found", 404)
    if not validate:
        return row
    if row["round_status"] != "confirmed" or row["confirm_status"] != "confirmed":
        raise ApiError("CONFIRMATION_NOT_CONFIRMED", "Confirmation round is not confirmed", 409)
    if not bool(row["round_effective"]):
        raise ApiError("CONFIRMATION_NOT_EFFECTIVE", "Confirmation round is not effective", 409)
    if int(row["current_version_id"] or 0) != int(row["plan_version_id"]):
        raise ApiError("PLAN_VERSION_NOT_CURRENT", "Confirmation round is not bound to the current plan version", 409)
    if int(row["plan_version_plan_id"]) != int(row["plan_id"]):
        raise ApiError("PLAN_VERSION_BINDING_MISMATCH", "Plan version belongs to another implementation plan", 409)
    if not bool(row["plan_version_effective"]):
        raise ApiError("PLAN_VERSION_BINDING_MISMATCH", "Plan version binding is not effective", 409)
    if row["plan_status"] != "active":
        raise ApiError("INVALID_STATE", "Implementation plan is not active", 409)
    return row


def _test_complete(row: dict[str, Any]) -> bool:
    environment = _json(row["environment_json"])
    steps = _json(row["steps_json"])
    return bool(
        str(row["scope"]).strip()
        and isinstance(environment, dict)
        and str(environment.get("name", "")).strip()
        and isinstance(steps, list)
        and steps
        and all(isinstance(item, str) and item.strip() for item in steps)
        and str(row["expected_result"]).strip()
        and str(row["actual_result"]).strip()
        and row["result_status"] in {"success", "failed", "partial"}
    )


def _test_record_identity(connection: Any, record_id: int, *, lock: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock else ""
    row = _mapping(
        connection.execute(
            _sql(
                "SELECT tr.*,r.implementation_plan_id,p.project_version_id,v.project_id "
                "FROM test_record tr "
                "JOIN confirmation_round r ON r.id=tr.confirmation_round_id "
                "JOIN implementation_plan p ON p.id=r.implementation_plan_id "
                "JOIN project_version v ON v.id=p.project_version_id "
                "WHERE tr.id=:id AND p.archived_at IS NULL AND v.archived_at IS NULL"
                f"{suffix}"
            ),
            {"id": record_id},
        )
    )
    if not row:
        raise ApiError("NOT_FOUND", "Test Record was not found", 404)
    return row


def _idem_hash(payload: dict[str, Any]) -> str:
    return _digest(payload)


def _idem_begin(
    connection: Any, *, user_id: int, endpoint: str, key: str, payload: dict[str, Any]
) -> str | None:
    now = _now()
    digest = _idem_hash(payload)
    inserted = (
        connection.execute(
            _sql("""
        INSERT IGNORE INTO idempotency_record
        (user_id,endpoint_key,idempotency_key,request_hash,status,response_code,response_ref,created_at,expires_at)
        VALUES (:user_id,:endpoint,:key,:digest,'in_progress',NULL,NULL,:created_at,:expires_at)
    """),
            {
                "user_id": user_id,
                "endpoint": endpoint,
                "key": key,
                "digest": digest,
                "created_at": now,
                "expires_at": now + timedelta(days=1),
            },
        ).rowcount
        == 1
    )
    row = _mapping(
        connection.execute(
            _sql(
                "SELECT request_hash,status,response_ref FROM idempotency_record "
                "WHERE user_id=:user_id AND endpoint_key=:endpoint "
                "AND idempotency_key=:key FOR UPDATE"
            ),
            {"user_id": user_id, "endpoint": endpoint, "key": key},
        )
    )
    if not row or row["request_hash"] != digest or (not inserted and row["status"] != "completed"):
        raise ApiError(
            "IDEMPOTENCY_CONFLICT", "Idempotency-Key conflicts with an existing command", 409
        )
    return (
        str(row["response_ref"]) if row["status"] == "completed" and row["response_ref"] else None
    )


def _idem_complete(
    connection: Any, *, user_id: int, endpoint: str, key: str, response_ref: str
) -> None:
    connection.execute(
        _sql(
            "UPDATE idempotency_record SET status='completed',response_code='OK',response_ref=:ref "
            "WHERE user_id=:user_id AND endpoint_key=:endpoint "
            "AND idempotency_key=:key"
        ),
        {"ref": response_ref, "user_id": user_id, "endpoint": endpoint, "key": key},
    )


def _snapshot_replay(connection: Any, response_ref: str) -> dict[str, Any]:
    if response_ref.startswith("test_record:"):
        record_id = response_ref[len("test_record:") :]
        if not _ID.fullmatch(record_id):
            raise ApiError("IDEMPOTENCY_CONFLICT", "Original command snapshot is unavailable", 409)
        row = _test_record_identity(connection, int(record_id))
        return {"test_record": _test_record(row)}
    if not response_ref.startswith("audit:"):
        raise ApiError("IDEMPOTENCY_CONFLICT", "Original command snapshot is unavailable", 409)
    audit_id = response_ref[6:]
    if not _ID.fullmatch(audit_id):
        raise ApiError("IDEMPOTENCY_CONFLICT", "Original command snapshot is unavailable", 409)
    row = _mapping(
        connection.execute(
            _sql("SELECT metadata_json FROM operation_audit_log WHERE id=:id"),
            {"id": int(audit_id)},
        )
    )
    if not row:
        raise ApiError("IDEMPOTENCY_CONFLICT", "Original command snapshot is unavailable", 409)
    metadata = _json(row["metadata_json"])
    snapshot = metadata.get("response_data") if isinstance(metadata, dict) else None
    if not isinstance(snapshot, dict):
        raise ApiError("IDEMPOTENCY_CONFLICT", "Original command snapshot is unavailable", 409)
    return snapshot


def _persist_command(
    connection: Any,
    *,
    actor_user_id: int,
    operation: str,
    object_type: str,
    object_id: int,
    object_version_id: int | None,
    trace_id: str,
    command_id: str,
    response_data: dict[str, Any] | None,
    audit_metadata: dict[str, Any] | None = None,
    aggregate_type: str,
    aggregate_version: int,
    event_name: str,
    event_payload: dict[str, Any],
    project_id: int,
    project_version_id: int,
) -> int:
    now = _now()
    audit = connection.execute(
        _sql("""
        INSERT INTO operation_audit_log
        (retention_class,expires_at,actor_user_id,actor_type,operation_name,object_type,object_id,object_version_id,
         result_status,failure_code,reason_summary,trace_id,command_id,occurred_at,metadata_json)
        VALUES ('audit',NULL,:actor,'user',:operation,:object_type,:object_id,:object_version_id,
                'success',NULL,NULL,:trace_id,:command_id,:occurred_at,:metadata)
    """),
        {
            "actor": actor_user_id,
            "operation": operation,
            "object_type": object_type,
            "object_id": object_id,
            "object_version_id": object_version_id,
            "trace_id": trace_id,
            "command_id": command_id,
            "occurred_at": now,
            "metadata": _canonical(
                audit_metadata
                if audit_metadata is not None
                else {"schema_version": "mvp3.command.snapshot.v1", "response_data": response_data}
            ),
        },
    )
    _outbox(
        connection,
        aggregate_type=aggregate_type,
        aggregate_id=object_id,
        aggregate_version=aggregate_version,
        event_name=event_name,
        payload=event_payload,
        trace_id=trace_id,
        command_id=command_id,
        module="confirmation",
        user_id=actor_user_id,
        project_id=project_id,
        project_version_id=project_version_id,
    )
    return int(audit.lastrowid)


def _map_integrity(exc: IntegrityError) -> ApiError:
    message = str(exc.orig if getattr(exc, "orig", None) else exc).lower()
    if "uk_plan_one_draft_round" in message or "draft_plan_key" in message:
        return ApiError("CONFIRMATION_ALREADY_EXISTS", "A draft confirmation already exists", 409)
    if (
        "uk_confirmation_round" in message
        or "uk_plan_effective" in message
        or "uk_plan_one_effective_round" in message
        or "uk_plan_version" in message
    ):
        return ApiError("VERSION_CONFLICT", "The resource changed concurrently", 409)
    return ApiError("INVALID_STATE", "The operation could not be completed", 409)


def _map_database_error(exc: Exception) -> ApiError:
    if isinstance(exc, IntegrityError):
        return _map_integrity(exc)
    message = str(getattr(exc, "orig", exc)).lower()
    if (
        "1213" in message
        or "1205" in message
        or "deadlock" in message
        or "lock wait timeout" in message
    ):
        return ApiError("VERSION_CONFLICT", "The resource changed concurrently", 409)
    return ApiError("INVALID_STATE", "The operation could not be completed", 409)


def _database_error_boundary(function: Any) -> Any:
    """Map driver errors after the transaction context has rolled back."""

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    return wrapped


class ConfirmationService:
    def _plan(self, connection: Any, plan_id: int, *, lock: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE" if lock else ""
        row = _mapping(
            connection.execute(
                _sql(
                    "SELECT * FROM implementation_plan "
                    f"WHERE id=:id AND archived_at IS NULL{suffix}"
                ),
                {"id": plan_id},
            )
        )
        if not row:
            raise ApiError("NOT_FOUND", "Implementation plan was not found", 404)
        return row

    def _plan_response(
        self, connection: Any, plan: dict[str, Any], *, with_versions: bool
    ) -> dict[str, Any]:
        versions_rows = (
            connection.execute(
                _sql(
                    "SELECT * FROM implementation_plan_version "
                    "WHERE implementation_plan_id=:id "
                    "ORDER BY CAST(version_no AS UNSIGNED),id"
                ),
                {"id": plan["id"]},
            )
            .mappings()
            .all()
        )
        versions = [_version(dict(row)) for row in versions_rows]
        effective = next((v for v in versions if v["is_effective"]), None)
        confirmed = _mapping(
            connection.execute(
                _sql(
                    "SELECT id FROM confirmation_round "
                    "WHERE implementation_plan_id=:id AND is_effective=1 "
                    "AND status='confirmed'"
                ),
                {"id": plan["id"]},
            )
        )
        history = _mapping(
            connection.execute(
                _sql(
                    "SELECT id FROM confirmation_round "
                    "WHERE implementation_plan_id=:id "
                    "AND status IN ('confirmed','superseded') LIMIT 1"
                ),
                {"id": plan["id"]},
            )
        )
        value = dict(plan)
        value["confirmed_effective"] = bool(confirmed)
        value["has_history"] = bool(history)
        value["effective_version_id"] = effective["id"] if effective else None
        return {"implementation_plan": _plan_row(value, versions if with_versions else None)}

    def _guard_plan_access(
        self, connection: Any, plan: dict[str, Any], user_id: int, roles: set[str]
    ) -> list[str]:
        version = _project_version(connection, int(plan["project_version_id"]))
        if not roles:
            return _read_access(connection, project_id=int(version["project_id"]), user_id=user_id)
        return _access(
            connection, project_id=int(version["project_id"]), user_id=user_id, allowed=roles
        )

    def list_plans(self, *, version_id: int, user_id: int) -> dict[str, Any]:
        version_id = _id(version_id, "version_id")
        with readonly() as connection:
            version = _project_version(connection, version_id)
            _read_access(connection, project_id=int(version["project_id"]), user_id=user_id)
            rows = (
                connection.execute(
                    _sql(
                        "SELECT * FROM implementation_plan "
                        "WHERE project_version_id=:id AND archived_at IS NULL "
                        "ORDER BY id"
                    ),
                    {"id": version_id},
                )
                .mappings()
                .all()
            )
            return {
                "items": [
                    self._plan_response(connection, dict(row), with_versions=False)[
                        "implementation_plan"
                    ]
                    for row in rows
                ]
            }

    def get_plan(self, *, plan_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            plan = self._plan(connection, _id(plan_id, "id"))
            self._guard_plan_access(connection, plan, user_id, set())
            return self._plan_response(connection, plan, with_versions=True)

    def create_plan(
        self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        payload = _exact(
            payload,
            {"source_prd_version_id", "source_design_review_id", "name"},
            "CreateImplementationPlan",
        )
        source_prd = _body_id(payload["source_prd_version_id"], "source_prd_version_id")
        source_review = _body_id(payload["source_design_review_id"], "source_design_review_id")
        name = _normal(payload["name"], "name")
        if len(name) > 200:
            raise ApiError("VALIDATION_ERROR", "name is too long", 422)
        endpoint = (
            "createProjectVersionImplementationPlan:"
            f"/api/v1/project-versions/{version_id}/implementation-plans"
        )
        request = {
            "source_prd_version_id": str(source_prd),
            "source_design_review_id": str(source_review),
            "name": name,
        }
        try:
            with transaction() as connection:
                project_version = _project_version(connection, _id(version_id, "version_id"))
                _access(
                    connection,
                    project_id=int(project_version["project_id"]),
                    user_id=user_id,
                    allowed={"owner"},
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                _source_live_guard(
                    connection,
                    project_version_id=int(project_version["id"]),
                    source_prd_version_id=source_prd,
                    source_review_id=source_review,
                )
                now = _now()
                result = connection.execute(
                    _sql(
                        "INSERT INTO implementation_plan "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,"
                        "archived_by,project_version_id,name,status,current_version_id,"
                        "source_prd_version_id,source_design_review_id) "
                        "VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:project_version_id,:name,"
                        "'draft',NULL,:source_prd,:source_review)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "project_version_id": project_version["id"],
                        "name": name,
                        "source_prd": source_prd,
                        "source_review": source_review,
                    },
                )
                plan_id = int(result.lastrowid)
                response_data = self._plan_response(
                    connection, self._plan(connection, plan_id), with_versions=True
                )
                command = f"cmd_{uuid.uuid4().hex}"
                audit_id = _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="implementation_plan.created",
                    object_type="implementation_plan",
                    object_id=plan_id,
                    object_version_id=None,
                    trace_id=trace_id,
                    command_id=command,
                    response_data=response_data,
                    aggregate_type="implementation_plan",
                    aggregate_version=1,
                    event_name="implementation_plan.created",
                    event_payload={"schema_version": "implementation_plan.mvp3.v1"},
                    project_id=int(project_version["project_id"]),
                    project_version_id=int(project_version["id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def create_plan_version(
        self, *, plan_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        payload = _exact(
            payload,
            {"expected_version", "content_json", "change_note"},
            "CreateImplementationPlanVersion",
        )
        expected = _expected(payload["expected_version"])
        content = _plan_content(payload["content_json"])
        note = _normal(payload["change_note"], "change_note")
        if len(note) > 2000:
            raise ApiError("VALIDATION_ERROR", "change_note is too long", 422)
        plan_id = _id(plan_id, "id")
        endpoint = (
            f"createImplementationPlanVersion:/api/v1/implementation-plans/{plan_id}/versions"
        )
        request = {"expected_version": expected, "content_json": content, "change_note": note}
        try:
            with transaction() as connection:
                plan = self._plan(connection, plan_id, lock=True)
                project_version = _project_version(connection, int(plan["project_version_id"]))
                _access(
                    connection,
                    project_id=int(project_version["project_id"]),
                    user_id=user_id,
                    allowed={"owner"},
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                if int(plan["row_version"]) != expected:
                    raise ApiError("VERSION_CONFLICT", "Implementation plan has changed", 409)
                _source_binding_guard(
                    connection,
                    project_version_id=int(plan["project_version_id"]),
                    source_prd_version_id=int(plan["source_prd_version_id"]),
                    source_review_id=int(plan["source_design_review_id"]),
                    lock=True,
                )
                previous = (
                    _mapping(
                        connection.execute(
                            _sql(
                                "SELECT * FROM implementation_plan_version "
                                "WHERE implementation_plan_id=:id AND id=:current_id"
                            ),
                            {"id": plan_id, "current_id": plan["current_version_id"]},
                        )
                    )
                    if plan["current_version_id"]
                    else None
                )
                next_no = int(previous["version_no"]) + 1 if previous else 1
                now = _now()
                result = connection.execute(
                    _sql(
                        "INSERT INTO implementation_plan_version "
                        "(created_at,created_by,implementation_plan_id,source_version_id,"
                        "version_no,review_id,content_json,content_hash,change_note,"
                        "created_from_ai_result_id,is_effective) "
                        "VALUES (:now,:uid,:plan_id,:source_id,:version_no,:review_id,"
                        ":content,:hash,:note,NULL,0)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "plan_id": plan_id,
                        "source_id": previous["id"] if previous else None,
                        "version_no": str(next_no),
                        "review_id": plan["source_design_review_id"],
                        "content": _canonical(content),
                        "hash": _digest(content),
                        "note": note,
                    },
                )
                version_id = int(result.lastrowid)
                connection.execute(
                    _sql(
                        "UPDATE implementation_plan SET current_version_id=:version_id,"
                        "row_version=row_version+1,updated_at=:now,updated_by=:uid "
                        "WHERE id=:id AND row_version=:expected"
                    ),
                    {
                        "version_id": version_id,
                        "now": now,
                        "uid": user_id,
                        "id": plan_id,
                        "expected": expected,
                    },
                )
                row = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM implementation_plan_version WHERE id=:id"),
                        {"id": version_id},
                    )
                )
                response_data = {
                    "implementation_plan_version": _version(row),
                    "plan_row_version": expected + 1,
                }
                command = f"cmd_{uuid.uuid4().hex}"
                audit_id = _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="implementation_plan.version.created",
                    object_type="implementation_plan",
                    object_id=plan_id,
                    object_version_id=version_id,
                    trace_id=trace_id,
                    command_id=command,
                    response_data=response_data,
                    aggregate_type="implementation_plan",
                    aggregate_version=expected + 1,
                    event_name="implementation_plan.version.created",
                    event_payload={
                        "schema_version": "implementation_plan.mvp3.v1",
                        "version_id": str(version_id),
                    },
                    project_id=int(project_version["project_id"]),
                    project_version_id=int(plan["project_version_id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def set_effective(
        self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        payload = _exact(payload, {"expected_version"}, "SetEffectiveImplementationPlanVersion")
        expected = _expected(payload["expected_version"])
        version_id = _id(version_id, "id")
        endpoint = (
            "setEffectiveImplementationPlanVersion:"
            f"/api/v1/plan-versions/{version_id}:set-effective"
        )
        request = {"expected_version": expected}
        try:
            with transaction() as connection:
                version = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM implementation_plan_version WHERE id=:id"),
                        {"id": version_id},
                    )
                )
                if not version:
                    raise ApiError("NOT_FOUND", "Implementation plan version was not found", 404)
                plan = self._plan(connection, int(version["implementation_plan_id"]), lock=True)
                project_version = _project_version(connection, int(plan["project_version_id"]))
                _access(
                    connection,
                    project_id=int(project_version["project_id"]),
                    user_id=user_id,
                    allowed={"owner"},
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                if int(plan["row_version"]) != expected:
                    raise ApiError("VERSION_CONFLICT", "Implementation plan has changed", 409)
                if int(plan["current_version_id"] or 0) != version_id:
                    raise ApiError(
                        "PLAN_VERSION_NOT_CURRENT", "Target is not the current plan version", 409
                    )
                _source_live_guard(
                    connection,
                    project_version_id=int(plan["project_version_id"]),
                    source_prd_version_id=int(plan["source_prd_version_id"]),
                    source_review_id=int(plan["source_design_review_id"]),
                )
                now = _now()
                connection.execute(
                    _sql(
                        "UPDATE implementation_plan_version SET is_effective=0 "
                        "WHERE implementation_plan_id=:id AND is_effective=1"
                    ),
                    {"id": plan["id"]},
                )
                connection.execute(
                    _sql("UPDATE implementation_plan_version SET is_effective=1 WHERE id=:id"),
                    {"id": version_id},
                )
                connection.execute(
                    _sql(
                        "UPDATE confirmation_round SET is_effective=0 "
                        "WHERE implementation_plan_id=:id AND is_effective=1"
                    ),
                    {"id": plan["id"]},
                )
                connection.execute(
                    _sql(
                        "UPDATE implementation_plan SET status='active',"
                        "row_version=row_version+1,updated_at=:now,updated_by=:uid "
                        "WHERE id=:id AND row_version=:expected"
                    ),
                    {"now": now, "uid": user_id, "id": plan["id"], "expected": expected},
                )
                response_data = self._plan_response(
                    connection, self._plan(connection, int(plan["id"])), with_versions=True
                )
                command = f"cmd_{uuid.uuid4().hex}"
                audit_id = _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="implementation_plan.version.effective",
                    object_type="implementation_plan",
                    object_id=int(plan["id"]),
                    object_version_id=version_id,
                    trace_id=trace_id,
                    command_id=command,
                    response_data=response_data,
                    aggregate_type="implementation_plan",
                    aggregate_version=expected + 1,
                    event_name="implementation_plan.version.effective",
                    event_payload={
                        "schema_version": "implementation_plan.mvp3.v1",
                        "version_id": str(version_id),
                    },
                    project_id=int(project_version["project_id"]),
                    project_version_id=int(plan["project_version_id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def list_rounds(self, *, plan_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            plan = self._plan(connection, _id(plan_id, "id"))
            self._guard_plan_access(connection, plan, user_id, set())
            rows = (
                connection.execute(
                    _sql(
                        "SELECT * FROM confirmation_round "
                        "WHERE implementation_plan_id=:id ORDER BY round_no"
                    ),
                    {"id": plan["id"]},
                )
                .mappings()
                .all()
            )
            return {"items": [_round(dict(row)) for row in rows]}

    def get_round(self, *, round_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            row = _mapping(
                connection.execute(
                    _sql("SELECT * FROM confirmation_round WHERE id=:id"),
                    {"id": _id(round_id, "id")},
                )
            )
            if not row:
                raise ApiError("NOT_FOUND", "Confirmation round was not found", 404)
            plan = self._plan(connection, int(row["implementation_plan_id"]))
            self._guard_plan_access(connection, plan, user_id, set())
            return {"confirmation_round": _round(row)}

    def create_round(
        self, *, plan_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        payload = _exact(
            payload,
            {"plan_version_id", "implementation_summary", "readiness_json"},
            "CreateConfirmationRound",
        )
        plan_id = _id(plan_id, "id")
        version_id = _body_id(payload["plan_version_id"], "plan_version_id")
        summary = _summary(payload["implementation_summary"])
        readiness = _readiness(payload["readiness_json"])
        endpoint = (
            "createImplementationPlanConfirmationRound:"
            f"/api/v1/implementation-plans/{plan_id}/confirmation-rounds"
        )
        request = {
            "plan_version_id": str(version_id),
            "implementation_summary": summary,
            "readiness_json": readiness,
        }
        try:
            with transaction() as connection:
                plan = self._plan(connection, plan_id, lock=True)
                project_version = _project_version(connection, int(plan["project_version_id"]))
                _access(
                    connection,
                    project_id=int(project_version["project_id"]),
                    user_id=user_id,
                    allowed={"owner", "implementer"},
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                _source_live_guard(
                    connection,
                    project_version_id=int(plan["project_version_id"]),
                    source_prd_version_id=int(plan["source_prd_version_id"]),
                    source_review_id=int(plan["source_design_review_id"]),
                )
                draft = _mapping(
                    connection.execute(
                        _sql(
                            "SELECT id FROM confirmation_round "
                            "WHERE implementation_plan_id=:id AND status='draft' "
                            "LIMIT 1 FOR UPDATE"
                        ),
                        {"id": plan_id},
                    )
                )
                if draft:
                    raise ApiError(
                        "CONFIRMATION_ALREADY_EXISTS", "A draft confirmation already exists", 409
                    )
                effective = _mapping(
                    connection.execute(
                        _sql(
                            "SELECT * FROM implementation_plan_version "
                            "WHERE id=:id AND implementation_plan_id=:plan_id "
                            "AND is_effective=1"
                        ),
                        {"id": version_id, "plan_id": plan_id},
                    )
                )
                current = _mapping(
                    connection.execute(
                        _sql(
                            "SELECT id FROM implementation_plan_version "
                            "WHERE id=:id AND implementation_plan_id=:plan_id"
                        ),
                        {"id": plan["current_version_id"], "plan_id": plan_id},
                    )
                )
                if not current or int(current["id"]) != version_id:
                    raise ApiError("PLAN_VERSION_NOT_CURRENT", "Target is not current", 409)
                if not effective:
                    raise ApiError("PLAN_VERSION_NOT_CURRENT", "Target is not effective", 409)
                latest = _mapping(
                    connection.execute(
                        _sql(
                            "SELECT * FROM confirmation_round "
                            "WHERE implementation_plan_id=:id "
                            "AND status IN ('confirmed','superseded') "
                            "ORDER BY round_no DESC LIMIT 1 FOR UPDATE"
                        ),
                        {"id": plan_id},
                    )
                )
                round_no = int(latest["round_no"]) + 1 if latest else 1
                now = _now()
                result = connection.execute(
                    _sql(
                        "INSERT INTO confirmation_round "
                        "(created_at,created_by,updated_at,updated_by,row_version,"
                        "implementation_plan_id,plan_version_id,source_round_id,round_no,status,"
                        "confirm_status,is_effective,confirmed_by,confirmed_at,superseded_at,"
                        "implementation_summary,readiness_json) "
                        "VALUES (:now,:uid,:now,:uid,1,:plan_id,:version_id,:source_round,"
                        ":round_no,'draft',NULL,0,NULL,NULL,NULL,:summary,:readiness)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "plan_id": plan_id,
                        "version_id": version_id,
                        "source_round": latest["id"] if latest else None,
                        "round_no": round_no,
                        "summary": summary,
                        "readiness": _canonical(readiness),
                    },
                )
                round_id = int(result.lastrowid)
                row = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM confirmation_round WHERE id=:id"), {"id": round_id}
                    )
                )
                response_data = {"confirmation_round": _round(row)}
                command = f"cmd_{uuid.uuid4().hex}"
                audit_id = _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="confirmation_round.created",
                    object_type="confirmation_round",
                    object_id=round_id,
                    object_version_id=version_id,
                    trace_id=trace_id,
                    command_id=command,
                    response_data=response_data,
                    aggregate_type="confirmation_round",
                    aggregate_version=1,
                    event_name="confirmation_round.created",
                    event_payload={"schema_version": "implementation_confirmation.mvp3.v1"},
                    project_id=int(project_version["project_id"]),
                    project_version_id=int(plan["project_version_id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    @_database_error_boundary
    def update_round(
        self,
        *,
        round_id: int,
        user_id: int,
        payload: dict[str, Any],
        trace_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key is not None:
            raise ApiError("VALIDATION_ERROR", "PATCH does not accept Idempotency-Key", 422)
        payload = _exact(
            payload,
            {"expected_version", "plan_version_id", "implementation_summary", "readiness_json"},
            "UpdateConfirmationRoundDraft",
        )
        expected = _expected(payload["expected_version"])
        round_id = _id(round_id, "id")
        version_id = _body_id(payload["plan_version_id"], "plan_version_id")
        summary = _summary(payload["implementation_summary"])
        readiness = _readiness(payload["readiness_json"])
        with transaction() as connection:
            identity = _mapping(
                connection.execute(
                    _sql("SELECT implementation_plan_id FROM confirmation_round WHERE id=:id"),
                    {"id": round_id},
                )
            )
            if not identity:
                raise ApiError("NOT_FOUND", "Confirmation round was not found", 404)
            plan = self._plan(connection, int(identity["implementation_plan_id"]), lock=True)
            project_version = _project_version(connection, int(plan["project_version_id"]))
            _access(
                connection,
                project_id=int(project_version["project_id"]),
                user_id=user_id,
                allowed={"owner", "implementer"},
            )
            row = _mapping(
                connection.execute(
                    _sql("SELECT * FROM confirmation_round WHERE id=:id FOR UPDATE"),
                    {"id": round_id},
                )
            )
            if not row or int(row["implementation_plan_id"]) != int(plan["id"]):
                raise ApiError("NOT_FOUND", "Confirmation round was not found", 404)
            if row["status"] != "draft":
                raise ApiError("CONFIRMATION_NOT_DRAFT", "Confirmation round is not a draft", 409)
            if int(row["row_version"]) != expected:
                raise ApiError("VERSION_CONFLICT", "Confirmation round has changed", 409)
            current = _mapping(
                connection.execute(
                    _sql(
                        "SELECT id,is_effective FROM implementation_plan_version "
                        "WHERE id=:id AND implementation_plan_id=:plan_id"
                    ),
                    {"id": version_id, "plan_id": plan["id"]},
                )
            )
            if not current or int(plan["current_version_id"] or 0) != version_id:
                raise ApiError("PLAN_VERSION_NOT_CURRENT", "Target is not current", 409)
            connection.execute(
                _sql(
                    "UPDATE confirmation_round SET plan_version_id=:version_id,"
                    "implementation_summary=:summary,readiness_json=:readiness,"
                    "row_version=row_version+1,updated_at=:now,updated_by=:uid "
                    "WHERE id=:id AND row_version=:expected"
                ),
                {
                    "version_id": version_id,
                    "summary": summary,
                    "readiness": _canonical(readiness),
                    "now": _now(),
                    "uid": user_id,
                    "id": round_id,
                    "expected": expected,
                },
            )
            updated = _mapping(
                connection.execute(
                    _sql("SELECT * FROM confirmation_round WHERE id=:id"), {"id": round_id}
                )
            )
            response_data = {"confirmation_round": _round(updated)}
            command = f"cmd_{uuid.uuid4().hex}"
            _persist_command(
                connection,
                actor_user_id=user_id,
                operation="confirmation_round.draft.updated",
                object_type="confirmation_round",
                object_id=round_id,
                object_version_id=version_id,
                trace_id=trace_id,
                command_id=command,
                response_data=response_data,
                aggregate_type="confirmation_round",
                aggregate_version=expected + 1,
                event_name="confirmation_round.draft.updated",
                event_payload={"schema_version": "implementation_confirmation.mvp3.v1"},
                project_id=int(project_version["project_id"]),
                project_version_id=int(plan["project_version_id"]),
            )
            return response_data

    def confirm_round(
        self, *, round_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        payload = _exact(payload, {"expected_version"}, "ConfirmConfirmationRound")
        expected = _expected(payload["expected_version"])
        round_id = _id(round_id, "id")
        endpoint = f"confirmConfirmationRound:/api/v1/confirmation-rounds/{round_id}:confirm"
        request = {"expected_version": expected}
        try:
            with transaction() as connection:
                identity = _mapping(
                    connection.execute(
                        _sql("SELECT implementation_plan_id FROM confirmation_round WHERE id=:id"),
                        {"id": round_id},
                    )
                )
                if not identity:
                    raise ApiError("NOT_FOUND", "Confirmation round was not found", 404)
                plan = self._plan(connection, int(identity["implementation_plan_id"]), lock=True)
                project_version = _project_version(connection, int(plan["project_version_id"]))
                _access(
                    connection,
                    project_id=int(project_version["project_id"]),
                    user_id=user_id,
                    allowed={"owner"},
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                _source_live_guard(
                    connection,
                    project_version_id=int(plan["project_version_id"]),
                    source_prd_version_id=int(plan["source_prd_version_id"]),
                    source_review_id=int(plan["source_design_review_id"]),
                )
                row = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM confirmation_round WHERE id=:id FOR UPDATE"),
                        {"id": round_id},
                    )
                )
                if not row or int(row["implementation_plan_id"]) != int(plan["id"]):
                    raise ApiError("NOT_FOUND", "Confirmation round was not found", 404)
                if row["status"] != "draft":
                    raise ApiError(
                        "CONFIRMATION_NOT_DRAFT", "Confirmation round is not a draft", 409
                    )
                if int(row["row_version"]) != expected:
                    raise ApiError("VERSION_CONFLICT", "Confirmation round has changed", 409)
                readiness = _readiness(row["readiness_json"])
                if (
                    readiness["scope_status"] != "ready"
                    or readiness["implementation_status"] != "ready"
                    or readiness["configuration_status"] not in {"ready", "not_applicable"}
                    or readiness["data_change_status"] not in {"ready", "not_applicable"}
                    or readiness["known_blockers"]
                ):
                    raise ApiError(
                        "READINESS_INCOMPLETE", "Readiness completion predicate is false", 409
                    )
                current = _mapping(
                    connection.execute(
                        _sql(
                            "SELECT * FROM implementation_plan_version "
                            "WHERE id=:id AND implementation_plan_id=:plan_id "
                            "AND is_effective=1"
                        ),
                        {"id": row["plan_version_id"], "plan_id": plan["id"]},
                    )
                )
                if not current or int(plan["current_version_id"] or 0) != int(
                    row["plan_version_id"]
                ):
                    raise ApiError(
                        "PLAN_VERSION_NOT_CURRENT",
                        "Confirmation is not bound to the effective current version",
                        409,
                    )
                now = _now()
                previous = _mapping(
                    connection.execute(
                        _sql(
                            "SELECT * FROM confirmation_round "
                            "WHERE implementation_plan_id=:id AND status='confirmed' "
                            "AND id<>:current ORDER BY round_no DESC LIMIT 1 FOR UPDATE"
                        ),
                        {"id": plan["id"], "current": round_id},
                    )
                )
                if previous:
                    connection.execute(
                        _sql(
                            "UPDATE confirmation_round SET status='superseded',"
                            "is_effective=0,superseded_at=:now WHERE id=:id"
                        ),
                        {"now": now, "id": previous["id"]},
                    )
                connection.execute(
                    _sql(
                        "UPDATE confirmation_round SET status='confirmed',"
                        "confirm_status='confirmed',is_effective=1,confirmed_by=:uid,"
                        "confirmed_at=:now,row_version=row_version+1,updated_at=:now,"
                        "updated_by=:uid WHERE id=:id AND row_version=:expected"
                    ),
                    {"uid": user_id, "now": now, "id": round_id, "expected": expected},
                )
                updated = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM confirmation_round WHERE id=:id"), {"id": round_id}
                    )
                )
                response_data = {"confirmation_round": _round(updated)}
                command = f"cmd_{uuid.uuid4().hex}"
                audit_id = _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="confirmation_round.confirmed",
                    object_type="confirmation_round",
                    object_id=round_id,
                    object_version_id=int(row["plan_version_id"]),
                    trace_id=trace_id,
                    command_id=command,
                    response_data=response_data,
                    aggregate_type="confirmation_round",
                    aggregate_version=expected + 1,
                    event_name="confirmation_round.confirmed",
                    event_payload={"schema_version": "implementation_confirmation.mvp3.v1"},
                    project_id=int(project_version["project_id"]),
                    project_version_id=int(plan["project_version_id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"audit:{audit_id}",
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def list_test_records(self, *, round_id: int, user_id: int) -> dict[str, Any]:
        round_id = _id(round_id, "round_id")
        with readonly() as connection:
            context = _mapping(
                connection.execute(
                    _sql(
                        "SELECT r.id,v.id AS project_version_id,v.project_id FROM confirmation_round r "
                        "JOIN implementation_plan p ON p.id=r.implementation_plan_id "
                        "JOIN project_version v ON v.id=p.project_version_id "
                        "WHERE r.id=:id AND p.archived_at IS NULL AND v.archived_at IS NULL"
                    ),
                    {"id": round_id},
                )
            )
            if not context:
                raise ApiError("NOT_FOUND", "Confirmation round was not found", 404)
            _read_access(connection, project_id=int(context["project_id"]), user_id=user_id)
            rows = (
                connection.execute(
                    _sql(
                        "SELECT * FROM test_record WHERE confirmation_round_id=:round_id "
                        "ORDER BY (submitted_at IS NULL),submitted_at DESC,id DESC"
                    ),
                    {"round_id": round_id},
                )
                .mappings()
                .all()
            )
            return {
                "items": [
                    _test_record(
                        {
                            **dict(row),
                            "project_id": context["project_id"],
                            "project_version_id": context["project_version_id"],
                        }
                    )
                    for row in rows
                ]
            }

    def create_test_record(
        self, *, round_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        payload = _exact(
            payload,
            {"title", "scope", "environment", "steps", "expected_result", "actual_result", "result_status"},
            "CreateTestRecord",
        )
        round_id = _id(round_id, "round_id")
        request = {
            "title": _test_title(payload["title"]),
            "scope": _test_text(payload["scope"], "scope"),
            "environment": _test_environment(payload["environment"]),
            "steps": _test_steps(payload["steps"]),
            "expected_result": _test_text(payload["expected_result"], "expected_result"),
            "actual_result": _test_text(payload["actual_result"], "actual_result"),
            "result_status": _test_result_status(payload["result_status"]),
        }
        endpoint = f"createConfirmationRoundTestRecord:/api/v1/confirmation-rounds/{round_id}/test-records"
        try:
            with transaction() as connection:
                # Resolve the project context before validating the source state.
                # This keeps non-members on the anti-enumeration path and avoids
                # exposing whether a hidden round is confirmed/effective.
                source = _test_source_guard(connection, round_id, validate=False)
                roles = _access(
                    connection,
                    project_id=int(source["project_id"]),
                    user_id=user_id,
                    allowed={"owner", "tester"},
                    lock=True,
                )
                replay = _idem_begin(
                    connection, user_id=user_id, endpoint=endpoint, key=key, payload=request
                )
                if replay:
                    return _snapshot_replay(connection, replay)
                source = _test_source_guard(connection, round_id, lock=True)
                now = _now()
                result = connection.execute(
                    _sql(
                        "INSERT INTO test_record "
                        "(created_at,created_by,updated_at,updated_by,row_version,"
                        "confirmation_round_id,supersedes_test_record_id,title,test_type,scope,"
                        "environment_json,steps_json,expected_result,actual_result,result_status,"
                        "no_issue_conclusion,tester_id,submitted_at) "
                        "VALUES (:now,:uid,:now,:uid,1,:round_id,NULL,:title,'manual',:scope,"
                        ":environment,:steps,:expected,:actual,:result_status,0,:uid,NULL)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "round_id": round_id,
                        "title": request["title"],
                        "scope": request["scope"],
                        "environment": _canonical(request["environment"]),
                        "steps": _canonical(request["steps"]),
                        "expected": request["expected_result"],
                        "actual": request["actual_result"],
                        "result_status": request["result_status"],
                    },
                )
                record_id = int(result.lastrowid)
                row = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM test_record WHERE id=:id"), {"id": record_id}
                    )
                )
                row["project_id"] = source["project_id"]
                row["project_version_id"] = source["project_version_id"]
                response_data = {"test_record": _test_record(row)}
                command = f"cmd_{uuid.uuid4().hex}"
                _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="test.record.created",
                    object_type="test_record",
                    object_id=record_id,
                    object_version_id=int(row["row_version"]),
                    trace_id=trace_id,
                    command_id=command,
                    response_data=None,
                    audit_metadata={
                        "schema_version": "test_record.mvp4.audit.v1",
                        "actual_role": _write_role(roles),
                        "test_record_id": record_id,
                        "row_version": int(row["row_version"]),
                    },
                    aggregate_type="test_record",
                    aggregate_version=int(row["row_version"]),
                    event_name="test.record.created",
                    event_payload={"schema_version": "test_record.mvp4.v1", "row_version": 1},
                    project_id=int(source["project_id"]),
                    project_version_id=int(source["project_version_id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"test_record:{record_id}",
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def get_test_record(self, *, record_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            row = _test_record_identity(connection, _id(record_id, "id"))
            _read_access(connection, project_id=int(row["project_id"]), user_id=user_id)
            return {"test_record": _test_record(row)}

    def update_test_record(
        self, *, record_id: int, user_id: int, payload: dict[str, Any], trace_id: str
    ) -> dict[str, Any]:
        allowed_fields = {
            "expected_version",
            "scope",
            "environment",
            "steps",
            "expected_result",
            "actual_result",
            "result_status",
        }
        if (
            not isinstance(payload, dict)
            or "expected_version" not in payload
            or not set(payload).issubset(allowed_fields)
        ):
            raise ApiError("VALIDATION_ERROR", "UpdateTestRecord request fields are invalid", 422)
        writable = set(payload) - {"expected_version"}
        if not writable:
            raise ApiError("VALIDATION_ERROR", "At least one draft field is required", 422)
        expected = _expected(payload["expected_version"])
        values: dict[str, Any] = {}
        if "scope" in payload:
            values["scope"] = _test_text(payload["scope"], "scope")
        if "environment" in payload:
            values["environment_json"] = _canonical(_test_environment(payload["environment"]))
        if "steps" in payload:
            values["steps_json"] = _canonical(_test_steps(payload["steps"]))
        if "expected_result" in payload:
            values["expected_result"] = _test_text(payload["expected_result"], "expected_result")
        if "actual_result" in payload:
            values["actual_result"] = _test_text(payload["actual_result"], "actual_result")
        if "result_status" in payload:
            values["result_status"] = _test_result_status(payload["result_status"])
        record_id = _id(record_id, "id")
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
                _test_source_guard(connection, int(identity["confirmation_round_id"]), lock=True)
                row = _test_record_identity(connection, record_id, lock=True)
                if row["submitted_at"] is not None:
                    raise ApiError("TEST_RECORD_SUBMITTED", "Submitted Test Record is read-only", 409)
                if int(row["row_version"]) != expected:
                    raise ApiError(
                        "VERSION_CONFLICT",
                        "Test Record has changed",
                        409,
                        [{"field": "row_version", "reason": f"latest={row['row_version']}"}],
                    )
                now = _now()
                assignments = [f"{field}=:{field}" for field in values]
                assignments.extend(["row_version=row_version+1", "updated_at=:now", "updated_by=:uid"])
                params = {**values, "id": record_id, "now": now, "uid": user_id}
                connection.execute(
                    _sql(f"UPDATE test_record SET {','.join(assignments)} WHERE id=:id"), params
                )
                updated = _test_record_identity(connection, record_id, lock=True)
                response_data = {"test_record": _test_record(updated)}
                command = f"cmd_{uuid.uuid4().hex}"
                _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="test.record.draft.updated",
                    object_type="test_record",
                    object_id=record_id,
                    object_version_id=int(updated["row_version"]),
                    trace_id=trace_id,
                    command_id=command,
                    response_data=None,
                    audit_metadata={
                        "schema_version": "test_record.mvp4.audit.v1",
                        "actual_role": _write_role(roles),
                        "test_record_id": record_id,
                        "row_version": int(updated["row_version"]),
                    },
                    aggregate_type="test_record",
                    aggregate_version=int(updated["row_version"]),
                    event_name="test.record.draft.updated",
                    event_payload={
                        "schema_version": "test_record.mvp4.v1",
                        "row_version": int(updated["row_version"]),
                    },
                    project_id=int(updated["project_id"]),
                    project_version_id=int(updated["project_version_id"]),
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    def submit_test_record(
        self, *, record_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str
    ) -> dict[str, Any]:
        payload = _exact(payload, {"expected_version"}, "SubmitTestRecord")
        expected = _expected(payload["expected_version"])
        record_id = _id(record_id, "id")
        endpoint = f"submitTestRecord:/api/v1/test-records/{record_id}:submit"
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
                _test_source_guard(connection, int(identity["confirmation_round_id"]), lock=True)
                row = _test_record_identity(connection, record_id, lock=True)
                if row["submitted_at"] is not None:
                    raise ApiError("TEST_RECORD_SUBMITTED", "Submitted Test Record is read-only", 409)
                if int(row["row_version"]) != expected:
                    raise ApiError(
                        "VERSION_CONFLICT",
                        "Test Record has changed",
                        409,
                        [{"field": "row_version", "reason": f"latest={row['row_version']}"}],
                    )
                if not _test_complete(row):
                    raise ApiError("TEST_RECORD_INCOMPLETE", "Test Record facts are incomplete", 409)
                now = _now()
                connection.execute(
                    _sql(
                        "UPDATE test_record SET submitted_at=:now,row_version=row_version+1,"
                        "updated_at=:now,updated_by=:uid WHERE id=:id"
                    ),
                    {"now": now, "uid": user_id, "id": record_id},
                )
                updated = _test_record_identity(connection, record_id, lock=True)
                response_data = {"test_record": _test_record(updated)}
                command = f"cmd_{uuid.uuid4().hex}"
                _persist_command(
                    connection,
                    actor_user_id=user_id,
                    operation="test.record.submitted",
                    object_type="test_record",
                    object_id=record_id,
                    object_version_id=int(updated["row_version"]),
                    trace_id=trace_id,
                    command_id=command,
                    response_data=None,
                    audit_metadata={
                        "schema_version": "test_record.mvp4.audit.v1",
                        "actual_role": _write_role(roles),
                        "test_record_id": record_id,
                        "row_version": int(updated["row_version"]),
                    },
                    aggregate_type="test_record",
                    aggregate_version=int(updated["row_version"]),
                    event_name="test.record.submitted",
                    event_payload={
                        "schema_version": "test_record.mvp4.v1",
                        "row_version": int(updated["row_version"]),
                    },
                    project_id=int(updated["project_id"]),
                    project_version_id=int(updated["project_version_id"]),
                )
                _idem_complete(
                    connection,
                    user_id=user_id,
                    endpoint=endpoint,
                    key=key,
                    response_ref=f"test_record:{record_id}",
                )
                return response_data
        except (IntegrityError, OperationalError) as exc:
            raise _map_database_error(exc) from exc

    # Explicit aliases keep the service vocabulary readable to callers that
    # use the frozen operation names while retaining the concise adapter names.
    create_implementation_plan = create_plan
    create_implementation_plan_version = create_plan_version
    set_effective_implementation_plan_version = set_effective
    list_implementation_plan_confirmation_rounds = list_rounds
    create_implementation_plan_confirmation_round = create_round
    get_confirmation_round = get_round
    update_confirmation_round_draft = update_round
    confirm_confirmation_round = confirm_round
    list_confirmation_round_test_records = list_test_records
    create_confirmation_round_test_record = create_test_record
    get_test_record_resource = get_test_record
    update_test_record_draft = update_test_record
    submit_test_record_command = submit_test_record


service = ConfirmationService()
