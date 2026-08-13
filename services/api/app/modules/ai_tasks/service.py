from __future__ import annotations

"""Business-side runtime bridge for the Requirement clarification slice.

The Business API deliberately never inserts rows in the AI-owned tables.  It
only derives a frozen envelope, calls the AI HTTP boundary, and reads AI facts
when a user asks for a candidate result.  Formalization is the one write path
and is kept in one Business transaction.
"""

import hashlib
import json
import secrets
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

from jsonschema import Draft202012Validator, ValidationError

from app.modules.requirements.service import (
    DIMENSIONS,
    _canonical_hash,
    _audit,
    _idempotency_begin,
    _idempotency_complete,
    _mapping,
    _now,
    _sql,
)
from app.platform.config import get_settings
from app.platform.database import readonly, transaction
from app.platform.errors import ApiError
from app.platform.security import decode_hs256
from app.platform.storage import S3Signer
from app.platform.sprint2_contract import SPRINT2_SCHEMAS


_REQ_CONTENT = Draft202012Validator({"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/components/schemas/RequirementContent", "components": {"schemas": SPRINT2_SCHEMAS}})
_RISK = Draft202012Validator({"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/components/schemas/RiskAcceptance", "components": {"schemas": SPRINT2_SCHEMAS}})
_CREATE_TASK = Draft202012Validator({"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/components/schemas/CreateAiTaskRequest", "components": {"schemas": SPRINT2_SCHEMAS}})
_ENVELOPE = Draft202012Validator({"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/components/schemas/RequirementClarifyTaskEnvelope", "components": {"schemas": SPRINT2_SCHEMAS}})
_FORMALIZE = Draft202012Validator({"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/components/schemas/FormalizeAiResultRequest", "components": {"schemas": SPRINT2_SCHEMAS}})
_STATUS_READY = {"ready"}
_INTERNAL_RESULT_REF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "ai_result_id", "ai_call_id", "result_no", "status",
        "target_snapshot_hash", "content_ref", "content_fingerprint",
    ],
    "properties": {
        "ai_result_id": {"type": "string", "pattern": "^[1-9][0-9]*$"},
        "ai_call_id": {"type": "string", "pattern": "^[1-9][0-9]*$"},
        "result_no": {"type": "integer", "minimum": 1},
        "status": SPRINT2_SCHEMAS["AiResultStatus"],
        "target_snapshot_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "content_ref": {"type": "string", "minLength": 1},
        "content_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
}
_INTERNAL_RESULT_REF = Draft202012Validator(_INTERNAL_RESULT_REF_SCHEMA)
_INTERNAL_TASK_RESPONSE = Draft202012Validator({
    "type": "object",
    "additionalProperties": False,
    "required": ["task_public_id", "status", "trace_id", "failure_code", "result_refs"],
    "properties": {
        "task_public_id": {"type": "string", "minLength": 1},
        "status": SPRINT2_SCHEMAS["AiTaskStatus"],
        "trace_id": {"type": "string", "minLength": 1},
        "failure_code": {"type": ["string", "null"]},
        "result_refs": {"type": "array", "items": _INTERNAL_RESULT_REF_SCHEMA},
    },
})


def _iso(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _safe_validation(value: Any, validator: Draft202012Validator, message: str = "Invalid runtime contract") -> None:
    try:
        validator.validate(value)
    except ValidationError as exc:
        raise ApiError(code="VALIDATION_ERROR", message=message, http_status=422) from exc


def _clarification_input(content: dict[str, Any]) -> dict[str, Any]:
    clarification = content["clarification"]
    mode = clarification.get("mode", "auto")
    rounds = clarification.get("rounds") or []
    confirmed = bool(clarification.get("continue_deep_confirmed", False))
    if mode in {"auto", "skip"}:
        return {"mode": mode, "round_no": 0, "continue_deep_confirmed": False}
    completed = max((int(item.get("round_no", 0)) for item in rounds), default=0)
    next_round = completed + 1
    limit = 3 if mode == "standard" else 5
    if next_round > limit:
        next_round = limit
    if mode == "deep" and next_round >= 4 and not confirmed:
        raise ApiError(code="DEEP_CONFIRMATION_REQUIRED", message="Deep clarification requires explicit confirmation", http_status=409)
    return {"mode": mode, "round_no": next_round, "continue_deep_confirmed": confirmed}


def _bearer(token: str | None) -> str:
    if not token or not token.startswith("Bearer "):
        raise ApiError(code="AUTH_REQUIRED", message="Authorization bearer token required", http_status=401)
    return token[7:]


class AiApiClient:
    """Small injectable HTTP client.  ``transport`` is used by contract tests."""

    def __init__(self, *, base_url: str | None = None, transport: Callable[..., Any] | None = None) -> None:
        self.base_url = (base_url if base_url is not None else get_settings().ai_api_url or "").rstrip("/")
        self.transport = transport

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None, *, idempotency_key: str | None = None, trace_id: str | None = None, command_id: str | None = None) -> dict[str, Any]:
        if self.transport is not None:
            try:
                result = self.transport(method, path, body, idempotency_key=idempotency_key, trace_id=trace_id, command_id=command_id)
            except TypeError:
                # Keep compatibility with the tiny three-argument test port.
                try:
                    result = self.transport(method, path, body, idempotency_key=idempotency_key)
                except Exception as exc:
                    raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI API is unavailable", http_status=503) from exc
            except Exception as exc:
                raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI API is unavailable", http_status=503) from exc
            if isinstance(result, dict):
                if result.get("code") and result.get("code") != "OK":
                    raise ApiError(code=str(result.get("code")), message="AI API rejected the task", http_status=503)
                return result.get("data", result)
            return result
        if not self.base_url:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI API is not configured", http_status=503)
        settings = get_settings()
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if not settings.internal_service_jwt_secret:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI API service identity is not configured", http_status=503)
        if method == "POST" and path == "/internal/v1/ai/tasks":
            task_binding = body.get("task_public_id") if isinstance(body, dict) else None
            body_trace = body.get("trace_id") if isinstance(body, dict) else None
            if trace_id is not None and body_trace is not None and str(trace_id) != str(body_trace):
                raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task trace binding is inconsistent", http_status=409)
            trace_binding = trace_id if trace_id is not None else body_trace
            scope = "ai.task:write"
        elif method == "GET" and path.startswith("/internal/v1/ai/tasks/"):
            task_binding = path.rsplit("/", 1)[-1]
            trace_binding = trace_id
            scope = "ai.task:read"
        else:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI API route is unsupported", http_status=503)
        if not task_binding or not trace_binding:
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task identity binding is incomplete", http_status=409)
        # The AI service accepts only a short-lived, task-scoped Business API token.
        now = int(datetime.now(UTC).timestamp())
        from app.platform.security import encode_hs256
        claims = {
            "iss": "business-api",
            "sub": "business-api",
            "aud": "ai-api",
            "scope": scope,
            "task_id": str(task_binding),
            "trace_id": str(trace_binding),
            "iat": now,
            "exp": now + 120,
            "jti": secrets.token_urlsafe(12),
        }
        headers["Authorization"] = "Bearer " + encode_hs256(claims, settings.internal_service_jwt_secret)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if command_id:
            headers["X-Command-ID"] = command_id
        request = urllib.request.Request(url, method=method, headers=headers, data=(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode() if body is not None else None))
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = {}
            raise ApiError(code=str(payload.get("code", "DEPENDENCY_UNAVAILABLE")), message="AI API request failed", http_status=503) from exc
        except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI API is unavailable", http_status=503) from exc
        if payload.get("code") and payload.get("code") != "OK":
            raise ApiError(code=str(payload.get("code")), message="AI API rejected the task", http_status=503)
        return payload.get("data", payload)

    def create_task(self, envelope: dict[str, Any], key: str) -> dict[str, Any]:
        return self._call("POST", "/internal/v1/ai/tasks", envelope, idempotency_key=key, trace_id=envelope.get("trace_id"), command_id=envelope.get("command_id"))

    def get_task(self, task_id: str, *, trace_id: str) -> dict[str, Any]:
        result = self._call("GET", f"/internal/v1/ai/tasks/{task_id}", trace_id=trace_id)
        try:
            _INTERNAL_TASK_RESPONSE.validate(result)
        except ValidationError as exc:
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task authority response is invalid", http_status=409) from exc
        return result


class ContentReader:
    def read_json(self, content_ref: str) -> Any:  # pragma: no cover - port definition
        raise NotImplementedError


class S3ContentReader(ContentReader):
    """Default reader for the existing S3-compatible storage boundary."""

    def read_json(self, content_ref: str) -> Any:
        settings = get_settings()
        if not (settings.object_storage_access_key and settings.object_storage_secret_key):
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI result content reader is not configured", http_status=503)
        signer = S3Signer(endpoint=settings.object_storage_endpoint, bucket=settings.object_storage_bucket, region=settings.object_storage_region, access_key=settings.object_storage_access_key, secret_key=settings.object_storage_secret_key)
        signed = signer.presign(method="GET", object_key=content_ref, expires_seconds=60)
        try:
            with urllib.request.urlopen(urllib.request.Request(signed.url, method="GET", headers=signed.required_headers), timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="AI result content is unavailable", http_status=503) from exc


def _task_summary(row: dict[str, Any]) -> dict[str, Any]:
    task_id = str(row.get("task_public_id") or row.get("task_id") or row.get("id"))
    internal_refs = row.get("result_refs", [])
    if not isinstance(internal_refs, list):
        raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task result references are invalid", http_status=409)
    result_refs = []
    for item in internal_refs:
        try:
            _INTERNAL_RESULT_REF.validate(item)
        except ValidationError as exc:
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task result references are invalid", http_status=409) from exc
        result_refs.append({
            "result_id": item["ai_result_id"],
            "status": item["status"],
            "target_snapshot_hash": item["target_snapshot_hash"],
        })
    return {
        "task_id": task_id,
        "task_public_id": task_id,
        "status": row.get("status", "queued"),
        "task_type": row.get("task_type", "requirement.clarify"),
        "created_by_user_id": str(row.get("user_id") or row.get("created_by_user_id") or ""),
        "queued_at": _iso(row.get("queued_at") or row.get("created_at")),
        "target_snapshot_hash": row.get("target_snapshot_hash", ""),
        "capability_summary": _json(row.get("capability_summary")) or {},
        "missing_items": _json(row.get("missing_items")) or [],
        "result_refs": result_refs,
        "events_url": row.get("events_url", f"/api/v1/ai/tasks/{task_id}/events"),
        "poll_url": row.get("poll_url", f"/api/v1/ai/tasks/{task_id}"),
    }


def _safe_capability_summary(row: dict[str, Any]) -> dict[str, str]:
    summary: dict[str, str] = {}
    provider_code = row.get("capability_provider_code")
    model_code = row.get("capability_model_code")
    capability = _json(row.get("model_capability_json"))
    if isinstance(provider_code, str) and provider_code:
        summary["provider_code"] = provider_code
    if isinstance(model_code, str) and model_code:
        summary["model_code"] = model_code
    if isinstance(capability, dict) and capability.get("truth_label") == "FORMAL_MOCK":
        summary["truth_label"] = "FORMAL_MOCK"
    return summary


def _result_view(row: dict[str, Any], content: Any) -> dict[str, Any]:
    quality = _json((content or {}).get("quality")) or _json(row.get("quality_summary") or row.get("quality_json")) or {
        "structure": row.get("format_status", "unknown"),
        "traceability": row.get("traceability_status", "unknown"),
        "security": row.get("safety_status", "unknown"),
        "major_error": bool(row.get("major_error", False)),
        "blocker_codes": [],
    }
    convergence = _json((content or {}).get("convergence")) or _json(row.get("convergence")) or {"should_finish": True, "next_round_no": None, "finish_reason": None}
    capability = _safe_capability_summary(row)
    return {
        "id": str(row.get("id") or row.get("result_id")),
        "schema_version": "0.2.0",
        "task_public_id": str(row.get("task_public_id") or row.get("task_id") or ""),
        "task_type": "requirement.clarify",
        "status": row.get("status", "ready"),
        "result_kind": row.get("result_kind", (content or {}).get("result_kind", "baseline")),
        "mode": row.get("mode", (content or {}).get("mode", "auto")),
        "round_no": int(row.get("round_no", (content or {}).get("round_no", 0))),
        "target_snapshot_hash": row.get("target_snapshot_hash", ""),
        "content_json": content,
        "content_summary": row.get("content_summary"),
        "source_refs": _json(row.get("source_refs")) or [],
        "quality_summary": quality,
        "convergence": convergence,
        "capability_summary": capability,
    }


class AiTaskService:
    def __init__(self, *, client: AiApiClient | None = None, content_reader: ContentReader | None = None) -> None:
        self.client = client or AiApiClient()
        self.content_reader = content_reader or S3ContentReader()

    def _target(self, connection: Any, target: dict[str, Any], user_id: int, *, for_write: bool = False) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        if not isinstance(target, dict) or target.get("object_type") != "requirement":
            raise ApiError(code="VALIDATION_ERROR", message="Only requirement targets are supported", http_status=422)
        try:
            requirement_id = int(target["object_id"])
            version_id = int(target["object_version_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(code="VALIDATION_ERROR", message="Requirement target identifiers are invalid", http_status=422) from exc
        version = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:version_id"), {"version_id": version_id}))
        requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:requirement_id"), {"requirement_id": requirement_id}))
        if not version or not requirement or int(version.get("requirement_id")) != requirement_id:
            raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
        project_version = _mapping(connection.execute(_sql("SELECT id,project_id FROM project_version WHERE id=:id"), {"id": requirement["project_version_id"]}))
        if not project_version:
            raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
        memberships = connection.execute(_sql("SELECT role_code FROM project_member WHERE project_id=:project_id AND user_id=:user_id AND status='active'"), {"project_id": project_version["project_id"], "user_id": user_id}).mappings().all()
        roles = [str(item["role_code"]) for item in memberships]
        if not roles:
            raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
        if for_write and "owner" not in roles:
            raise ApiError(code="FORBIDDEN", message="Project role does not allow this action", http_status=403)
        if not for_write and not set(roles).intersection({"owner", "reviewer", "implementer", "tester"}):
            raise ApiError(code="FORBIDDEN", message="Project role does not allow this action", http_status=403)
        return requirement, version, roles

    def _envelope(self, connection: Any, *, user_id: int, payload: dict[str, Any], trace_id: str) -> dict[str, Any]:
        _safe_validation(payload, _CREATE_TASK, "AI task request is invalid")
        target = payload.get("target")
        requirement, version, _ = self._target(connection, target, user_id, for_write=True)
        project_version = _mapping(connection.execute(_sql("SELECT project_id FROM project_version WHERE id=:id"), {"id": requirement["project_version_id"]}))
        content = _json(version.get("content_json"))
        _safe_validation(content, _REQ_CONTENT, "Requirement content is invalid")
        raw_ref = content["raw_input_ref"]
        raw_hash = hashlib.sha256(content["raw_input"].encode("utf-8")).hexdigest()
        if raw_ref.get("content_hash") != raw_hash or version.get("content_hash") != _canonical_hash(content):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="Requirement content hash is invalid", http_status=409)
        derived_refs = [str(raw_ref["source_id"])]
        supplied_refs = payload.get("source_ref_ids")
        if supplied_refs is not None and supplied_refs != derived_refs:
            raise ApiError(code="VALIDATION_ERROR", message="source_ref_ids must match the target raw input reference", http_status=422)
        risk = _json(version.get("risk_acceptance_json")) or []
        if not isinstance(risk, list):
            raise ApiError(code="RISK_ACCEPTANCE_INVALID", message="Risk acceptance is invalid", http_status=422)
        for item in risk:
            _safe_validation(item, _RISK, "Risk acceptance is invalid")
        clarification = content["clarification"]
        mode = clarification.get("mode", "auto")
        input_data = _clarification_input(content)
        command_id = f"cmd_{uuid.uuid4().hex}"
        envelope = {
            "schema_version": "0.2.0", "task_public_id": str(uuid.uuid4()), "user_id": str(user_id),
            "project_id": str(project_version["project_id"] if project_version else requirement["project_version_id"]), "project_version_id": str(requirement["project_version_id"]),
            "module": "product_design", "task_type": "requirement.clarify",
            "target": {"object_type": "requirement", "object_id": str(requirement["id"]), "object_version_id": str(version["id"])},
            "target_snapshot_hash": str(version["content_hash"]), "source_ref_ids": derived_refs,
            "capability_selection": payload.get("capability_selection"), "risk_acceptances": risk,
            "command_id": command_id, "trace_id": trace_id, "requested_at": _iso(None), "input": input_data,
        }
        _safe_validation(envelope, _ENVELOPE, "AI task envelope is invalid")
        return envelope

    def create_task(self, *, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        with readonly() as connection:
            envelope = self._envelope(connection, user_id=user_id, payload=payload, trace_id=trace_id)
        digest = _canonical_hash(payload)
        stable = hashlib.sha256(f"{user_id}|POST:/api/v1/ai/tasks|{key}|{digest}".encode()).hexdigest()
        envelope["task_public_id"] = str(uuid.UUID(stable[:32]))
        envelope["command_id"] = "cmd_" + stable[:32]
        replay = None
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint="POST:/api/v1/ai/tasks", key=key, payload=payload)
        if replay:
            with readonly() as connection:
                replay_task = _mapping(connection.execute(_sql("SELECT task_public_id,trace_id FROM ai_task WHERE task_public_id=:task_id"), {"task_id": str(replay)}))
            if not replay_task or not replay_task.get("trace_id"):
                raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task trace binding is unavailable", http_status=409)
            authority = self.client.get_task(str(replay), trace_id=str(replay_task["trace_id"]))
            authority_id = authority.get("task_public_id") or authority.get("task_id")
            if authority_id is None or str(authority_id) != str(replay):
                raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task authority response is inconsistent", http_status=409)
            return _task_summary({**authority, "task_public_id": authority.get("task_public_id") or replay, "user_id": user_id, "target_snapshot_hash": envelope["target_snapshot_hash"]})
        try:
            result = self.client.create_task(envelope, key)
        except Exception:
            with transaction() as connection:
                connection.execute(_sql("DELETE FROM idempotency_record WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key AND status='in_progress' AND request_hash=:digest"), {"user_id": user_id, "endpoint": "POST:/api/v1/ai/tasks", "key": key, "digest": digest})
            raise
        if not result or result.get("status") not in {"prechecking", "queued", "preparing", "generating", "checking", "ready", "partial_result", "quality_blocked"}:
            with transaction() as connection:
                connection.execute(_sql("DELETE FROM idempotency_record WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key AND status='in_progress' AND request_hash=:digest"), {"user_id": user_id, "endpoint": "POST:/api/v1/ai/tasks", "key": key, "digest": digest})
            raise ApiError(code="QUEUE_UNAVAILABLE", message="AI task was not accepted", http_status=503)
        returned_id = result.get("task_public_id") or result.get("task_id")
        if returned_id is None or str(returned_id) != envelope["task_public_id"]:
            with transaction() as connection:
                connection.execute(_sql("DELETE FROM idempotency_record WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key AND status='in_progress' AND request_hash=:digest"), {"user_id": user_id, "endpoint": "POST:/api/v1/ai/tasks", "key": key, "digest": digest})
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task identifier is inconsistent", http_status=409)
        summary = _task_summary({**result, "task_public_id": envelope["task_public_id"], "user_id": user_id, "target_snapshot_hash": envelope["target_snapshot_hash"]})
        try:
            with transaction() as connection:
                requirement_id = int(envelope["target"]["object_id"]); version_id = int(envelope["target"]["object_version_id"])
                _audit(connection, user_id=user_id, requirement_id=requirement_id, version_id=version_id, trace_id=trace_id, command_id=envelope["command_id"], operation="ai.task.created")
                _idempotency_complete(connection, user_id=user_id, endpoint="POST:/api/v1/ai/tasks", key=key, response_ref=envelope["task_public_id"])
        except Exception:
            with transaction() as connection:
                connection.execute(_sql("DELETE FROM idempotency_record WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key AND status='in_progress' AND request_hash=:digest"), {"user_id": user_id, "endpoint": "POST:/api/v1/ai/tasks", "key": key, "digest": digest})
            raise
        return summary

    def get_task(self, *, user_id: int, task_id: str) -> dict[str, Any]:
        with readonly() as connection:
            row = _mapping(connection.execute(_sql("SELECT * FROM ai_task WHERE task_public_id=:task_id"), {"task_id": task_id}))
            if not row:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            self._target(connection, {"object_type": "requirement", "object_id": row.get("target_object_id"), "object_version_id": row.get("target_object_version_id")}, user_id)
        if not row.get("trace_id"):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task trace binding is unavailable", http_status=409)
        authority = self.client.get_task(task_id, trace_id=str(row["trace_id"]))
        if str(authority.get("task_public_id") or authority.get("task_id")) != str(task_id):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task authority response is inconsistent", http_status=409)
        if authority.get("trace_id") is not None and str(authority.get("trace_id")) != str(row.get("trace_id")):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task authority response is inconsistent", http_status=409)
        if authority.get("target_snapshot_hash") is not None and str(authority.get("target_snapshot_hash")) != str(row.get("target_snapshot_hash")):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI task authority response is inconsistent", http_status=409)
        return _task_summary({**row, **authority, "task_public_id": task_id})

    def get_result(self, *, user_id: int, result_id: str) -> dict[str, Any]:
        with readonly() as connection:
            result = _mapping(connection.execute(_sql("SELECT ar.*,at.task_public_id,at.target_object_id,at.target_object_version_id,at.target_snapshot_hash,at.status AS task_status,pp.provider_code AS capability_provider_code,mc.model_code AS capability_model_code,mc.capability_json AS model_capability_json FROM ai_result ar JOIN ai_call ac ON ac.id=ar.ai_call_id JOIN ai_task at ON at.id=ac.ai_task_id JOIN provider_profile pp ON pp.id=ac.provider_profile_id JOIN model_catalog mc ON mc.id=ac.model_catalog_id WHERE ar.id=:result_id"), {"result_id": result_id}))
            if not result:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            requirement, version, _ = self._target(connection, {"object_type": "requirement", "object_id": result.get("target_object_id"), "object_version_id": result.get("target_object_version_id")}, user_id)
        content = result.get("content_json")
        if content is None:
            ref = result.get("content_ref")
            if not ref:
                raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result content is unavailable", http_status=409)
            content = self.content_reader.read_json(str(ref))
        fingerprint = result.get("content_fingerprint")
        if fingerprint and _canonical_hash(content) != fingerprint:
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result content fingerprint is invalid", http_status=409)
        _safe_validation(content, Draft202012Validator({"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/components/schemas/AiResultContent", "components": {"schemas": SPRINT2_SCHEMAS}}), "AI result content is invalid")
        if str(content.get("task_public_id")) != str(result.get("task_public_id")) or str(content.get("target_snapshot_hash")) != str(result.get("target_snapshot_hash")) or str(result.get("target_snapshot_hash")) != str(version.get("content_hash")):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result target is inconsistent", http_status=409)
        version_content = _json(version.get("content_json"))
        if not isinstance(version_content, dict) or not isinstance(version_content.get("raw_input_ref"), dict):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="Requirement source reference is invalid", http_status=409)
        _safe_validation(version_content, _REQ_CONTENT, "Requirement content is invalid")
        if _canonical_hash(version_content) != str(version.get("content_hash")) or version_content["raw_input_ref"].get("content_hash") != hashlib.sha256(version_content["raw_input"].encode("utf-8")).hexdigest():
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="Requirement content hash is invalid", http_status=409)
        result["source_refs"] = [version_content.get("raw_input_ref")] if isinstance(version_content, dict) else []
        if content.get("status") != result.get("status"):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result status is inconsistent", http_status=409)
        return _result_view({**result, "id": result_id}, content)

    def formalize(self, *, user_id: int, result_id: str, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        _safe_validation(payload, _FORMALIZE, "Formalize request is invalid")
        adoption = payload.get("adoption")
        if adoption not in {"adopt", "modified_adopt", "reject"}:
            raise ApiError(code="VALIDATION_ERROR", message="Invalid adoption", http_status=422)
        if adoption == "reject" and not payload.get("reason"):
            raise ApiError(code="VALIDATION_ERROR", message="Reject reason is required", http_status=422)
        if adoption == "modified_adopt" and not isinstance(payload.get("modified_content_json"), dict):
            raise ApiError(code="VALIDATION_ERROR", message="modified_content_json is required", http_status=422)
        endpoint = f"POST:/api/v1/ai/results/{result_id}:formalize"
        # Load the immutable AI candidate and its object content before opening
        # the Business transaction; object storage/network IO must not hold a
        # MySQL lock.
        with readonly() as read_connection:
            metadata = _mapping(read_connection.execute(_sql("SELECT ar.*,at.task_public_id,at.target_snapshot_hash AS task_target_snapshot_hash,at.target_object_id,at.target_object_version_id FROM ai_result ar JOIN ai_call ac ON ac.id=ar.ai_call_id JOIN ai_task at ON at.id=ac.ai_task_id WHERE ar.id=:result_id"), {"result_id": result_id}))
        if not metadata:
            raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
        # Replay preflight: verify current owner access and idempotency before
        # touching the object store. Completed commands are fully replayable
        # from Business facts alone.
        with readonly() as preflight:
            _, preflight_version, _ = self._target(preflight, {"object_type": "requirement", "object_id": metadata.get("target_object_id"), "object_version_id": metadata.get("target_object_version_id")}, user_id, for_write=True)
            idem = _mapping(preflight.execute(_sql("SELECT request_hash,status,response_ref FROM idempotency_record WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key"), {"user_id": user_id, "endpoint": endpoint, "key": key}))
        if idem:
            if idem.get("request_hash") != _canonical_hash(payload):
                raise ApiError(code="IDEMPOTENCY_CONFLICT", message="Key was used with another request", http_status=409)
            if idem.get("status") == "in_progress":
                raise ApiError(code="IDEMPOTENCY_CONFLICT", message="The same command is still in progress", http_status=409)
            if idem.get("status") == "completed":
                with readonly() as replay_connection:
                    existing = _mapping(replay_connection.execute(_sql("SELECT a.id,a.adoption_status,a.formal_object_version_id,v.version_no,v.confirmation_status,v.content_hash,v.created_at FROM ai_adoption a LEFT JOIN requirement_version v ON v.id=a.formal_object_version_id WHERE a.id=:id"), {"id": idem.get("response_ref")}))
                if existing:
                    return {"adoption_id": str(existing["id"]), "adoption_status": existing["adoption_status"], "artifact_version_ref": None if existing.get("formal_object_version_id") is None else {"id": str(existing["formal_object_version_id"]), "version_no": str(existing["version_no"]), "status": existing.get("confirmation_status", "draft"), "content_hash": existing["content_hash"], "created_at": _iso(existing["created_at"])} }
                raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Idempotency adoption is unavailable", http_status=503)
        preloaded_content = _json(metadata.get("content_json"))
        if preloaded_content is None:
            if not metadata.get("content_ref"):
                raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result content is unavailable", http_status=409)
            preloaded_content = self.content_reader.read_json(str(metadata["content_ref"]))
        if metadata.get("content_fingerprint") and _canonical_hash(preloaded_content) != metadata["content_fingerprint"]:
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result content fingerprint is invalid", http_status=409)
        _safe_validation(preloaded_content, Draft202012Validator({"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/components/schemas/AiResultContent", "components": {"schemas": SPRINT2_SCHEMAS}}), "AI result content is invalid")
        hashes = {str(payload.get("target_snapshot_hash")), str(preflight_version.get("content_hash")), str(metadata.get("target_snapshot_hash")), str(metadata.get("task_target_snapshot_hash")), str(preloaded_content.get("target_snapshot_hash"))}
        if len(hashes) != 1:
            raise ApiError(code="STALE_TARGET", message="AI result target is stale", http_status=409)
        if str(preloaded_content.get("task_public_id")) != str(metadata.get("task_public_id")) or str(preloaded_content.get("target_snapshot_hash")) != str(metadata.get("target_snapshot_hash")) or str(metadata.get("target_snapshot_hash")) != str(metadata.get("task_target_snapshot_hash")):
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result target is inconsistent", http_status=409)
        with transaction() as connection:
            authorization_row = _mapping(connection.execute(_sql("SELECT ar.*,at.target_object_id,at.target_object_version_id FROM ai_result ar JOIN ai_call ac ON ac.id=ar.ai_call_id JOIN ai_task at ON at.id=ac.ai_task_id WHERE ar.id=:result_id"), {"result_id": result_id}))
            if not authorization_row:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            self._target(
                connection,
                {
                    "object_type": "requirement",
                    "object_id": str(authorization_row["target_object_id"]),
                    "object_version_id": str(authorization_row["target_object_version_id"]),
                },
                user_id,
                for_write=True,
            )
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            if replay:
                existing = _mapping(connection.execute(_sql("SELECT a.id,a.adoption_status,a.formal_object_version_id,v.version_no,v.confirmation_status,v.content_hash,v.created_at FROM ai_adoption a LEFT JOIN requirement_version v ON v.id=a.formal_object_version_id WHERE a.id=:id"), {"id": replay}))
                if existing:
                    if existing.get("formal_object_version_id") is not None:
                        return {"adoption_id": str(existing["id"]), "adoption_status": existing["adoption_status"], "artifact_version_ref": {"id": str(existing["formal_object_version_id"]), "version_no": str(existing["version_no"]), "status": existing.get("confirmation_status", "draft"), "content_hash": existing["content_hash"], "created_at": _iso(existing["created_at"])} }
                    return {"adoption_id": str(existing["id"]), "adoption_status": existing["adoption_status"], "artifact_version_ref": None if existing.get("formal_object_version_id") is None else {"id": str(existing["formal_object_version_id"])}}
                raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Idempotency adoption is unavailable", http_status=503)
            row = _mapping(connection.execute(_sql("SELECT ar.*,at.task_public_id,at.target_object_id,at.target_object_version_id,at.user_id,at.target_snapshot_hash FROM ai_result ar JOIN ai_call ac ON ac.id=ar.ai_call_id JOIN ai_task at ON at.id=ac.ai_task_id WHERE ar.id=:result_id"), {"result_id": result_id}))
            if not row:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            target = {"object_type": "requirement", "object_id": str(row["target_object_id"]), "object_version_id": str(row["target_object_version_id"])}
            requirement, version, _ = self._target(connection, target, user_id, for_write=True)
            project_version = _mapping(connection.execute(_sql("SELECT project_id FROM project_version WHERE id=:id"), {"id": requirement["project_version_id"]})) or {}
            locked_requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:requirement_id FOR UPDATE"), {"requirement_id": requirement["id"]}))
            locked_version = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:version_id FOR UPDATE"), {"version_id": version["id"]}))
            if locked_requirement:
                requirement = locked_requirement
            if locked_version:
                version = locked_version
            content = preloaded_content
            if (
                payload.get("target_object_id") != str(requirement["id"])
                or str(payload.get("target_snapshot_hash")) != str(version["content_hash"])
                or str(row.get("target_snapshot_hash")) != str(version["content_hash"])
                or str(content.get("target_snapshot_hash")) != str(version["content_hash"])
            ):
                raise ApiError(code="STALE_TARGET", message="AI result target is stale", http_status=409)
            if int(payload.get("expected_version", 0)) != int(requirement["row_version"]):
                raise ApiError(code="VERSION_CONFLICT", message="Requirement has changed", http_status=409)
            if row.get("status") not in _STATUS_READY:
                raise ApiError(code="RESULT_NOT_READY", message="AI result is not ready", http_status=409)
            if content.get("status") != row.get("status") or str(content.get("task_public_id")) != str(row.get("task_public_id")):
                raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result facts are inconsistent", http_status=409)
            if row.get("format_status") not in {"valid", "passed", "complete"} or row.get("traceability_status") not in {"valid", "passed", "complete"} or row.get("safety_status") not in {"valid", "passed", "complete"} or bool(row.get("major_error")) or (row.get("required_items_total") is not None and row.get("required_items_met") != row.get("required_items_total")):
                    raise ApiError(code="RESULT_QUALITY_BLOCKED", message="AI result quality gate did not pass", http_status=409)
            content = preloaded_content
            if row.get("content_fingerprint") and _canonical_hash(content) != row["content_fingerprint"]:
                raise ApiError(code="TRACEABILITY_INCOMPLETE", message="AI result content fingerprint is invalid", http_status=409)
            if adoption != "reject":
                ai_content = payload.get("modified_content_json") if adoption == "modified_adopt" else content
                old_content = _json(version["content_json"])
                new_content = dict(old_content)
                new_content.setdefault("clarification", {})["continue_deep_confirmed"] = bool(old_content.get("clarification", {}).get("continue_deep_confirmed", False)) if new_content.get("clarification", {}).get("mode") == old_content.get("clarification", {}).get("mode") else False
                if isinstance(ai_content, dict) and isinstance(ai_content.get("baseline"), dict):
                    new_content["baseline"] = ai_content["baseline"]
                if isinstance(ai_content, dict) and isinstance(ai_content.get("clarification"), dict):
                    new_content["clarification"] = ai_content["clarification"]
                old_flag = bool(old_content.get("clarification", {}).get("continue_deep_confirmed", False))
                merged_mode = new_content.get("clarification", {}).get("mode")
                old_mode = old_content.get("clarification", {}).get("mode")
                new_content.setdefault("clarification", {})["continue_deep_confirmed"] = old_flag if merged_mode == old_mode else False
                _safe_validation(new_content, _REQ_CONTENT, "Formalized requirement content is invalid")
                new_hash = _canonical_hash(new_content)
                now = _now()
                latest = _mapping(connection.execute(_sql("SELECT version_no FROM requirement_version WHERE requirement_id=:rid ORDER BY id DESC LIMIT 1"), {"rid": requirement["id"]}))
                next_no = int(str(latest["version_no"]).lstrip("V")) + 1 if latest else 1
                inserted = connection.execute(_sql("INSERT INTO requirement_version (created_at,created_by,requirement_id,source_version_id,version_no,content_format,content_json,content_hash,confirmation_status,unresolved_count,risk_acceptance_json,created_from_ai_result_id,is_effective) VALUES (:now,:uid,:rid,:source,:version_no,:format,:content,:hash,'draft',:unresolved,:risk,:result_id,0)"), {"now": now, "uid": user_id, "rid": requirement["id"], "source": version["id"], "version_no": str(next_no), "format": version["content_format"], "content": json.dumps(new_content, ensure_ascii=False, separators=(",", ":")), "hash": new_hash, "unresolved": len(new_content.get("baseline", {}).get("unresolved_items", [])), "risk": version.get("risk_acceptance_json"), "result_id": result_id})
                new_version_id = int(inserted.lastrowid)
                updated = connection.execute(_sql("UPDATE requirement SET current_version_id=:vid,row_version=row_version+1,updated_at=:now,updated_by=:uid WHERE id=:rid AND row_version=:expected"), {"vid": new_version_id, "now": now, "uid": user_id, "rid": requirement["id"], "expected": payload["expected_version"]})
                if getattr(updated, "rowcount", 1) != 1:
                    raise ApiError(code="VERSION_CONFLICT", message="Requirement has changed", http_status=409)
            else:
                new_version_id = None
                new_hash = None
            now = _now()
            adoption_status = {"adopt": "adopted", "modified_adopt": "adopted_after_edit", "reject": "rejected"}[adoption]
            ad = connection.execute(_sql("INSERT INTO ai_adoption (created_at,created_by,retention_class,expires_at,ai_result_id,supersedes_adoption_id,adoption_status,modification_intensity,reason_code,reason_text,formal_object_type,formal_object_id,formal_object_version_id,reviewed_by,reviewed_at) VALUES (:now,:uid,'business',NULL,:result_id,NULL,:status,:intensity,NULL,:reason,'requirement',:rid,:vid,:uid,:now)"), {"now": now, "uid": user_id, "result_id": result_id, "status": adoption_status, "intensity": payload.get("modification_intensity", "none"), "reason": payload.get("reason"), "rid": requirement["id"], "vid": new_version_id})
            adoption_id = str(ad.lastrowid)
            command_id = f"cmd_{uuid.uuid4().hex}"
            _audit(connection, user_id=user_id, requirement_id=int(requirement["id"]), version_id=int(new_version_id or version["id"]), trace_id=trace_id, command_id=command_id, operation="ai.result.formalize")
            event_id = str(uuid.uuid4())
            event_payload = {"artifact_type": "requirement", "formal_version_id": str(new_version_id) if new_version_id is not None else None, "source_ai_result_id": str(result_id), "adoption_id": adoption_id, "adoption_status": adoption_status}
            envelope = {"schema_version": "0.2.0", "event_id": event_id, "event_name": "artifact.version.formalized" if new_version_id is not None else "ai.result.rejected", "occurred_at": _iso(now), "producer": "Business API", "module": "product_design", "result_status": "success", "source_type": "server", "privacy_class": "internal_id", "user_id": str(user_id), "project_id": str(project_version.get("project_id")), "project_version_id": str(requirement["project_version_id"]), "object_type": "requirement", "object_id": str(requirement["id"]), "object_version_id": str(new_version_id or version["id"]), "trace_id": trace_id, "command_id": command_id, "payload_json": event_payload}
            connection.execute(_sql("INSERT INTO business_event_outbox (event_id,aggregate_type,aggregate_id,aggregate_version,event_name,schema_version,payload_json,publish_status,attempt_count,next_attempt_at,published_at,created_at) VALUES (:event_id,'requirement',:rid,:aggregate_version,:event_name,'0.2.0',:payload,'pending',0,NULL,NULL,:created_at)"), {"event_id": event_id, "rid": requirement["id"], "aggregate_version": int(requirement["row_version"]) + (1 if new_version_id is not None else 0), "event_name": envelope["event_name"], "payload": json.dumps(envelope, ensure_ascii=False, separators=(",", ":")), "created_at": now})
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=adoption_id)
            return {"adoption_id": adoption_id, "adoption_status": adoption_status, "artifact_version_ref": None if new_version_id is None else {"id": str(new_version_id), "version_no": str(next_no), "status": "draft", "content_hash": new_hash, "created_at": _iso(now)}}


class ContextService:
    def __init__(self) -> None:
        pass

    def _claims(self, authorization: str | None, task_id: str, action: str) -> dict[str, Any]:
        settings = get_settings()
        if not settings.internal_service_jwt_secret:
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Internal service authentication required", http_status=401)
        claims = decode_hs256(_bearer(authorization), settings.internal_service_jwt_secret, audience="business-api", issuer="ai-worker", require_jti=True, max_ttl_seconds=300)
        scopes = set(str(claims.get("scope", "")).split())
        if "context:read" not in scopes:
            raise ApiError(code="FORBIDDEN", message="Internal service scope is insufficient", http_status=403)
        if str(claims.get("task_id") or claims.get("task_public_id")) != str(task_id):
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Service token task binding is invalid", http_status=401)
        return claims

    def _load(self, task_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        with readonly() as connection:
            task = _mapping(connection.execute(_sql("SELECT * FROM ai_task WHERE task_public_id=:task_id"), {"task_id": task_id}))
            if not task:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            if task.get("target_object_type") != "requirement":
                raise ApiError(code="STALE_TARGET", message="Task target is invalid", http_status=409)
            version = _mapping(connection.execute(_sql("SELECT * FROM requirement_version WHERE id=:version_id"), {"version_id": task["target_object_version_id"]}))
            requirement = _mapping(connection.execute(_sql("SELECT * FROM requirement WHERE id=:requirement_id"), {"requirement_id": task["target_object_id"]}))
            if not version or not requirement or int(version.get("requirement_id")) != int(requirement.get("id")) or int(requirement.get("project_version_id")) != int(task.get("project_version_id")):
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            project_version = _mapping(connection.execute(_sql("SELECT project_id FROM project_version WHERE id=:id"), {"id": task["project_version_id"]}))
            if not project_version or int(project_version.get("project_id")) != int(task.get("project_id")):
                raise ApiError(code="STALE_TARGET", message="Task target is invalid", http_status=409)
            members = connection.execute(_sql("SELECT role_code FROM project_member WHERE project_id=:project_id AND user_id=:user_id AND status='active'"), {"project_id": task["project_id"], "user_id": task["user_id"]}).mappings().all()
            if not members:
                raise ApiError(code="PERMISSION_CHANGED", message="Task owner no longer has project access", http_status=403)
            return task, requirement, version

    def context_snapshot(self, *, task_id: str, authorization: str | None, body: dict[str, Any], trace_id: str | None = None) -> dict[str, Any]:
        claims = self._claims(authorization, task_id, "ai:context_snapshot")
        if set(body) != {"token_budget"} or not isinstance(body.get("token_budget"), int) or isinstance(body.get("token_budget"), bool) or not 1 <= body["token_budget"] <= 200000:
            raise ApiError(code="VALIDATION_ERROR", message="Context request must contain token_budget", http_status=422)
        task, requirement, version = self._load(task_id)
        if claims.get("trace_id") is None and trace_id is None:
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Trace binding is required", http_status=401)
        if claims.get("trace_id") is not None and str(claims.get("trace_id")) != str(task.get("trace_id")):
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Service token trace binding is invalid", http_status=401)
        if trace_id is not None and str(trace_id) != str(task.get("trace_id")):
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Trace header binding is invalid", http_status=401)
        content = _json(version["content_json"])
        _safe_validation(content, _REQ_CONTENT, "Requirement content is invalid")
        if str(task.get("target_snapshot_hash")) != str(version.get("content_hash")) or _canonical_hash(content) != str(version.get("content_hash")):
            raise ApiError(code="STALE_TARGET", message="Task target is stale", http_status=409)
        raw_ref = content["raw_input_ref"]
        if raw_ref.get("content_hash") != hashlib.sha256(content["raw_input"].encode()).hexdigest():
            raise ApiError(code="TRACEABILITY_INCOMPLETE", message="Requirement source hash is invalid", http_status=409)
        allowed = [str(raw_ref["source_id"])]
        risk = _json(version.get("risk_acceptance_json")) or []
        for item in risk:
            _safe_validation(item, _RISK, "Risk acceptance is invalid")
        input_data = _clarification_input(content)
        return {"contract_version": "p1-runtime-context.v1", "task_public_id": str(task["task_public_id"]), "target": {"object_type": "requirement", "object_id": str(task["target_object_id"]), "object_version_id": str(task["target_object_version_id"])}, "target_snapshot_hash": str(version["content_hash"]), "input": input_data, "source_ref_ids": allowed, "risk_acceptances": risk, "requirement_content": content}

    def freshness(self, *, task_id: str, authorization: str | None, trace_id: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        claims = self._claims(authorization, task_id, "ai:target_freshness")
        task, requirement, version = self._load(task_id)
        if claims.get("trace_id") is None and trace_id is None:
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Trace binding is required", http_status=401)
        if body is not None and (set(body) != {"target_snapshot_hash"} or str(body.get("target_snapshot_hash")) != str(task.get("target_snapshot_hash"))):
            raise ApiError(code="STALE_TARGET", message="Task target is stale", http_status=409)
        if claims.get("trace_id") is not None and str(claims.get("trace_id")) != str(task.get("trace_id")):
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Service token trace binding is invalid", http_status=401)
        if trace_id is not None and str(trace_id) != str(task.get("trace_id")):
            raise ApiError(code="SERVICE_TOKEN_INVALID", message="Trace header binding is invalid", http_status=401)
        with readonly() as connection:
            current = _mapping(connection.execute(_sql("SELECT id,content_hash FROM requirement_version WHERE id=:version_id"), {"version_id": requirement.get("current_version_id")}))
        current_hash = str(current.get("content_hash")) if current else ""
        fresh = bool(current and str(current.get("id")) == str(version.get("id")) and str(task.get("target_snapshot_hash")) == current_hash)
        return {"fresh": fresh, "current_snapshot_hash": current_hash, "current_version_id": str(current.get("id")) if current else None}
