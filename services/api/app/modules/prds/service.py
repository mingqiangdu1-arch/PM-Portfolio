from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.prds.domain import (
    DesignReviewStatus,
    PrdContentValidationError,
    PrdStatus,
    ReviewDecision,
    validate_prd_content,
)
from app.platform.database import readonly, transaction
from app.platform.errors import ApiError


def _sql(statement: str) -> Any:
    from sqlalchemy import text

    return text(statement)


def _mapping(result: Any) -> dict[str, Any] | None:
    row = result.mappings().first()
    return dict(row) if row else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _command_id() -> str:
    return f"cmd_{uuid.uuid4().hex}"


def _content(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return validate_prd_content(value)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ApiError(code="VALIDATION_ERROR", message=f"{field} must be a string", http_status=422)
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip()
    if not normalized:
        raise ApiError(code="VALIDATION_ERROR", message=f"{field} must not be blank", http_status=422)
    return normalized


def _require_exact_keys(payload: Any, *, required: set[str], command: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != required:
        raise ApiError(
            code="VALIDATION_ERROR",
            message=f"{command} request fields are invalid",
            http_status=422,
        )
    return payload


def _idempotency_begin(
    connection: Any, *, user_id: int, endpoint: str, key: str, payload: dict[str, Any]
) -> str | None:
    digest = _hash(payload)
    now = _now()
    inserted = connection.execute(
        _sql(
            "INSERT IGNORE INTO idempotency_record "
            "(user_id,endpoint_key,idempotency_key,request_hash,status,response_code,response_ref,created_at,expires_at) "
            "VALUES (:user_id,:endpoint,:key,:digest,'in_progress',NULL,NULL,:created_at,:expires_at)"
        ),
        {
            "user_id": user_id,
            "endpoint": endpoint,
            "key": key,
            "digest": digest,
            "created_at": now,
            "expires_at": now + timedelta(days=1),
        },
    ).rowcount == 1
    row = _mapping(
        connection.execute(
            _sql(
                "SELECT request_hash,status,response_ref FROM idempotency_record "
                "WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key FOR UPDATE"
            ),
            {"user_id": user_id, "endpoint": endpoint, "key": key},
        )
    )
    if not row or row["request_hash"] != digest or not inserted and row["status"] != "completed":
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="Idempotency-Key conflicts with an existing command",
            http_status=409,
        )
    return str(row["response_ref"]) if row["status"] == "completed" else None


def _idempotency_complete(
    connection: Any, *, user_id: int, endpoint: str, key: str, response_ref: int
) -> None:
    connection.execute(
        _sql(
            "UPDATE idempotency_record SET status='completed',response_code='OK',response_ref=:ref "
            "WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key"
        ),
        {"ref": str(response_ref), "user_id": user_id, "endpoint": endpoint, "key": key},
    )


def _project_version(connection: Any, version_id: int) -> dict[str, Any]:
    row = _mapping(
        connection.execute(
            _sql("SELECT id,project_id FROM project_version WHERE id=:id"), {"id": version_id}
        )
    )
    if not row:
        raise ApiError(code="NOT_FOUND", message="Project version was not found", http_status=404)
    return row


def _roles(connection: Any, *, project_id: int, user_id: int) -> list[str]:
    rows = connection.execute(
        _sql(
            "SELECT role_code FROM project_member "
            "WHERE project_id=:project_id AND user_id=:user_id AND status='active'"
        ),
        {"project_id": project_id, "user_id": user_id},
    ).mappings().all()
    if not rows:
        raise ApiError(code="NOT_FOUND", message="Project resource was not found", http_status=404)
    return [str(row["role_code"]) for row in rows]


def _require_access(connection: Any, *, project_id: int, user_id: int, write: bool) -> list[str]:
    roles = _roles(connection, project_id=project_id, user_id=user_id)
    if write and "owner" not in roles:
        raise ApiError(code="FORBIDDEN", message="Owner role is required", http_status=403)
    return roles


def _prd(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "project_version_id": str(row["project_version_id"]),
        "source_requirement_version_id": str(row["source_requirement_version_id"]),
        "name": row["name"],
        "status": row["status"],
        "current_version_id": str(row["current_version_id"])
        if row["current_version_id"] is not None
        else None,
        "row_version": int(row["row_version"]),
    }


def _prd_version(row: dict[str, Any]) -> dict[str, Any]:
    content = _content(row["content_json"])
    return {
        "id": str(row["id"]),
        "prd_id": str(row["prd_id"]),
        "source_version_id": str(row["source_version_id"])
        if row["source_version_id"] is not None
        else None,
        "version_no": str(row["version_no"]),
        "content_json": content,
        "content_hash": row["content_hash"],
        "is_effective": bool(row["is_effective"]),
    }


def _review(row: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "project_version_id": str(row["project_version_id"]),
        "round_no": int(row["round_no"]),
        "status": row["status"],
        "summary": row["summary"],
        "row_version": int(row["row_version"]),
        "scope": {
            "prd_id": str(scope["object_id"]),
            "prd_version_id": str(scope["object_version_id"]),
            "content_hash": scope["content_hash"],
        },
    }


def _current_review(connection: Any, *, prd: dict[str, Any]) -> dict[str, Any] | None:
    current_version_id = prd.get("current_version_id")
    if current_version_id is None:
        return None
    candidates = connection.execute(
        _sql(
            "SELECT dr.id FROM design_review dr "
            "JOIN design_review_scope scope ON scope.design_review_id=dr.id "
            "JOIN prd_version version ON version.id=scope.object_version_id "
            "WHERE dr.archived_at IS NULL AND dr.project_version_id=:project_version_id "
            "AND scope.object_type='PRD' AND scope.object_id=:prd_id "
            "AND scope.object_version_id=:version_id AND version.prd_id=:prd_id "
            "AND scope.content_hash=version.content_hash"
        ),
        {
            "project_version_id": int(prd["project_version_id"]),
            "prd_id": int(prd["id"]),
            "version_id": int(current_version_id),
        },
    ).mappings().all()
    if len(candidates) > 1:
        raise ApiError(
            code="INVALID_STATE",
            message="Current PRD version is bound to multiple design reviews",
            http_status=409,
        )
    if not candidates:
        if prd["status"] in {
            PrdStatus.IN_REVIEW.value,
            PrdStatus.CHANGES_REQUESTED.value,
            PrdStatus.CONFIRMED.value,
        }:
            raise ApiError(
                code="INVALID_STATE",
                message="Current PRD review relation is missing",
                http_status=409,
            )
        return None
    review_id = int(candidates[0]["id"])
    review = _mapping(
        connection.execute(
            _sql("SELECT * FROM design_review WHERE id=:id AND archived_at IS NULL"),
            {"id": review_id},
        )
    )
    scope = _mapping(
        connection.execute(
            _sql(
                "SELECT * FROM design_review_scope WHERE design_review_id=:review_id "
                "AND object_type='PRD' AND object_id=:prd_id AND object_version_id=:version_id"
            ),
            {
                "review_id": review_id,
                "prd_id": int(prd["id"]),
                "version_id": int(current_version_id),
            },
        )
    )
    if not review or not scope:
        raise ApiError(
            code="INVALID_STATE",
            message="Current PRD review relation is incomplete",
            http_status=409,
        )
    return _review(review, scope)


def _audit_and_outbox(
    connection: Any,
    *,
    user_id: int,
    project_id: int,
    project_version_id: int,
    prd_id: int,
    version_id: int | None,
    aggregate_version: int,
    event_name: str,
    trace_id: str,
) -> None:
    now = _now()
    command_id = _command_id()
    connection.execute(
        _sql(
            "INSERT INTO operation_audit_log "
            "(retention_class,expires_at,actor_user_id,actor_type,operation_name,object_type,object_id,object_version_id,"
            "result_status,failure_code,reason_summary,trace_id,command_id,occurred_at,metadata_json) VALUES "
            "('audit',NULL,:user_id,'user',:event_name,'prd',:prd_id,:version_id,"
            "'success',NULL,NULL,:trace_id,:command_id,:occurred_at,:metadata)"
        ),
        {
            "user_id": user_id,
            "event_name": event_name,
            "prd_id": prd_id,
            "version_id": version_id,
            "trace_id": trace_id,
            "command_id": command_id,
            "occurred_at": now,
            "metadata": json.dumps({"schema_version": "prd.mvp2.v1"}, separators=(",", ":")),
        },
    )
    envelope = {
        "schema_version": "0.2.0",
        "event_id": str(uuid.uuid4()),
        "event_name": event_name,
        "occurred_at": _iso(now),
        "producer": "Business API",
        "module": "product_design",
        "result_status": "success",
        "source_type": "server",
        "privacy_class": "internal_id",
        "user_id": str(user_id),
        "project_id": str(project_id),
        "project_version_id": str(project_version_id),
        "object_type": "prd",
        "object_id": str(prd_id),
        "object_version_id": str(version_id) if version_id is not None else None,
        "trace_id": trace_id,
        "command_id": command_id,
        "payload_json": {"schema_version": "prd.mvp2.v1"},
    }
    connection.execute(
        _sql(
            "INSERT INTO business_event_outbox "
            "(event_id,aggregate_type,aggregate_id,aggregate_version,event_name,schema_version,payload_json,publish_status,"
            "attempt_count,next_attempt_at,published_at,created_at) VALUES "
            "(:event_id,'prd',:prd_id,:aggregate_version,:event_name,'0.2.0',:payload,'pending',0,NULL,NULL,:created_at)"
        ),
        {
            "event_id": envelope["event_id"],
            "prd_id": prd_id,
            "aggregate_version": aggregate_version,
            "event_name": event_name,
            "payload": json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
            "created_at": now,
        },
    )


class PrdService:
    def list_prds(self, *, version_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            project_version = _project_version(connection, version_id)
            _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=False)
            rows = connection.execute(
                _sql("SELECT * FROM prd WHERE project_version_id=:version_id AND archived_at IS NULL ORDER BY id"),
                {"version_id": version_id},
            ).mappings().all()
            return {"items": [_prd(dict(row)) for row in rows], "has_more": False}

    def get_prd(self, *, prd_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            prd = _mapping(connection.execute(_sql("SELECT * FROM prd WHERE id=:id AND archived_at IS NULL"), {"id": prd_id}))
            if not prd:
                raise ApiError(code="NOT_FOUND", message="PRD was not found", http_status=404)
            project_version = _project_version(connection, int(prd["project_version_id"]))
            _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=False)
            return {"prd": _prd(prd), "design_review": _current_review(connection, prd=prd)}

    def get_version(self, *, version_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            version = _mapping(connection.execute(_sql("SELECT * FROM prd_version WHERE id=:id"), {"id": version_id}))
            if not version:
                raise ApiError(code="NOT_FOUND", message="PRD version was not found", http_status=404)
            prd = _mapping(connection.execute(_sql("SELECT * FROM prd WHERE id=:id AND archived_at IS NULL"), {"id": version["prd_id"]}))
            if not prd:
                raise ApiError(code="NOT_FOUND", message="PRD was not found", http_status=404)
            project_version = _project_version(connection, int(prd["project_version_id"]))
            _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=False)
            return {"prd_version": _prd_version(version)}

    def create_prd(self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        payload = _require_exact_keys(
            payload,
            required={"source_requirement_version_id", "name"},
            command="Create PRD",
        )
        source_id = payload.get("source_requirement_version_id")
        if not isinstance(source_id, str) or not source_id.isdigit():
            raise ApiError(code="VALIDATION_ERROR", message="source_requirement_version_id must be an ID", http_status=422)
        name = _text(payload.get("name"), "name")
        endpoint = f"POST:/api/v1/project-versions/{version_id}/prds"
        with transaction() as connection:
            project_version = _project_version(connection, version_id)
            _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=True)
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload={"source_requirement_version_id": source_id, "name": name})
            if replay:
                prd = _mapping(connection.execute(_sql("SELECT * FROM prd WHERE id=:id"), {"id": int(replay)}))
                if not prd:
                    raise ApiError(code="NOT_FOUND", message="PRD was not found", http_status=404)
                return {"prd": _prd(prd), "design_review": None}
            existing = _mapping(connection.execute(_sql("SELECT id FROM prd WHERE project_version_id=:version_id AND is_main=1 AND archived_at IS NULL FOR UPDATE"), {"version_id": version_id}))
            if existing:
                raise ApiError(code="INVALID_STATE", message="A main PRD already exists", http_status=409)
            source = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:id"), {"id": int(source_id)}))
            requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:id"), {"id": source["requirement_id"]})) if source else None
            if not source or not requirement or int(requirement["project_version_id"]) != version_id:
                raise ApiError(code="NOT_FOUND", message="Source Requirement version was not found", http_status=404)
            if source["confirmation_status"] != "confirmed" or not bool(source["is_effective"]):
                raise ApiError(code="INVALID_STATE", message="Source Requirement version must be confirmed and effective", http_status=409)
            now = _now()
            result = connection.execute(
                _sql(
                    "INSERT INTO prd (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,"
                    "project_version_id,source_requirement_version_id,name,prd_type,is_main,status,current_version_id) VALUES "
                    "(:now,:user_id,:now,:user_id,1,NULL,NULL,:version_id,:source_id,:name,'prd',1,'draft',NULL)"
                ),
                {"now": now, "user_id": user_id, "version_id": version_id, "source_id": int(source_id), "name": name},
            )
            prd_id = int(result.lastrowid)
            _audit_and_outbox(connection, user_id=user_id, project_id=int(project_version["project_id"]), project_version_id=version_id, prd_id=prd_id, version_id=None, aggregate_version=1, event_name="prd.created", trace_id=trace_id)
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=prd_id)
            prd = _mapping(connection.execute(_sql("SELECT * FROM prd WHERE id=:id"), {"id": prd_id}))
            assert prd is not None
            return {"prd": _prd(prd), "design_review": None}

    def save_version(self, *, prd_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        payload = _require_exact_keys(
            payload,
            required={"expected_version", "content_json", "change_note"},
            command="Create PRD version",
        )
        expected = payload.get("expected_version")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise ApiError(code="VALIDATION_ERROR", message="expected_version must be positive", http_status=422)
        try:
            content = validate_prd_content(payload.get("content_json"))
        except PrdContentValidationError as exc:
            raise ApiError(code="VALIDATION_ERROR", message=str(exc), http_status=422) from exc
        change_note = _text(payload.get("change_note"), "change_note")
        endpoint = f"POST:/api/v1/prds/{prd_id}/versions"
        with transaction() as connection:
            prd = _mapping(connection.execute(_sql("SELECT * FROM prd WHERE id=:id AND archived_at IS NULL FOR UPDATE"), {"id": prd_id}))
            if not prd:
                raise ApiError(code="NOT_FOUND", message="PRD was not found", http_status=404)
            project_version = _project_version(connection, int(prd["project_version_id"]))
            _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=True)
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload={"expected_version": expected, "content_json": content, "change_note": change_note})
            if replay:
                version = _mapping(connection.execute(_sql("SELECT * FROM prd_version WHERE id=:id"), {"id": int(replay)}))
                if not version:
                    raise ApiError(code="NOT_FOUND", message="PRD version was not found", http_status=404)
                return {"prd_version": _prd_version(version)}
            if int(prd["row_version"]) != expected:
                raise ApiError(code="VERSION_CONFLICT", message="PRD has changed", http_status=409)
            if prd["status"] not in {PrdStatus.DRAFT.value, PrdStatus.CHANGES_REQUESTED.value}:
                raise ApiError(code="INVALID_STATE", message="PRD cannot be saved in its current state", http_status=409)
            latest = _mapping(connection.execute(_sql("SELECT version_no FROM prd_version WHERE prd_id=:prd_id ORDER BY id DESC LIMIT 1"), {"prd_id": prd_id}))
            version_no = int(str(latest["version_no"])) + 1 if latest else 1
            now = _now()
            content_hash = _hash(content)
            result = connection.execute(
                _sql(
                    "INSERT INTO prd_version (created_at,created_by,prd_id,source_version_id,version_no,content_format,"
                    "content_json,rendered_summary,content_hash,change_note,created_from_ai_result_id,is_effective) VALUES "
                    "(:now,:user_id,:prd_id,:source_version_id,:version_no,'json',:content,NULL,:content_hash,:change_note,NULL,0)"
                ),
                {"now": now, "user_id": user_id, "prd_id": prd_id, "source_version_id": prd["current_version_id"], "version_no": str(version_no), "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")), "content_hash": content_hash, "change_note": change_note},
            )
            version_id = int(result.lastrowid)
            connection.execute(_sql("UPDATE prd SET current_version_id=:version_id,status='draft',row_version=row_version+1,updated_at=:now,updated_by=:user_id WHERE id=:prd_id"), {"version_id": version_id, "now": now, "user_id": user_id, "prd_id": prd_id})
            _audit_and_outbox(connection, user_id=user_id, project_id=int(project_version["project_id"]), project_version_id=int(prd["project_version_id"]), prd_id=prd_id, version_id=version_id, aggregate_version=expected + 1, event_name="prd.version.created", trace_id=trace_id)
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=version_id)
            version = _mapping(connection.execute(_sql("SELECT * FROM prd_version WHERE id=:id"), {"id": version_id}))
            assert version is not None
            return {"prd_version": _prd_version(version)}

    def submit_review(self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        payload = _require_exact_keys(
            payload,
            required={"prd_id", "prd_version_id", "content_hash", "expected_version"},
            command="Submit design review",
        )
        expected = payload.get("expected_version")
        prd_id = payload.get("prd_id")
        prd_version_id = payload.get("prd_version_id")
        content_hash = payload.get("content_hash")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1 or not all(isinstance(value, str) and value.isdigit() for value in (prd_id, prd_version_id)) or not isinstance(content_hash, str) or re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
            raise ApiError(code="VALIDATION_ERROR", message="Invalid review submission", http_status=422)
        endpoint = f"POST:/api/v1/project-versions/{version_id}/design-reviews"
        with transaction() as connection:
            project_version = _project_version(connection, version_id)
            _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=True)
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            if replay:
                return self._review_for_user(connection, review_id=int(replay), user_id=user_id)
            prd = _mapping(connection.execute(_sql("SELECT * FROM prd WHERE id=:id AND archived_at IS NULL FOR UPDATE"), {"id": int(prd_id)}))
            prd_version = _mapping(connection.execute(_sql("SELECT * FROM prd_version WHERE id=:id"), {"id": int(prd_version_id)}))
            if not prd or not prd_version or int(prd["project_version_id"]) != version_id or int(prd_version["prd_id"]) != int(prd["id"]):
                raise ApiError(code="NOT_FOUND", message="PRD review target was not found", http_status=404)
            if int(prd["row_version"]) != expected:
                raise ApiError(code="VERSION_CONFLICT", message="PRD has changed", http_status=409)
            if prd["status"] != PrdStatus.DRAFT.value or int(prd["current_version_id"] or 0) != int(prd_version_id):
                raise ApiError(code="INVALID_STATE", message="Only the current draft version may be submitted", http_status=409)
            if prd_version["content_hash"] != content_hash:
                raise ApiError(code="VALIDATION_ERROR", message="PRD version content hash does not match", http_status=422)
            latest = _mapping(connection.execute(_sql("SELECT round_no FROM design_review WHERE project_version_id=:version_id ORDER BY round_no DESC LIMIT 1 FOR UPDATE"), {"version_id": version_id}))
            round_no = int(latest["round_no"]) + 1 if latest else 1
            now = _now()
            result = connection.execute(_sql("INSERT INTO design_review (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,round_no,status,summary,submitted_at,passed_at,submitted_by,passed_by) VALUES (:now,:user_id,:now,:user_id,1,NULL,NULL,:version_id,:round_no,'open',NULL,:now,NULL,:user_id,NULL)"), {"now": now, "user_id": user_id, "version_id": version_id, "round_no": round_no})
            review_id = int(result.lastrowid)
            connection.execute(_sql("INSERT INTO design_review_scope (created_at,created_by,design_review_id,object_type,object_id,object_version_id,content_hash) VALUES (:now,:user_id,:review_id,'PRD',:prd_id,:version_id,:content_hash)"), {"now": now, "user_id": user_id, "review_id": review_id, "prd_id": int(prd_id), "version_id": int(prd_version_id), "content_hash": content_hash})
            connection.execute(_sql("UPDATE prd SET status='in_review',row_version=row_version+1,updated_at=:now,updated_by=:user_id WHERE id=:prd_id"), {"now": now, "user_id": user_id, "prd_id": int(prd_id)})
            _audit_and_outbox(connection, user_id=user_id, project_id=int(project_version["project_id"]), project_version_id=version_id, prd_id=int(prd_id), version_id=int(prd_version_id), aggregate_version=expected + 1, event_name="prd.review.submitted", trace_id=trace_id)
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=review_id)
            return self._review_for_user(connection, review_id=review_id, user_id=user_id)

    def _review_for_user(self, connection: Any, *, review_id: int, user_id: int) -> dict[str, Any]:
        review = _mapping(connection.execute(_sql("SELECT * FROM design_review WHERE id=:id AND archived_at IS NULL"), {"id": review_id}))
        scope = _mapping(connection.execute(_sql("SELECT * FROM design_review_scope WHERE design_review_id=:id AND object_type='PRD'"), {"id": review_id}))
        if not review or not scope:
            raise ApiError(code="NOT_FOUND", message="Design review was not found", http_status=404)
        project_version = _project_version(connection, int(review["project_version_id"]))
        _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=False)
        return {"design_review": _review(review, scope)}

    def get_review(self, *, review_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            return self._review_for_user(connection, review_id=review_id, user_id=user_id)

    def decide_review(self, *, review_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiError(code="VALIDATION_ERROR", message="Invalid review decision", http_status=422)
        expected = payload.get("expected_version")
        decision = payload.get("decision")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1 or decision not in {item.value for item in ReviewDecision}:
            raise ApiError(code="VALIDATION_ERROR", message="Invalid review decision", http_status=422)
        required = {"expected_version", "decision", "summary"} if decision == ReviewDecision.CHANGES_REQUESTED.value else {"expected_version", "decision"}
        payload = _require_exact_keys(payload, required=required, command="Decide design review")
        summary: str | None = None
        if decision == ReviewDecision.CHANGES_REQUESTED.value:
            summary = _text(payload.get("summary"), "summary")
        endpoint = f"POST:/api/v1/design-reviews/{review_id}:decide"
        with transaction() as connection:
            review = _mapping(connection.execute(_sql("SELECT * FROM design_review WHERE id=:id AND archived_at IS NULL FOR UPDATE"), {"id": review_id}))
            if not review:
                raise ApiError(code="NOT_FOUND", message="Design review was not found", http_status=404)
            project_version = _project_version(connection, int(review["project_version_id"]))
            _require_access(connection, project_id=int(project_version["project_id"]), user_id=user_id, write=True)
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            if replay:
                return self._review_for_user(connection, review_id=int(replay), user_id=user_id)
            if int(review["row_version"]) != expected:
                raise ApiError(code="VERSION_CONFLICT", message="Design review has changed", http_status=409)
            if review["status"] != DesignReviewStatus.OPEN.value:
                raise ApiError(code="INVALID_STATE", message="Design review is not open", http_status=409)
            scope = _mapping(connection.execute(_sql("SELECT * FROM design_review_scope WHERE design_review_id=:id AND object_type='PRD' FOR UPDATE"), {"id": review_id}))
            if not scope:
                raise ApiError(code="NOT_FOUND", message="Design review scope was not found", http_status=404)
            prd = _mapping(connection.execute(_sql("SELECT * FROM prd WHERE id=:id AND archived_at IS NULL FOR UPDATE"), {"id": scope["object_id"]}))
            prd_version = _mapping(connection.execute(_sql("SELECT * FROM prd_version WHERE id=:id"), {"id": scope["object_version_id"]}))
            if not prd or not prd_version or int(prd["project_version_id"]) != int(review["project_version_id"]) or int(prd_version["prd_id"]) != int(prd["id"]) or prd_version["content_hash"] != scope["content_hash"]:
                raise ApiError(code="INVALID_STATE", message="Design review scope is no longer valid", http_status=409)
            now = _now()
            if decision == ReviewDecision.CHANGES_REQUESTED.value:
                connection.execute(_sql("UPDATE design_review SET status='changes_requested',summary=:summary,row_version=row_version+1,updated_at=:now,updated_by=:user_id WHERE id=:review_id"), {"summary": summary, "now": now, "user_id": user_id, "review_id": review_id})
                connection.execute(_sql("UPDATE prd SET status='changes_requested',row_version=row_version+1,updated_at=:now,updated_by=:user_id WHERE id=:prd_id"), {"now": now, "user_id": user_id, "prd_id": prd["id"]})
                event_name = "prd.review.changes_requested"
                aggregate_version = int(prd["row_version"]) + 1
            else:
                connection.execute(_sql("UPDATE design_review SET status='passed',summary=NULL,passed_at=:now,passed_by=:user_id,row_version=row_version+1,updated_at=:now,updated_by=:user_id WHERE id=:review_id"), {"now": now, "user_id": user_id, "review_id": review_id})
                connection.execute(_sql("UPDATE prd_version SET is_effective=0 WHERE prd_id=:prd_id"), {"prd_id": prd["id"]})
                connection.execute(_sql("UPDATE prd_version SET is_effective=1 WHERE id=:version_id AND prd_id=:prd_id"), {"version_id": prd_version["id"], "prd_id": prd["id"]})
                connection.execute(_sql("UPDATE prd SET current_version_id=:version_id,status='confirmed',row_version=row_version+1,updated_at=:now,updated_by=:user_id WHERE id=:prd_id"), {"version_id": prd_version["id"], "now": now, "user_id": user_id, "prd_id": prd["id"]})
                event_name = "prd.confirmed"
                aggregate_version = int(prd["row_version"]) + 1
            _audit_and_outbox(connection, user_id=user_id, project_id=int(project_version["project_id"]), project_version_id=int(review["project_version_id"]), prd_id=int(prd["id"]), version_id=int(prd_version["id"]), aggregate_version=aggregate_version, event_name=event_name, trace_id=trace_id)
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=review_id)
            return self._review_for_user(connection, review_id=review_id, user_id=user_id)
