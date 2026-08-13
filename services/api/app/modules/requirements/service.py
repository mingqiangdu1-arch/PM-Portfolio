from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
import unicodedata
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from app.platform.database import readonly, transaction
from app.platform.config import get_settings
from app.platform.errors import ApiError
from app.platform.storage import S3Signer
from app.platform.sprint2_contract import SPRINT2_SCHEMAS


DIMENSIONS = (
    "goal",
    "users_and_roles",
    "usage_scenarios",
    "functional_scope",
    "business_rules",
    "exception_cases",
    "permission_requirements",
    "acceptance_criteria",
)


def _sql(statement: str) -> Any:
    from sqlalchemy import text

    return text(statement)


def _mapping(result: Any) -> dict[str, Any] | None:
    row = result.mappings().first()
    return dict(row) if row else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _request_hash(payload: dict[str, Any]) -> str:
    return _canonical_hash(payload)


def _command_id() -> str:
    return f"cmd_{uuid.uuid4().hex}"


def _idempotency_begin(connection: Any, *, user_id: int, endpoint: str, key: str, payload: dict[str, Any]) -> str | None:
    digest = _request_hash(payload)
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
    if not row:
        raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Idempotency record unavailable", http_status=503)
    if row["request_hash"] != digest:
        raise ApiError(code="IDEMPOTENCY_CONFLICT", message="Key was used with another request", http_status=409)
    if row["status"] == "completed":
        return str(row["response_ref"])
    if not inserted:
        raise ApiError(code="IDEMPOTENCY_CONFLICT", message="The same command is still in progress", http_status=409)
    return None


def _idempotency_complete(connection: Any, *, user_id: int, endpoint: str, key: str, response_ref: str) -> None:
    result = connection.execute(
        _sql(
            "UPDATE idempotency_record SET status='completed',response_code='OK',response_ref=:ref "
            "WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key"
        ),
        {"ref": response_ref, "user_id": user_id, "endpoint": endpoint, "key": key},
    )
    if getattr(result, "rowcount", 1) != 1:
        raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Idempotency record could not be completed", http_status=503)


def _audit(connection: Any, *, user_id: int, requirement_id: int, version_id: int, trace_id: str, command_id: str, operation: str = "requirement.create") -> None:
    connection.execute(
        _sql(
            "INSERT INTO operation_audit_log "
            "(retention_class,expires_at,actor_user_id,actor_type,operation_name,object_type,object_id,object_version_id,"
            "result_status,failure_code,reason_summary,trace_id,command_id,occurred_at,metadata_json) VALUES "
            "('audit',NULL,:uid,'user',:operation,'requirement',:rid,:vid,'success',NULL,NULL,:trace,:command,:at,:metadata)"
        ),
        {
            "uid": user_id,
            "operation": operation,
            "rid": requirement_id,
            "vid": version_id,
            "trace": trace_id,
            "command": command_id,
            "at": _now(),
            "metadata": json.dumps({"source_type": "manual"}, separators=(",", ":")),
        },
    )


def _outbox(
    connection: Any,
    *,
    user_id: int,
    project_id: int,
    project_version_id: int,
    requirement_id: int,
    version_id: int,
    aggregate_version: int,
    content_hash: str,
    trace_id: str,
    command_id: str,
) -> None:
    event_id = str(uuid.uuid4())
    occurred = _iso(_now())
    payload = {"artifact_type": "requirement", "draft_version_id": str(version_id), "content_hash": content_hash}
    envelope = {
        "schema_version": "0.2.0",
        "event_id": event_id,
        "event_name": "artifact.draft.saved",
        "occurred_at": occurred,
        "producer": "Business API",
        "module": "product_design",
        "result_status": "success",
        "source_type": "server",
        "privacy_class": "internal_id",
        "user_id": str(user_id),
        "project_id": str(project_id),
        "project_version_id": str(project_version_id),
        "object_type": "requirement",
        "object_id": str(requirement_id),
        "object_version_id": str(version_id),
        "trace_id": trace_id,
        "command_id": command_id,
        "payload_json": payload,
    }
    connection.execute(
        _sql(
            "INSERT INTO business_event_outbox "
            "(event_id,aggregate_type,aggregate_id,aggregate_version,event_name,schema_version,payload_json,publish_status,"
            "attempt_count,next_attempt_at,published_at,created_at) VALUES "
            "(:event_id,'requirement',:rid,:aggregate_version,'artifact.draft.saved','0.2.0',:payload,'pending',0,NULL,NULL,:created_at)"
        ),
        {"event_id": event_id, "rid": requirement_id, "aggregate_version": aggregate_version, "payload": json.dumps(envelope, ensure_ascii=False, separators=(",", ":")), "created_at": _now()},
    )


def _confirmation_outbox(
    connection: Any,
    *,
    user_id: int,
    project_id: int,
    project_version_id: int,
    requirement_id: int,
    version_id: int,
    version_no: str,
    aggregate_version: int,
    content_hash: str,
    gate_result: str,
    accepted_risk_count: int,
    unresolved_count: int,
    trace_id: str,
    command_id: str,
) -> None:
    event_id = str(uuid.uuid4())
    occurred_at = _now()
    event_payload = {
        "requirement_version_id": str(version_id),
        "requirement_version_no": str(version_no),
        "content_hash": content_hash,
        "confirmation_status": "confirmed",
        "gate_result": gate_result,
        "accepted_risk_count": accepted_risk_count,
        "unresolved_count": unresolved_count,
    }
    envelope = {
        "schema_version": "0.2.0",
        "event_id": event_id,
        "event_name": "requirement.version.confirmed",
        "occurred_at": _iso(occurred_at),
        "producer": "Business API",
        "module": "product_design",
        "result_status": "success",
        "source_type": "server",
        "privacy_class": "internal_id",
        "user_id": str(user_id),
        "project_id": str(project_id),
        "project_version_id": str(project_version_id),
        "object_type": "requirement",
        "object_id": str(requirement_id),
        "object_version_id": str(version_id),
        "trace_id": trace_id,
        "command_id": command_id,
        "payload_json": event_payload,
    }
    result = connection.execute(
        _sql(
            "INSERT INTO business_event_outbox "
            "(event_id,aggregate_type,aggregate_id,aggregate_version,event_name,schema_version,payload_json,publish_status,"
            "attempt_count,next_attempt_at,published_at,created_at) VALUES "
            "(:event_id,'requirement',:rid,:aggregate_version,'requirement.version.confirmed','0.2.0',:payload,'pending',0,NULL,NULL,:created_at)"
        ),
        {
            "event_id": event_id,
            "rid": requirement_id,
            "aggregate_version": aggregate_version,
            "payload": json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
            "created_at": occurred_at,
        },
    )
    if getattr(result, "rowcount", 1) != 1:
        raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Confirmation event could not be recorded", http_status=503)


def _unresolved_code(value: str) -> tuple[str, str]:
    canonical = unicodedata.normalize("NFC", value.strip())
    if not canonical:
        raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Unresolved item must not be blank", http_status=422)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return canonical, digest


class _AiResultContentReader:
    """Minimal storage boundary used by confirmation without importing ai_tasks."""

    def read_json(self, content_ref: str) -> Any:
        settings = get_settings()
        if not (settings.object_storage_access_key and settings.object_storage_secret_key):
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI result content reader is not configured", http_status=503)
        signer = S3Signer(
            endpoint=settings.object_storage_endpoint,
            bucket=settings.object_storage_bucket,
            region=settings.object_storage_region,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
        )
        signed = signer.presign(method="GET", object_key=content_ref, expires_seconds=60)
        try:
            with urllib.request.urlopen(
                urllib.request.Request(signed.url, method="GET", headers=signed.required_headers), timeout=10
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI result content is unavailable", http_status=503) from exc


def _empty_content(raw_input: str, *, requirement_id: int, title: str) -> tuple[dict[str, Any], str]:
    raw_ref = {
        "source_type": "manual",
        "source_id": str(requirement_id),
        "source_version_id": None,
        "content_hash": hashlib.sha256(raw_input.encode("utf-8")).hexdigest(),
        "label": title,
    }
    baseline_dimension = {
        "confirmed_facts": [],
        "source_refs": [],
        "deferred_items": [],
        "not_applicable_items": [],
    }
    content = {
        "raw_input": raw_input,
        "raw_input_ref": raw_ref,
        "clarification": {
            "mode": "auto",
            "assessment": None,
            "assessment_ref": None,
            "assessment_summary": None,
            "rounds": [],
            "finish_reason": None,
            "continue_deep_confirmed": False,
        },
        "baseline": {
            "dimensions": {dimension: dict(baseline_dimension) for dimension in DIMENSIONS},
            "assumptions": [],
            "unresolved_items": [],
        },
    }
    return content, _canonical_hash(content)


_CONTRACT_VALIDATORS = {
    schema_name: Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"#/components/schemas/{schema_name}",
            "components": {"schemas": SPRINT2_SCHEMAS},
        }
    )
    for schema_name in (
        "RequirementContent",
        "CreateRequirementRequest",
        "ReviseRequirementVersionRequest",
        "SetClarificationModeRequest",
        "SubmitClarificationAnswersRequest",
        "ConfirmRequirementVersionRequest",
    )
}


def _validate_contract(value: Any, schema_name: str) -> None:
    try:
        _CONTRACT_VALIDATORS[schema_name].validate(value)
    except ValidationError:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Request does not match the frozen schema",
            http_status=422,
        ) from None


def _permission(roles: list[str], row_version: int) -> dict[str, Any]:
    return {
        "roles": roles,
        "allowed_actions": ["requirement:view", "requirement:create", "requirement:update", "requirement:confirm"],
        "permission_version": max(1, int(row_version)),
    }


def _version(row: dict[str, Any], content: dict[str, Any] | None = None) -> dict[str, Any]:
    if content is not None:
        clarification = content.setdefault("clarification", {})
        clarification.setdefault("continue_deep_confirmed", False)
    risk_acceptances = row.get("risk_acceptance_json") or []
    if isinstance(risk_acceptances, str):
        risk_acceptances = json.loads(risk_acceptances)
    return {
        "id": str(row["id"]),
        "requirement_id": str(row["requirement_id"]),
        "source_version_id": str(row["source_version_id"]) if row.get("source_version_id") is not None else None,
        "version_no": row["version_no"],
        "content_format": row["content_format"],
        "content_json": content if content is not None else row["content_json"],
        "content_hash": row["content_hash"],
        "confirmation_status": row["confirmation_status"],
        "unresolved_count": int(row["unresolved_count"]),
        "risk_acceptances": risk_acceptances,
        "created_from_ai_result_id": str(row["created_from_ai_result_id"]) if row.get("created_from_ai_result_id") is not None else None,
        "is_effective": bool(row["is_effective"]),
        "created_at": _iso(row["created_at"]),
    }


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "project_version_id": str(row["project_version_id"]),
        "title": row["title"],
        "source_type": row["source_type"],
        "priority": row["priority"],
        "status": row["status"],
        "current_version_id": str(row["current_version_id"]) if row.get("current_version_id") is not None else None,
        "effective_version_id": None,
        "updated_at": _iso(row["updated_at"]),
        "version": int(row["row_version"]),
    }


class RequirementService:
    def __init__(self, *, content_reader: Any | None = None) -> None:
        # Tests and alternate storage implementations can inject this narrow
        # dependency; production uses the existing S3-compatible boundary.
        self.content_reader = content_reader or _AiResultContentReader()

    @staticmethod
    def _risk_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
        value = row.get("risk_acceptance_json") or []
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Stored risk acceptance is invalid", http_status=422) from None
        if not isinstance(value, list):
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Stored risk acceptance is invalid", http_status=422)
        codes: set[str] = set()
        for item in value:
            if not isinstance(item, dict) or not isinstance(item.get("missing_item_code"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["missing_item_code"]):
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Stored risk acceptance is invalid", http_status=422)
            if item["missing_item_code"] in codes:
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Stored risk acceptance is ambiguous", http_status=422)
            codes.add(item["missing_item_code"])
        return value

    @classmethod
    def _stored_gate_result(cls, row: dict[str, Any]) -> tuple[str, int, int]:
        risks = cls._risk_rows(row)
        unresolved_count = int(row.get("unresolved_count") or 0)
        accepted_count = len(risks)
        if unresolved_count and accepted_count != unresolved_count:
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Stored risk acceptance is incomplete", http_status=422)
        return ("passed_with_risk" if accepted_count else "passed", accepted_count, unresolved_count)

    def _read_linked_ai_result(self, result_id: Any, *, requirement: dict[str, Any], addressed: dict[str, Any]) -> dict[str, Any]:
        """Read immutable AI metadata/content before acquiring business locks."""
        with readonly() as connection:
            metadata = _mapping(
                connection.execute(
                    _sql(
                        "SELECT ar.*,at.task_public_id,at.target_object_id,at.target_object_version_id,"
                        "at.target_snapshot_hash AS task_target_snapshot_hash "
                        "FROM ai_result ar JOIN ai_call ac ON ac.id=ar.ai_call_id "
                        "JOIN ai_task at ON at.id=ac.ai_task_id WHERE ar.id=:result_id"
                    ),
                    {"result_id": result_id},
                )
            )
        if not metadata:
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result is unavailable", http_status=422)
        content = metadata.get("content_json")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (TypeError, ValueError, json.JSONDecodeError):
                content = None
        if content is None:
            content_ref = metadata.get("content_ref")
            if not content_ref:
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result content is unavailable", http_status=422)
            if hasattr(self.content_reader, "read_json"):
                content = self.content_reader.read_json(str(content_ref))
            else:
                content = self.content_reader(str(content_ref))
        try:
            Draft202012Validator(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$ref": "#/components/schemas/AiResultContent",
                    "components": {"schemas": SPRINT2_SCHEMAS},
                }
            ).validate(content)
        except ValidationError:
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result content is invalid", http_status=422) from None
        fingerprint = metadata.get("content_fingerprint") or metadata.get("fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint) or _canonical_hash(content) != fingerprint:
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result fingerprint is invalid", http_status=422)
        target_hash = str(addressed.get("content_hash"))
        if (
            content.get("status") != "ready"
            or metadata.get("status") != "ready"
            or str(content.get("target_snapshot_hash")) != target_hash
            or str(metadata.get("target_snapshot_hash")) != target_hash
            or str(metadata.get("task_target_snapshot_hash")) != target_hash
            or str(content.get("task_public_id")) != str(metadata.get("task_public_id"))
            or str(metadata.get("target_object_id")) != str(requirement.get("id"))
            or str(metadata.get("target_object_version_id")) != str(addressed.get("id"))
        ):
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result target is inconsistent", http_status=422)
        quality = content.get("quality")
        if not isinstance(quality, dict) or (
            quality.get("format_status") != "passed"
            or quality.get("traceability_status") != "passed"
            or quality.get("safety_status") != "passed"
            or quality.get("major_error") is not False
            or quality.get("required_items_met") != quality.get("required_items_total")
        ):
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result quality is not trusted", http_status=422)
        blockers = quality.get("blocker_codes")
        if not isinstance(blockers, list) or any(not isinstance(code, str) or not re.fullmatch(r"[0-9a-f]{64}", code) for code in blockers) or len(blockers) != len(set(blockers)):
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result blocker codes are invalid", http_status=422)
        return {"metadata": metadata, "content": content, "blocker_codes": set(blockers)}

    def list_requirements(self, *, version_id: int, user_id: int, status: str | None = None) -> dict[str, Any]:
        with readonly() as connection:
            project_version = _mapping(
                connection.execute(
                    _sql("SELECT id,project_id FROM project_version WHERE id=:id"),
                    {"id": version_id},
                )
            )
            if not project_version:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            memberships = connection.execute(
                _sql("SELECT role_code,row_version FROM project_member WHERE project_id=:project_id AND user_id=:user_id AND status='active'"),
                {"project_id": project_version["project_id"], "user_id": user_id},
            ).mappings().all()
            if not memberships:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)

            statement = "SELECT * FROM requirement WHERE project_version_id=:version_id"
            params: dict[str, Any] = {"version_id": version_id}
            if status is not None:
                statement += " AND status=:status"
                params["status"] = status
            rows = connection.execute(
                _sql(statement + " ORDER BY updated_at DESC, id DESC"),
                params,
            ).mappings().all()
            return {"items": [_summary(dict(row)) for row in rows], "next_cursor": None, "has_more": False}

    def get_requirement(self, *, requirement_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            requirement = _mapping(
                connection.execute(
                    _sql("SELECT * FROM requirement WHERE id=:requirement_id"),
                    {"requirement_id": requirement_id},
                )
            )
            if not requirement:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            project_version = _mapping(
                connection.execute(
                    _sql("SELECT id,project_id FROM project_version WHERE id=:id"),
                    {"id": requirement["project_version_id"]},
                )
            )
            if not project_version:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            memberships = connection.execute(
                _sql("SELECT role_code,row_version FROM project_member WHERE project_id=:project_id AND user_id=:user_id AND status='active'"),
                {"project_id": project_version["project_id"], "user_id": user_id},
            ).mappings().all()
            if not memberships:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            roles = [str(item["role_code"]) for item in memberships]
            current = None
            if requirement.get("current_version_id") is not None:
                current = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM requirement_version WHERE id=:id"),
                        {"id": requirement["current_version_id"]},
                    )
                )
                if not current:
                    raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Requirement version unavailable", http_status=503)
            effective = _mapping(
                connection.execute(
                    _sql("SELECT * FROM requirement_version WHERE requirement_id=:requirement_id AND is_effective=1 ORDER BY id DESC LIMIT 1"),
                    {"requirement_id": requirement_id},
                )
            )

        def version_view(row: dict[str, Any] | None) -> dict[str, Any] | None:
            if not row:
                return None
            content = row.get("content_json")
            if isinstance(content, str):
                content = json.loads(content)
            return _version(row, content)

        summary = _summary(requirement)
        summary["effective_version_id"] = str(effective["id"]) if effective else None
        return {
            "requirement": summary,
            "current_version": version_view(current),
            "effective_version": version_view(effective),
            "permissions": _permission(roles, requirement["row_version"]),
        }

    def confirm(self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        _validate_contract(payload, "ConfirmRequirementVersionRequest")
        expected = payload.get("expected_version")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise ApiError(code="VALIDATION_ERROR", message="expected_version must be a positive integer", http_status=422)
        risk_acceptances = payload.get("risk_acceptances")
        if not isinstance(risk_acceptances, list):
            raise ApiError(code="VALIDATION_ERROR", message="risk_acceptances must be an array", http_status=422)

        endpoint = f"POST:/api/v1/requirement-versions/{version_id}:confirm"

        # Locate immutable facts without holding a transaction lock.  A
        # completed idempotency key or an already-effective version can be
        # replayed/no-op'd from stored business facts and does not need a
        # second object-store read.
        with readonly() as probe:
            probe_version = _mapping(probe.execute(_sql("SELECT * FROM requirement_version WHERE id=:id"), {"id": version_id}))
            if not probe_version:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            probe_requirement = _mapping(probe.execute(_sql("SELECT * FROM requirement WHERE id=:id"), {"id": probe_version["requirement_id"]}))
            if not probe_requirement:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            idem_probe = _mapping(
                probe.execute(
                    _sql("SELECT request_hash,status,response_ref FROM idempotency_record WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key"),
                    {"user_id": user_id, "endpoint": endpoint, "key": key},
                )
            )
        linked_facts = None
        if (
            probe_version.get("created_from_ai_result_id") is not None
            and not (idem_probe and idem_probe.get("status") == "completed")
            and not (probe_version.get("confirmation_status") == "confirmed" and bool(probe_version.get("is_effective")))
        ):
            linked_facts = self._read_linked_ai_result(
                probe_version["created_from_ai_result_id"], requirement=probe_requirement, addressed=probe_version
            )

        with transaction() as connection:
            # Lock order is part of the confirmation contract: requirement
            # aggregate first, then the addressed version.
            requirement = _mapping(
                connection.execute(
                    _sql("SELECT * FROM requirement WHERE id=:id FOR UPDATE"),
                    {"id": probe_version["requirement_id"]},
                )
            )
            if not requirement:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            addressed = _mapping(
                connection.execute(
                    _sql("SELECT * FROM requirement_version WHERE id=:id FOR UPDATE"),
                    {"id": version_id},
                )
            )
            if not addressed:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            if str(addressed.get("requirement_id")) != str(requirement.get("id")):
                raise ApiError(code="VERSION_CONFLICT", message="Requirement version is not current", http_status=409)
            # Re-check immutable facts after acquiring locks.  The pre-read is
            # intentionally outside the transaction to avoid network I/O while
            # locked, so any drift is a fail-closed dependency conflict.
            if linked_facts is not None:
                linked_metadata = linked_facts["metadata"]
                if (
                    str(addressed.get("created_from_ai_result_id")) != str(linked_metadata.get("id"))
                    or str(addressed.get("content_hash")) != str(probe_version.get("content_hash"))
                    or str(requirement.get("id")) != str(probe_requirement.get("id"))
                ):
                    raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Linked AI result changed", http_status=422)
            project_version = _mapping(
                connection.execute(
                    _sql("SELECT id,project_id FROM project_version WHERE id=:id"),
                    {"id": requirement["project_version_id"]},
                )
            )
            if not project_version:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            memberships = connection.execute(
                _sql("SELECT role_code FROM project_member WHERE project_id=:project_id AND user_id=:user_id AND status='active'"),
                {"project_id": project_version["project_id"], "user_id": user_id},
            ).mappings().all()
            if not memberships:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            if "owner" not in {str(item["role_code"]) for item in memberships}:
                raise ApiError(code="FORBIDDEN", message="Project role does not allow this action", http_status=403)

            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            if replay:
                replay_row = _mapping(
                    connection.execute(
                        _sql("SELECT * FROM requirement_version WHERE id=:id"),
                        {"id": replay},
                    )
                )
                if not replay_row or replay_row.get("confirmation_status") != "confirmed" or not replay_row.get("is_effective"):
                    raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Confirmed version is unavailable", http_status=503)
                replay_content = replay_row.get("content_json")
                if isinstance(replay_content, str):
                    replay_content = json.loads(replay_content)
                gate_result, accepted_count, unresolved_count = self._stored_gate_result(replay_row)
                return {"effective_version": _version(replay_row, replay_content), "gate_result": gate_result}

            if str(requirement.get("current_version_id")) != str(addressed["id"]):
                raise ApiError(code="VERSION_CONFLICT", message="Requirement version is not current", http_status=409)
            if int(requirement["row_version"]) != expected:
                raise ApiError(code="VERSION_CONFLICT", message="Requirement has changed", http_status=409)

            # A fresh idempotency key against the already-effective version is
            # a side-effect-free no-op.  Its gate is derived from the persisted
            # risk acceptance facts; do not re-read AI content or re-run gates.
            if addressed.get("confirmation_status") == "confirmed" and bool(addressed.get("is_effective")):
                replay_content = addressed.get("content_json")
                if isinstance(replay_content, str):
                    replay_content = json.loads(replay_content)
                stored_gate, _, _ = self._stored_gate_result(addressed)
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(addressed["id"]))
                return {"effective_version": _version(addressed, replay_content), "gate_result": stored_gate}

            content = addressed.get("content_json")
            if isinstance(content, str):
                content = json.loads(content)
            _validate_contract(content, "RequirementContent")
            unresolved_items = content["baseline"]["unresolved_items"]
            unresolved_pairs = [_unresolved_code(item) for item in unresolved_items]
            canonical_items = [item[0] for item in unresolved_pairs]
            if len(canonical_items) != len(set(canonical_items)):
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Unresolved items are ambiguous", http_status=422)
            unresolved_codes = {item[1] for item in unresolved_pairs}
            if len(unresolved_codes) != len(unresolved_pairs):
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Unresolved item digest is ambiguous", http_status=422)
            acceptance_codes = [str(item["missing_item_code"]) for item in risk_acceptances]
            if any(not re.fullmatch(r"[0-9a-f]{64}", code) for code in acceptance_codes):
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Risk acceptance code is invalid", http_status=422)
            if len(acceptance_codes) != len(set(acceptance_codes)):
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Risk acceptance is ambiguous", http_status=422)
            if any(code not in unresolved_codes for code in acceptance_codes):
                raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Risk acceptance does not match an unresolved item", http_status=422)

            # AI quality is authoritative only for the immutable result linked
            # to this version.  Non-empty unresolved content without a trusted
            # result fails closed.
            blocker_codes: set[str] = set(unresolved_codes) if unresolved_codes else set()
            if unresolved_codes:
                if addressed.get("created_from_ai_result_id") is None or linked_facts is None:
                    raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Unresolved items require a trusted AI result", http_status=422)
                blocker_codes = set(linked_facts["blocker_codes"])
                if not blocker_codes.issubset(unresolved_codes):
                    raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="AI blocker code is not an unresolved item", http_status=422)
                if blocker_codes:
                    raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Unresolved blocker requires resolution", http_status=422)
                # Every remaining unresolved item must be accepted exactly once
                # and may only be accepted at low impact.
                if set(acceptance_codes) != unresolved_codes:
                    raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Every unresolved item requires one acceptance", http_status=422)
                if any(item.get("impact") != "low" for item in risk_acceptances):
                    raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Risk acceptance impact must be low", http_status=422)
                gate_result = "passed_with_risk"
            else:
                if risk_acceptances:
                    raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Risk acceptance does not match an unresolved item", http_status=422)
                gate_result = "passed"

            now = _now()
            connection.execute(
                _sql("UPDATE requirement_version SET is_effective=0 WHERE requirement_id=:rid AND is_effective=1 AND id<>:vid"),
                {"rid": requirement["id"], "vid": addressed["id"]},
            )
            confirmed = connection.execute(
                _sql(
                    "UPDATE requirement_version SET confirmation_status='confirmed',is_effective=1,risk_acceptance_json=:risk "
                    "WHERE id=:vid AND requirement_id=:rid"
                ),
                {"risk": json.dumps(risk_acceptances, ensure_ascii=False, separators=(",", ":")), "vid": addressed["id"], "rid": requirement["id"]},
            )
            if getattr(confirmed, "rowcount", 1) != 1:
                raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Requirement version could not be confirmed", http_status=503)
            updated = connection.execute(
                _sql(
                    "UPDATE requirement SET status='effective',row_version=row_version+1,updated_at=:now,updated_by=:uid "
                    "WHERE id=:rid AND current_version_id=:vid AND row_version=:expected"
                ),
                {"now": now, "uid": user_id, "rid": requirement["id"], "vid": addressed["id"], "expected": expected},
            )
            if getattr(updated, "rowcount", 1) != 1:
                raise ApiError(code="VERSION_CONFLICT", message="Requirement has changed", http_status=409)
            command_id = _command_id()
            _audit(
                connection,
                user_id=user_id,
                requirement_id=int(requirement["id"]),
                version_id=int(addressed["id"]),
                trace_id=trace_id,
                command_id=command_id,
                operation="requirement.version.confirmed",
            )
            _confirmation_outbox(
                connection,
                user_id=user_id,
                project_id=int(project_version["project_id"]),
                project_version_id=int(requirement["project_version_id"]),
                requirement_id=int(requirement["id"]),
                version_id=int(addressed["id"]),
                version_no=str(addressed["version_no"]),
                aggregate_version=expected + 1,
                content_hash=str(addressed["content_hash"]),
                gate_result=gate_result,
                accepted_risk_count=len(risk_acceptances),
                unresolved_count=len(unresolved_items),
                trace_id=trace_id,
                command_id=command_id,
            )
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(addressed["id"]))
            confirmed_row = dict(addressed)
            confirmed_row.update(
                confirmation_status="confirmed",
                is_effective=1,
                risk_acceptance_json=risk_acceptances,
            )
            return {"effective_version": _version(confirmed_row, content), "gate_result": gate_result}

    def set_clarification_mode(self, *, version_id: int, user_id: int, payload: dict[str, Any], trace_id: str, key: str | None = None) -> dict[str, Any]:
        _validate_contract(payload, "SetClarificationModeRequest")
        mode = payload.get("mode")
        expected = payload.get("expected_version")
        if mode not in {"auto", "standard", "deep", "skip"} or not isinstance(expected, int) or expected < 1:
            raise ApiError(code="VALIDATION_ERROR", message="Invalid clarification mode request", http_status=422)
        if mode == "skip" and not payload.get("reason"):
            raise ApiError(code="CLARIFICATION_MODE_REASON_REQUIRED", message="A reason is required when skipping clarification", http_status=422)
        with readonly() as connection:
            addressed = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:id"), {"id": version_id}))
            if not addressed:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:id"), {"id": addressed["requirement_id"]}))
            if not requirement:
                raise ApiError(code="VERSION_CONFLICT", message="Requirement has changed", http_status=409)
            content = addressed["content_json"]
            if isinstance(content, str):
                content = json.loads(content)
            else:
                content = deepcopy(content)
            content["clarification"]["mode"] = mode
            content["clarification"]["continue_deep_confirmed"] = False
            content["clarification"]["finish_reason"] = None
        return self.revise(version_id=version_id, user_id=user_id, payload={"expected_version": expected, "content_json": content}, trace_id=trace_id, endpoint=f"POST:/api/v1/requirement-versions/{version_id}:set-clarification-mode" if key else None, key=key, idempotency_payload=payload)

    def submit_clarification_answers(self, *, version_id: int, user_id: int, payload: dict[str, Any], trace_id: str, key: str | None = None) -> dict[str, Any]:
        _validate_contract(payload, "SubmitClarificationAnswersRequest")
        expected = payload.get("expected_version")
        round_no = payload.get("round_no")
        if not isinstance(expected, int) or expected < 1 or not isinstance(round_no, int) or not 1 <= round_no <= 5:
            raise ApiError(code="VALIDATION_ERROR", message="Invalid clarification answers request", http_status=422)
        with readonly() as connection:
            addressed = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:id"), {"id": version_id}))
            requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:id"), {"id": addressed["requirement_id"]})) if addressed else None
            if not addressed or not requirement:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            content = addressed["content_json"]
            if isinstance(content, str):
                content = json.loads(content)
            else:
                content = deepcopy(content)
            clarification = content["clarification"]
            mode = clarification.get("mode", "auto")
            confirmed = bool(clarification.get("continue_deep_confirmed", False))
            rounds = clarification.get("rounds") or []
            if clarification.get("finish_reason") is not None or not rounds or int(rounds[-1].get("round_no", 0)) != round_no:
                raise ApiError(code="CLARIFICATION_ROUND_INVALID", message="Clarification round is invalid", http_status=409)
            if mode in {"auto", "skip"}:
                raise ApiError(code="CLARIFICATION_ROUND_INVALID", message="Clarification round is invalid", http_status=409)
            if mode == "standard" and round_no > 3:
                raise ApiError(code="CLARIFICATION_ROUND_LIMIT_REACHED", message="Clarification round limit reached", http_status=409)
            if mode == "deep" and round_no > 5:
                raise ApiError(code="CLARIFICATION_ROUND_LIMIT_REACHED", message="Clarification round limit reached", http_status=409)
            if mode == "deep" and round_no >= 4 and not confirmed and not payload.get("continue_deep_confirmed", False):
                raise ApiError(code="DEEP_CONFIRMATION_REQUIRED", message="Deep clarification requires explicit confirmation", http_status=409)
            if payload.get("continue_deep_confirmed"):
                if mode != "deep" or round_no != 3 or payload.get("finish_now"):
                    raise ApiError(code="CLARIFICATION_ROUND_INVALID", message="Deep confirmation is not valid for this round", http_status=409)
                if confirmed or len(rounds) != 3:
                    raise ApiError(code="CLARIFICATION_ROUND_INVALID", message="Deep confirmation requires exactly three completed rounds", http_status=409)
                clarification["continue_deep_confirmed"] = True
            rounds = clarification.get("rounds") or []
            if rounds:
                latest = dict(rounds[-1])
                latest["round_no"] = round_no
                latest["answers"] = payload.get("answers") or latest.get("answers", [])
                rounds = [*rounds[:-1], latest]
            clarification["rounds"] = rounds
            if payload.get("finish_now"):
                clarification["finish_reason"] = "user_finished"
        version = self.revise(version_id=version_id, user_id=user_id, payload={"expected_version": expected, "content_json": content}, trace_id=trace_id, endpoint=f"POST:/api/v1/requirement-versions/{version_id}/clarification-answers" if key else None, key=key, idempotency_payload=payload)
        return {"requirement_version": version, "task_creation": {"decoupled": True, "create_operation": "POST /api/v1/ai/tasks"}, "baseline_candidate_ref": None}
    def create_requirement(self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        """Explicit command alias retained for callers that use resource verbs."""
        return self.create(version_id=version_id, user_id=user_id, payload=payload, key=key, trace_id=trace_id)

    def revise(self, *, version_id: int, user_id: int, payload: dict[str, Any], trace_id: str, endpoint: str | None = None, key: str | None = None, idempotency_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        _validate_contract(payload, "ReviseRequirementVersionRequest")
        expected = payload.get("expected_version")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise ApiError(code="VALIDATION_ERROR", message="expected_version must be a positive integer", http_status=422)
        title = payload.get("title")
        if title is not None and (not isinstance(title, str) or not 1 <= len(title) <= 200):
            raise ApiError(code="VALIDATION_ERROR", message="title must contain 1 to 200 characters", http_status=422)
        risk_supplied = "risk_acceptances" in payload
        risk = payload.get("risk_acceptances")
        if risk_supplied and not isinstance(risk, list):
            raise ApiError(code="VALIDATION_ERROR", message="risk_acceptances must be an array", http_status=422)
        content_supplied = "content_json" in payload
        supplied_content = payload.get("content_json")
        if content_supplied and not isinstance(supplied_content, dict):
            raise ApiError(code="VALIDATION_ERROR", message="content_json must be an object", http_status=422)
        with transaction() as connection:
            addressed = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:id"), {"id": version_id}))
            if not addressed:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:id FOR UPDATE"), {"id": addressed["requirement_id"]}))
            if not requirement:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            project_version = _mapping(connection.execute(_sql("SELECT id,project_id FROM project_version WHERE id=:id"), {"id": requirement["project_version_id"]}))
            if not project_version:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            memberships = connection.execute(
                _sql("SELECT role_code FROM project_member WHERE project_id=:project_id AND user_id=:user_id AND status='active'"),
                {"project_id": project_version["project_id"], "user_id": user_id},
            ).mappings().all()
            if not memberships:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            roles = [str(item["role_code"]) for item in memberships]
            if "owner" not in roles:
                raise ApiError(code="FORBIDDEN", message="Project role does not allow this action", http_status=403)
            if endpoint and key:
                replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=idempotency_payload or payload)
                if replay:
                    replay_row = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:id"), {"id": replay}))
                    if replay_row:
                        replay_content = replay_row.get("content_json")
                        if isinstance(replay_content, str): replay_content = json.loads(replay_content)
                        return _version(replay_row, replay_content)
                    raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Idempotency version is unavailable", http_status=503)
            if int(requirement["row_version"]) != expected:
                raise ApiError(code="VERSION_CONFLICT", message="Requirement has changed", http_status=409)
            old_content = addressed["content_json"]
            if isinstance(old_content, str):
                old_content = json.loads(old_content)
            if content_supplied:
                new_content = dict(supplied_content)
                if "raw_input" in new_content and new_content["raw_input"] != old_content.get("raw_input"):
                    raise ApiError(code="VALIDATION_ERROR", message="raw_input is immutable", http_status=422)
                if "raw_input_ref" in new_content and new_content["raw_input_ref"] != old_content.get("raw_input_ref"):
                    raise ApiError(code="VALIDATION_ERROR", message="raw_input_ref is immutable", http_status=422)
                new_content["raw_input"] = old_content.get("raw_input")
                new_content["raw_input_ref"] = old_content.get("raw_input_ref")
            else:
                new_content = old_content
            # R4 confirmation is an explicit persisted fact. Legacy content
            # remains false in memory; every newly materialized version writes
            # the boolean explicitly.
            old_flag = bool(old_content.get("clarification", {}).get("continue_deep_confirmed", False))
            new_mode = new_content.get("clarification", {}).get("mode")
            old_mode = old_content.get("clarification", {}).get("mode")
            if endpoint and endpoint.endswith("/clarification-answers"):
                pass
            elif endpoint and ":set-clarification-mode" in endpoint:
                new_content["clarification"]["continue_deep_confirmed"] = False
            else:
                new_content["clarification"]["continue_deep_confirmed"] = old_flag if new_mode == old_mode else False
            _validate_contract(new_content, "RequirementContent")
            content_hash = _canonical_hash(new_content)
            new_risk = risk if risk_supplied else (addressed.get("risk_acceptance_json") or None)
            if isinstance(new_risk, str):
                new_risk = json.loads(new_risk)
            latest = _mapping(connection.execute(_sql("SELECT version_no FROM requirement_version WHERE requirement_id=:rid ORDER BY id DESC LIMIT 1"), {"rid": requirement["id"]}))
            next_no = int(str(latest["version_no"]).lstrip("V")) + 1 if latest else 1
            now = _now()
            result = connection.execute(
                _sql(
                    "INSERT INTO requirement_version (created_at,created_by,requirement_id,source_version_id,version_no,content_format,"
                    "content_json,content_hash,confirmation_status,unresolved_count,risk_acceptance_json,created_from_ai_result_id,is_effective) "
                    "VALUES (:now,:uid,:rid,:source,:version_no,:format,:content,:hash,'draft',:unresolved,:risk,NULL,0)"
                ),
                {
                    "now": now, "uid": user_id, "rid": requirement["id"], "source": addressed["id"], "version_no": str(next_no),
                    "format": addressed["content_format"], "content": json.dumps(new_content, ensure_ascii=False, separators=(",", ":")),
                    "hash": content_hash, "unresolved": len(new_content.get("baseline", {}).get("unresolved_items", [])),
                    "risk": json.dumps(new_risk, ensure_ascii=False, separators=(",", ":")) if new_risk is not None else None,
                },
            )
            new_version_id = int(result.lastrowid)
            new_title = title if title is not None else requirement["title"]
            updated = connection.execute(
                _sql("UPDATE requirement SET title=:title,current_version_id=:vid,row_version=row_version+1,updated_at=:now,updated_by=:uid WHERE id=:rid AND row_version=:expected"),
                {"title": new_title, "vid": new_version_id, "now": now, "uid": user_id, "rid": requirement["id"], "expected": expected},
            )
            if getattr(updated, "rowcount", 1) != 1:
                raise ApiError(code="VERSION_CONFLICT", message="Requirement has changed", http_status=409)
            command_id = _command_id()
            _audit(connection, user_id=user_id, requirement_id=int(requirement["id"]), version_id=new_version_id, trace_id=trace_id, command_id=command_id, operation="requirement.version.revised")
            _outbox(connection, user_id=user_id, project_id=int(project_version["project_id"]), project_version_id=int(requirement["project_version_id"]), requirement_id=int(requirement["id"]), version_id=new_version_id, aggregate_version=expected + 1, content_hash=content_hash, trace_id=trace_id, command_id=command_id)
            if endpoint and key:
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(new_version_id))
            row = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:id"), {"id": new_version_id})) or {
                "id": new_version_id, "requirement_id": requirement["id"], "source_version_id": addressed["id"], "version_no": str(next_no),
                "content_format": addressed["content_format"], "content_json": new_content, "content_hash": content_hash,
                "confirmation_status": "draft", "unresolved_count": 0, "risk_acceptance_json": new_risk, "created_from_ai_result_id": None,
                "is_effective": 0, "created_at": now,
            }
            return _version(row, new_content)

    def create(self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        _validate_contract(payload, "CreateRequirementRequest")
        title = payload.get("title")
        raw_input = payload.get("raw_input")
        source_refs = payload.get("source_refs")
        if not isinstance(title, str) or not 1 <= len(title) <= 200:
            raise ApiError(code="VALIDATION_ERROR", message="title must contain 1 to 200 characters", http_status=422)
        if not isinstance(raw_input, str) or len(raw_input) < 1:
            raise ApiError(code="VALIDATION_ERROR", message="raw_input must contain at least 1 character", http_status=422)
        if not isinstance(source_refs, list):
            raise ApiError(code="VALIDATION_ERROR", message="source_refs must be an array", http_status=422)
        if source_refs:
            raise ApiError(code="VALIDATION_ERROR", message="source_refs is not supported in this slice", http_status=422)
        request_payload = {"title": title, "raw_input": raw_input, "source_refs": source_refs}
        endpoint = f"POST:/api/v1/project-versions/{version_id}/requirements"
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=request_payload)
            project_version = _mapping(
                connection.execute(_sql("SELECT id,project_id,row_version FROM project_version WHERE id=:id"), {"id": version_id})
            )
            if not project_version:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            memberships = connection.execute(
                _sql("SELECT role_code,row_version FROM project_member WHERE project_id=:project_id AND user_id=:user_id AND status='active'"),
                {"project_id": project_version["project_id"], "user_id": user_id},
            ).mappings().all()
            if not memberships:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            roles = [str(item["role_code"]) for item in memberships]
            if "owner" not in roles:
                raise ApiError(code="FORBIDDEN", message="Project role does not allow this action", http_status=403)
            if replay:
                requirement_id = int(replay)
            else:
                now = _now()
                result = connection.execute(
                    _sql(
                        "INSERT INTO requirement (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,"
                        "project_version_id,title,source_type,priority,status,current_version_id) VALUES "
                        "(:now,:uid,:now,:uid,1,NULL,NULL,:version_id,:title,'manual','normal','draft',NULL)"
                    ),
                    {"now": now, "uid": user_id, "version_id": version_id, "title": title},
                )
                requirement_id = int(result.lastrowid)
                content, content_hash = _empty_content(raw_input, requirement_id=requirement_id, title=title)
                result = connection.execute(
                    _sql(
                        "INSERT INTO requirement_version (created_at,created_by,requirement_id,source_version_id,version_no,content_format,"
                        "content_json,content_hash,confirmation_status,unresolved_count,risk_acceptance_json,created_from_ai_result_id,is_effective) "
                        "VALUES (:now,:uid,:rid,NULL,'1','json',:content,:content_hash,'draft',0,NULL,NULL,0)"
                    ),
                    {"now": now, "uid": user_id, "rid": requirement_id, "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")), "content_hash": content_hash},
                )
                version_pk = int(result.lastrowid)
                pointer = connection.execute(_sql("UPDATE requirement SET current_version_id=:vid WHERE id=:rid"), {"vid": version_pk, "rid": requirement_id})
                if getattr(pointer, "rowcount", 1) != 1:
                    raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Requirement pointer could not be updated", http_status=503)
                command_id = _command_id()
                _audit(connection, user_id=user_id, requirement_id=requirement_id, version_id=version_pk, trace_id=trace_id, command_id=command_id)
                _outbox(connection, user_id=user_id, project_id=int(project_version["project_id"]), project_version_id=version_id, requirement_id=requirement_id, version_id=version_pk, aggregate_version=1, content_hash=content_hash, trace_id=trace_id, command_id=command_id)
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(requirement_id))
            requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:rid"), {"rid": requirement_id}))
            if not requirement:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            current = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:vid"), {"vid": requirement["current_version_id"]}))
            if not current:
                raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Requirement version unavailable", http_status=503)
            content = current["content_json"]
            if isinstance(content, str):
                content = json.loads(content)
            return {"requirement": _summary(requirement), "current_version": _version(current, content), "effective_version": None, "permissions": _permission(roles, requirement["row_version"])}
