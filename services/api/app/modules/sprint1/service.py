from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from app.modules.projects.domain import is_allowed
from app.platform.config import get_settings
from app.platform.database import readonly, transaction
from app.platform.errors import ApiError
from app.platform.security import (
    decode_hs256,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)
from app.platform.storage import S3ObjectStorage, S3Signer, checksum_sha256_base64


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _sql(statement: str) -> Any:
    from sqlalchemy import text

    return text(statement)


def _mapping(result: Any) -> dict[str, Any] | None:
    row = result.mappings().first()
    return dict(row) if row else None


def _command_id() -> str:
    return f"cmd_{uuid.uuid4().hex}"


def _event_id() -> str:
    return str(uuid.uuid4())


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _audit(
    connection: Any,
    *,
    actor_user_id: int | None,
    operation: str,
    object_type: str,
    object_id: int | None,
    object_version_id: int | None,
    trace_id: str,
    command_id: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    result_status: str = "success",
    failure_code: str | None = None,
) -> None:
    connection.execute(
        _sql(
            "INSERT INTO operation_audit_log "
            "(retention_class,expires_at,actor_user_id,actor_type,operation_name,object_type,"
            "object_id,object_version_id,result_status,failure_code,reason_summary,trace_id,"
            "command_id,occurred_at,metadata_json) VALUES "
            "('audit',NULL,:actor,'user',:operation,:object_type,:object_id,:object_version_id,"
            ":result_status,:failure_code,:reason,:trace_id,:command_id,:occurred_at,:metadata)"
        ),
        {
            "actor": actor_user_id,
            "operation": operation,
            "object_type": object_type,
            "object_id": object_id,
            "object_version_id": object_version_id,
            "reason": reason,
            "trace_id": trace_id,
            "command_id": command_id,
            "occurred_at": _now(),
            "metadata": json.dumps(metadata or {}, separators=(",", ":")),
            "result_status": result_status,
            "failure_code": failure_code,
        },
    )


def _outbox(
    connection: Any,
    *,
    aggregate_type: str,
    aggregate_id: int,
    aggregate_version: int,
    event_name: str | None,
    payload: dict[str, Any],
    trace_id: str,
    command_id: str,
    module: str,
    user_id: int | None = None,
    project_id: int | None = None,
    project_version_id: int | None = None,
    session_id: str | None = None,
    result_status: str = "success",
    failure_code: str | None = None,
) -> None:
    event_id = _event_id()
    envelope = {
        "schema_version": "0.1.3",
        "event_id": event_id,
        "event_name": event_name,
        "occurred_at": _now().replace(tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "module": module,
        "result_status": result_status,
        "source_type": "server",
        "privacy_class": "pseudonymous" if module == "identity" else "internal_id",
        "trace_id": trace_id,
        "command_id": command_id,
        "payload_json": payload,
    }
    for key, value in {
        "user_id": user_id,
        "project_id": project_id,
        "project_version_id": project_version_id,
        "session_id": session_id,
        "failure_code": failure_code,
    }.items():
        if value is not None:
            envelope[key] = str(value)
    connection.execute(
        _sql(
            "INSERT INTO business_event_outbox "
            "(event_id,aggregate_type,aggregate_id,aggregate_version,event_name,schema_version,"
            "payload_json,publish_status,attempt_count,next_attempt_at,published_at,created_at) "
            "VALUES (:event_id,:aggregate_type,:aggregate_id,:aggregate_version,:event_name,"
            "'0.1.3',:payload,'pending',0,NULL,NULL,:created_at)"
        ),
        {
            "event_id": event_id,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "aggregate_version": aggregate_version,
            "event_name": event_name,
            "payload": json.dumps(envelope, separators=(",", ":")),
            "created_at": _now(),
        },
    )


def _idempotency_begin(
    connection: Any,
    *,
    user_id: int,
    endpoint: str,
    key: str,
    payload: dict[str, Any],
) -> str | None:
    digest = _request_hash(payload)
    now = _now()
    inserted = connection.execute(
        _sql(
            "INSERT IGNORE INTO idempotency_record "
            "(user_id,endpoint_key,idempotency_key,request_hash,status,response_code,response_ref,"
            "created_at,expires_at) VALUES (:user_id,:endpoint,:key,:digest,'in_progress',NULL,NULL,"
            ":created_at,:expires_at)"
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
    record = _mapping(
        connection.execute(
            _sql(
                "SELECT request_hash,status,response_ref FROM idempotency_record "
                "WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key FOR UPDATE"
            ),
            {"user_id": user_id, "endpoint": endpoint, "key": key},
        )
    )
    assert record
    if record["request_hash"] != digest:
        raise ApiError(code="IDEMPOTENCY_CONFLICT", message="Key was used with another request", http_status=409)
    if record["status"] == "completed":
        return str(record["response_ref"])
    if not inserted:
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="The same command is still in progress",
            http_status=409,
        )
    return None


def _idempotency_lookup(
    connection: Any,
    *,
    user_id: int,
    endpoint: str,
    key: str,
    payload: dict[str, Any],
) -> str | None:
    record = _mapping(
        connection.execute(
            _sql(
                "SELECT request_hash,status,response_ref FROM idempotency_record "
                "WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key"
            ),
            {"user_id": user_id, "endpoint": endpoint, "key": key},
        )
    )
    if not record:
        return None
    if record["request_hash"] != _request_hash(payload):
        raise ApiError(code="IDEMPOTENCY_CONFLICT", message="Key was used with another request", http_status=409)
    return str(record["response_ref"]) if record["status"] == "completed" else None


def _idempotency_complete(
    connection: Any, *, user_id: int, endpoint: str, key: str, response_ref: str
) -> None:
    connection.execute(
        _sql(
            "UPDATE idempotency_record SET status='completed',response_code='OK',response_ref=:ref "
            "WHERE user_id=:user_id AND endpoint_key=:endpoint AND idempotency_key=:key"
        ),
        {"ref": response_ref, "user_id": user_id, "endpoint": endpoint, "key": key},
    )


def _identity_event(
    connection: Any,
    *,
    event_name: str,
    trace_id: str,
    command_id: str,
    user_id: int | None,
    session_id: str | None,
    payload: dict[str, Any],
    result_status: str = "success",
    failure_code: str | None = None,
) -> None:
    _outbox(
        connection,
        aggregate_type="user_account" if user_id else "identity_attempt",
        aggregate_id=user_id or 0,
        aggregate_version=1,
        event_name=event_name,
        payload=payload,
        trace_id=trace_id,
        command_id=command_id,
        module="identity",
        user_id=user_id,
        session_id=session_id,
        result_status=result_status,
        failure_code=failure_code,
    )


def _record_auth_failure(
    *,
    operation: str,
    event_name: str | None,
    failure_code: str,
    trace_id: str,
    user_id: int | None = None,
) -> None:
    command_id = _command_id()
    with transaction() as connection:
        _audit(
            connection,
            actor_user_id=user_id,
            operation=operation,
            object_type="auth_attempt",
            object_id=None,
            object_version_id=None,
            trace_id=trace_id,
            command_id=command_id,
            metadata={"reason_class": "credentials_rejected"},
            result_status="failed",
            failure_code=failure_code,
        )
        if event_name:
            _identity_event(
                connection,
                event_name=event_name,
                trace_id=trace_id,
                command_id=command_id,
                user_id=user_id,
                session_id=None,
                payload={"producer_component": "business_api", "reason_class": "credentials_rejected"},
                result_status="failed",
                failure_code=failure_code,
            )


def _user_summary(row: dict[str, Any]) -> dict[str, Any]:
    roles = ["admin"] if row.get("system_role") == "admin" else []
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "system_roles": roles,
        "status": row["status"],
    }


def _project_roles(connection: Any, project_id: int, user_id: int) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            _sql(
                "SELECT role_code FROM project_member WHERE project_id=:project_id "
                "AND user_id=:user_id AND status='active'"
            ),
            {"project_id": project_id, "user_id": user_id},
        )
    ]


def _require_action(connection: Any, *, project_id: int, user_id: int, action: str) -> list[str]:
    roles = _project_roles(connection, project_id, user_id)
    if not roles:
        raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
    if not is_allowed(roles, action):
        raise ApiError(code="FORBIDDEN", message="Project role does not allow this action", http_status=403)
    return roles


def _validate_relation_target(
    connection: Any, *, project_id: int, relation: dict[str, Any]
) -> None:
    object_type = relation["object_type"]
    object_id = int(relation["object_id"])
    if object_type == "project":
        valid = object_id == project_id
    elif object_type == "project_version":
        valid = connection.execute(
            _sql("SELECT 1 FROM project_version WHERE id=:id AND project_id=:project_id"),
            {"id": object_id, "project_id": project_id},
        ).first() is not None
    elif object_type == "project_context":
        valid = connection.execute(
            _sql("SELECT 1 FROM project_context WHERE id=:id AND project_id=:project_id"),
            {"id": object_id, "project_id": project_id},
        ).first() is not None
    else:
        raise ApiError(
            code="FEATURE_DISABLED",
            message="Relation target type is not enabled in Sprint 1",
            http_status=409,
        )
    if not valid:
        raise ApiError(code="RESOURCE_NOT_FOUND", message="Relation target not found", http_status=404)


def _project_summary(connection: Any, project_id: int, user_id: int) -> dict[str, Any]:
    row = _mapping(
        connection.execute(
            _sql(
                "SELECT p.*,pv.id working_version_id,pv.version_no working_version_no "
                "FROM project p JOIN project_version pv ON pv.project_id=p.id AND pv.is_working=1 "
                "WHERE p.id=:project_id"
            ),
            {"project_id": project_id},
        )
    )
    if not row:
        raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
    roles = _project_roles(connection, project_id, user_id)
    if not roles:
        raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
    actions = [action for action in (
        "project:view", "project:update", "project:archive", "project:restore",
        "project:manage-members", "version:view-history", "version:set-working",
        "version:derive", "file:upload", "file:download", "file:relate"
    ) if is_allowed(roles, action)]
    return {
        "id": str(row["id"]), "name": row["name"], "description": row["description"],
        "status": row["status"], "working_version_id": str(row["working_version_id"]),
        "working_version_no": row["working_version_no"], "last_module": row["last_module"],
        "updated_at": row["updated_at"].replace(tzinfo=UTC).isoformat(), "version": row["row_version"],
        "permissions": {"roles": roles, "allowed_actions": actions, "permission_version": max(1, row["row_version"])},
    }


def _version_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]), "project_id": str(row["project_id"]),
        "parent_version_id": str(row["parent_version_id"]) if row["parent_version_id"] else None,
        "version_no": row["version_no"], "version_name": row["version_name"],
        "creation_reason": row["creation_reason"], "lifecycle_status": row["lifecycle_status"],
        "workflow_node": row["workflow_node"], "is_working": bool(row["is_working"]),
        "version": row["row_version"], "created_at": row["created_at"].replace(tzinfo=UTC).isoformat(),
    }


class Sprint1Service:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _jwt_secret(self) -> str:
        if not self.settings.access_jwt_secret:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="JWT signing secret is not configured", http_status=503)
        return self.settings.access_jwt_secret

    def _tokens(self, *, user_id: int, display_name: str, email: str, status: str, system_role: str, session_id: str) -> dict[str, Any]:
        token, _ = issue_access_token(
            user_id=user_id, session_id=session_id, secret=self._jwt_secret(),
            ttl_seconds=self.settings.access_jwt_ttl_seconds,
        )
        return {
            "user": _user_summary({"id": user_id, "display_name": display_name, "email": email, "status": status, "system_role": system_role}),
            "access_token": token, "token_type": "Bearer", "expires_in": self.settings.access_jwt_ttl_seconds,
        }

    def register(self, *, email: str, password: str, display_name: str, trace_id: str) -> tuple[dict[str, Any], str]:
        normalized = email.strip().casefold()
        if not 12 <= len(password) <= 128:
            raise ApiError(code="WEAK_PASSWORD", message="Password must contain 12 to 128 characters")
        refresh = new_refresh_token()
        session_public_id = str(uuid.uuid4())
        command_id = _command_id()
        now = _now()
        try:
            with transaction() as connection:
                result = connection.execute(
                    _sql(
                        "INSERT INTO user_account (created_at,created_by,updated_at,updated_by,row_version,"
                        "archived_at,archived_by,email,password_hash,display_name,system_role,status,last_login_at) "
                        "VALUES (:now,NULL,:now,NULL,1,NULL,NULL,:email,:password_hash,:display_name,'user','active',:now)"
                    ),
                    {"now": now, "email": normalized, "password_hash": hash_password(password), "display_name": display_name},
                )
                user_id = int(result.lastrowid)
                connection.execute(
                    _sql(
                        "INSERT INTO user_session (created_at,created_by,user_id,refresh_token_hash,session_public_id,"
                        "issued_at,expires_at,revoked_at,revoke_reason,token_family_id,rotated_at,replaced_by_session_id) "
                        "VALUES (:now,:user_id,:user_id,:token_hash,:session_id,:now,:expires,NULL,NULL,:session_id,NULL,NULL)"
                    ),
                    {"now": now, "user_id": user_id, "token_hash": hash_refresh_token(refresh), "session_id": session_public_id, "expires": now + timedelta(days=7)},
                )
                _audit(connection, actor_user_id=user_id, operation="auth.register", object_type="user_account", object_id=user_id, object_version_id=None, trace_id=trace_id, command_id=command_id)
                _identity_event(connection, event_name="identity.user.registered", trace_id=trace_id, command_id=command_id, user_id=user_id, session_id=session_public_id, payload={"producer_component": "business_api", "system_role": "user"})
        except Exception as exc:
            if exc.__class__.__name__ == "IntegrityError":
                _record_auth_failure(operation="auth.register", event_name=None, failure_code="EMAIL_EXISTS", trace_id=trace_id)
                raise ApiError(code="EMAIL_EXISTS", message="Email is already registered", http_status=409) from exc
            raise
        data = self._tokens(user_id=user_id, display_name=display_name, email=normalized, status="active", system_role="user", session_id=session_public_id)
        return data, f"{session_public_id}.{refresh}"

    def login(self, *, email: str, password: str, trace_id: str) -> tuple[dict[str, Any], str]:
        normalized = email.strip().casefold()
        invalid_user_id: int | None = None
        with transaction() as connection:
            user = _mapping(connection.execute(_sql("SELECT * FROM user_account WHERE email=:email AND status='active' FOR UPDATE"), {"email": normalized}))
            if not user or not verify_password(user["password_hash"], password):
                invalid_user_id = int(user["id"]) if user else None
            else:
                refresh = new_refresh_token()
                session_public_id = str(uuid.uuid4())
                now = _now()
                connection.execute(_sql("INSERT INTO user_session (created_at,created_by,user_id,refresh_token_hash,session_public_id,issued_at,expires_at,revoked_at,revoke_reason,token_family_id,rotated_at,replaced_by_session_id) VALUES (:now,:uid,:uid,:hash,:sid,:now,:expires,NULL,NULL,:sid,NULL,NULL)"), {"now": now, "uid": user["id"], "hash": hash_refresh_token(refresh), "sid": session_public_id, "expires": now + timedelta(days=7)})
                connection.execute(_sql("UPDATE user_account SET last_login_at=:now,updated_at=:now,row_version=row_version+1 WHERE id=:id"), {"now": now, "id": user["id"]})
                command_id = _command_id()
                _audit(connection, actor_user_id=user["id"], operation="auth.login", object_type="user_session", object_id=None, object_version_id=None, trace_id=trace_id, command_id=command_id)
                _identity_event(connection, event_name="identity.session.login_succeeded", trace_id=trace_id, command_id=command_id, user_id=user["id"], session_id=session_public_id, payload={"producer_component": "business_api", "authentication_method": "password"})
        if invalid_user_id is not None or not user:
            _record_auth_failure(operation="auth.login", event_name="identity.session.login_failed", failure_code="INVALID_CREDENTIALS", trace_id=trace_id, user_id=invalid_user_id)
            raise ApiError(code="INVALID_CREDENTIALS", message="Invalid email or password", http_status=401)
        return self._tokens(user_id=user["id"], display_name=user["display_name"], email=user["email"], status=user["status"], system_role=user["system_role"], session_id=session_public_id), f"{session_public_id}.{refresh}"

    def refresh(self, *, cookie: str, trace_id: str) -> tuple[dict[str, Any], str]:
        try:
            session_public_id, raw = cookie.split(".", 1)
        except ValueError as exc:
            raise ApiError(code="REFRESH_INVALID", message="Refresh token is invalid", http_status=401) from exc
        now = _now()
        replay_detected = False
        with transaction() as connection:
            session = _mapping(connection.execute(_sql("SELECT * FROM user_session WHERE session_public_id=:sid FOR UPDATE"), {"sid": session_public_id}))
            if not session or not hmac.compare_digest(session.get("refresh_token_hash", ""), hash_refresh_token(raw)):
                raise ApiError(code="REFRESH_INVALID", message="Refresh token is invalid", http_status=401)
            if session["rotated_at"] is not None:
                connection.execute(_sql("UPDATE user_session SET revoked_at=COALESCE(revoked_at,:now),revoke_reason='token_reuse' WHERE token_family_id=:family"), {"now": now, "family": session["token_family_id"]})
                command_id = _command_id()
                _audit(connection, actor_user_id=session["user_id"], operation="auth.refresh_replay", object_type="user_session", object_id=session["id"], object_version_id=None, trace_id=trace_id, command_id=command_id, result_status="blocked", failure_code="TOKEN_REUSE_DETECTED")
                _identity_event(connection, event_name="identity.session.refresh_replay_blocked", trace_id=trace_id, command_id=command_id, user_id=session["user_id"], session_id=session_public_id, payload={"producer_component": "business_api", "family_revoked": True}, result_status="blocked", failure_code="TOKEN_REUSE_DETECTED")
                replay_detected = True
            elif session["revoked_at"] is not None or session["expires_at"] <= now:
                raise ApiError(code="REFRESH_INVALID", message="Refresh token is invalid", http_status=401)
            else:
                successor_raw = new_refresh_token()
                successor_public_id = str(uuid.uuid4())
                result = connection.execute(_sql("INSERT INTO user_session (created_at,created_by,user_id,refresh_token_hash,session_public_id,issued_at,expires_at,revoked_at,revoke_reason,token_family_id,rotated_at,replaced_by_session_id) VALUES (:now,:uid,:uid,:hash,:sid,:now,:expires,NULL,NULL,:family,NULL,NULL)"), {"now": now, "uid": session["user_id"], "hash": hash_refresh_token(successor_raw), "sid": successor_public_id, "expires": now + timedelta(days=7), "family": session["token_family_id"]})
                successor_id = int(result.lastrowid)
                updated = connection.execute(_sql("UPDATE user_session SET rotated_at=:now,revoked_at=:now,revoke_reason='rotated',replaced_by_session_id=:successor WHERE id=:id AND rotated_at IS NULL"), {"now": now, "successor": successor_id, "id": session["id"]})
                if updated.rowcount != 1:
                    raise ApiError(code="TOKEN_REUSE_DETECTED", message="Concurrent refresh detected", http_status=401)
                user = _mapping(connection.execute(_sql("SELECT * FROM user_account WHERE id=:id"), {"id": session["user_id"]}))
                assert user
                command_id = _command_id()
                _audit(connection, actor_user_id=session["user_id"], operation="auth.refresh", object_type="user_session", object_id=successor_id, object_version_id=None, trace_id=trace_id, command_id=command_id, metadata={"predecessor_session_id": session["id"]})
                _identity_event(connection, event_name="identity.session.refreshed", trace_id=trace_id, command_id=command_id, user_id=session["user_id"], session_id=successor_public_id, payload={"producer_component": "business_api", "rotation_succeeded": True})
        if replay_detected:
            raise ApiError(code="TOKEN_REUSE_DETECTED", message="Refresh token reuse detected", http_status=401)
        access, _ = issue_access_token(user_id=user["id"], session_id=successor_public_id, secret=self._jwt_secret(), ttl_seconds=self.settings.access_jwt_ttl_seconds)
        return {"access_token": access, "token_type": "Bearer", "expires_in": self.settings.access_jwt_ttl_seconds}, f"{successor_public_id}.{successor_raw}"

    def authenticate(self, authorization: str | None) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(code="AUTH_REQUIRED", message="Authentication required", http_status=401)
        claims = decode_hs256(
            authorization[7:],
            self._jwt_secret(),
            audience="business-api",
            issuer="business-api",
            require_jti=True,
            max_ttl_seconds=self.settings.access_jwt_ttl_seconds,
        )
        with readonly() as connection:
            row = _mapping(connection.execute(_sql("SELECT u.*,s.id database_session_id,s.expires_at session_expires_at,s.revoked_at FROM user_account u JOIN user_session s ON s.user_id=u.id WHERE u.id=:uid AND s.session_public_id=:sid"), {"uid": int(claims["sub"]), "sid": claims["sid"]}))
        if not row or row["revoked_at"] is not None or row["session_expires_at"] <= _now() or row["status"] != "active":
            raise ApiError(code="AUTH_REQUIRED", message="Session is revoked or expired", http_status=401)
        row["session_public_id"] = claims["sid"]
        return row

    def authenticate_refresh_cookie(self, cookie: str | None) -> dict[str, Any]:
        if not cookie:
            raise ApiError(code="AUTH_REQUIRED", message="Authentication required", http_status=401)
        try:
            session_public_id, raw = cookie.split(".", 1)
        except ValueError as exc:
            raise ApiError(code="AUTH_REQUIRED", message="Authentication required", http_status=401) from exc
        with readonly() as connection:
            row = _mapping(connection.execute(_sql("SELECT u.*,s.id database_session_id,s.expires_at session_expires_at,s.revoked_at,s.refresh_token_hash FROM user_account u JOIN user_session s ON s.user_id=u.id WHERE s.session_public_id=:sid"), {"sid": session_public_id}))
        if not row or row["revoked_at"] is not None or row["session_expires_at"] <= _now() or not hmac.compare_digest(row["refresh_token_hash"], hash_refresh_token(raw)):
            raise ApiError(code="AUTH_REQUIRED", message="Authentication required", http_status=401)
        row["session_public_id"] = session_public_id
        return row

    def logout(self, *, user: dict[str, Any], trace_id: str) -> None:
        with transaction() as connection:
            connection.execute(_sql("UPDATE user_session SET revoked_at=COALESCE(revoked_at,:now),revoke_reason='logout' WHERE session_public_id=:sid"), {"now": _now(), "sid": user["session_public_id"]})
            command_id = _command_id()
            _audit(connection, actor_user_id=user["id"], operation="auth.logout", object_type="user_session", object_id=user["database_session_id"], object_version_id=None, trace_id=trace_id, command_id=command_id)
            _identity_event(connection, event_name="identity.session.logged_out", trace_id=trace_id, command_id=command_id, user_id=user["id"], session_id=user["session_public_id"], payload={"producer_component": "business_api", "revocation_reason": "logout"})

    def create_project(self, *, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        endpoint = "POST:/api/v1/projects"
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            if replay:
                project_id = int(replay)
                project = _project_summary(connection, project_id, user_id)
                version_row = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE project_id=:id AND version_no='V1'"), {"id": project_id}))
                assert version_row
                return {"project": project, "version": _version_summary(version_row), "working_version_id": str(version_row["id"])}
            now = _now()
            result = connection.execute(_sql("INSERT INTO project (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,owner_user_id,name,description,status,last_module) VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:uid,:name,:description,'active',NULL)"), {"now": now, "uid": user_id, "name": payload["name"], "description": payload.get("description")})
            project_id = int(result.lastrowid)
            workflow_node = "file_import" if payload.get("start_mode") == "import" else "project_context"
            version_result = connection.execute(_sql("INSERT INTO project_version (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_id,parent_version_id,version_no,version_name,creation_reason,lifecycle_status,workflow_node,is_working) VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:project_id,NULL,'V1','V1','initial project version','active',:workflow_node,1)"), {"now": now, "uid": user_id, "project_id": project_id, "workflow_node": workflow_node})
            version_id = int(version_result.lastrowid)
            connection.execute(_sql("INSERT INTO project_member (created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,role_code,status) VALUES (:now,:uid,:now,:uid,1,:project_id,:uid,'owner','active')"), {"now": now, "uid": user_id, "project_id": project_id})
            empty_hash = hashlib.sha256(b"{}").hexdigest()
            connection.execute(_sql("INSERT INTO project_context (created_at,created_by,updated_at,updated_by,row_version,project_id,background,business_goal,target_user,core_module_json,key_constraint,decision_summary,history_summary,content_hash) VALUES (:now,:uid,:now,:uid,1,:project_id,NULL,NULL,NULL,NULL,NULL,NULL,NULL,:hash)"), {"now": now, "uid": user_id, "project_id": project_id, "hash": empty_hash})
            command_id = _command_id()
            _audit(connection, actor_user_id=user_id, operation="project.create", object_type="project", object_id=project_id, object_version_id=version_id, trace_id=trace_id, command_id=command_id)
            _outbox(connection, aggregate_type="project", aggregate_id=project_id, aggregate_version=1, event_name="project.project.created", payload={"initial_version_id": str(version_id), "startup_mode": payload["start_mode"]}, trace_id=trace_id, command_id=command_id, module="project", user_id=user_id, project_id=project_id, project_version_id=version_id)
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(project_id))
            project = _project_summary(connection, project_id, user_id)
            version = _version_summary(_mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id"), {"id": version_id})))
        return {"project": project, "version": version, "working_version_id": str(version_id)}

    def get_project(self, *, project_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            return _project_summary(connection, project_id, user_id)

    def list_projects(self, *, user_id: int, limit: int = 20) -> dict[str, Any]:
        with readonly() as connection:
            ids = [row[0] for row in connection.execute(_sql("SELECT DISTINCT p.id,p.updated_at FROM project p JOIN project_member pm ON pm.project_id=p.id WHERE pm.user_id=:uid AND pm.status='active' ORDER BY p.updated_at DESC,p.id DESC LIMIT :limit"), {"uid": user_id, "limit": limit})]
            return {"items": [_project_summary(connection, project_id, user_id) for project_id in ids], "next_cursor": None, "has_more": False}

    def list_versions(self, *, project_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            _require_action(connection, project_id=project_id, user_id=user_id, action="version:view-history")
            rows = connection.execute(_sql("SELECT * FROM project_version WHERE project_id=:project_id ORDER BY created_at DESC,id DESC"), {"project_id": project_id}).mappings().all()
            return {"items": [_version_summary(dict(row)) for row in rows], "next_cursor": None, "has_more": False}

    def set_working(self, *, project_id: int, version_id: int, user_id: int, expected: int, reason: str, key: str, trace_id: str) -> dict[str, Any]:
        endpoint = f"POST:/api/v1/projects/{project_id}/versions/{version_id}:set-working"
        payload = {"version_id": version_id, "expected_project_version": expected, "reason": reason}
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            _require_action(connection, project_id=project_id, user_id=user_id, action="version:set-working")
            if replay:
                replay_data = json.loads(replay)
                previous = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id"), {"id": replay_data["previous_id"]}))
                current = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id"), {"id": replay_data["current_id"]}))
                assert previous and current
                return {"previous": _version_summary(previous), "current": _version_summary(current), "project_version": replay_data["project_version"]}
            project = _mapping(connection.execute(_sql("SELECT * FROM project WHERE id=:id FOR UPDATE"), {"id": project_id}))
            if not project or project["row_version"] != expected:
                raise ApiError(code="VERSION_CONFLICT", message="Project has changed", http_status=409, details=[{"field": "expected_project_version", "reason": f"latest={project['row_version'] if project else 'unknown'}"}])
            previous = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE project_id=:pid AND is_working=1 FOR UPDATE"), {"pid": project_id}))
            target = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id AND project_id=:pid FOR UPDATE"), {"id": version_id, "pid": project_id}))
            if not target:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            if not target["is_working"]:
                connection.execute(_sql("UPDATE project_version SET is_working=0,updated_at=:now,row_version=row_version+1 WHERE project_id=:pid AND is_working=1"), {"now": _now(), "pid": project_id})
                connection.execute(_sql("UPDATE project_version SET is_working=1,updated_at=:now,row_version=row_version+1 WHERE id=:id"), {"now": _now(), "id": version_id})
                connection.execute(_sql("UPDATE project SET updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE id=:pid"), {"now": _now(), "uid": user_id, "pid": project_id})
                command_id = _command_id()
                _audit(connection, actor_user_id=user_id, operation="project_version.set_working", object_type="project_version", object_id=version_id, object_version_id=version_id, trace_id=trace_id, command_id=command_id, reason=reason)
                _outbox(connection, aggregate_type="project", aggregate_id=project_id, aggregate_version=expected + 1, event_name="project.version.working_set", payload={"previous_working_version_id": str(previous["id"]), "new_working_version_id": str(version_id)}, trace_id=trace_id, command_id=command_id, module="project", user_id=user_id, project_id=project_id, project_version_id=version_id)
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=json.dumps({"previous_id": previous["id"], "current_id": version_id, "project_version": expected + 1}, separators=(",", ":")))
                result_project_version = expected + 1
            else:
                _audit(connection, actor_user_id=user_id, operation="project_version.set_working_noop", object_type="project_version", object_id=version_id, object_version_id=version_id, trace_id=trace_id, command_id=_command_id(), reason=reason)
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=json.dumps({"previous_id": version_id, "current_id": version_id, "project_version": expected}, separators=(",", ":")))
                result_project_version = expected
            current = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id"), {"id": version_id}))
            assert previous and current
            return {"previous": _version_summary(previous), "current": _version_summary(current), "project_version": result_project_version}

    def derive_version(self, *, project_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        endpoint = f"POST:/api/v1/projects/{project_id}/versions:derive"
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            _require_action(connection, project_id=project_id, user_id=user_id, action="version:derive")
            if replay:
                row = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id"), {"id": int(replay)}))
                assert row
                return _version_summary(row)
            project = _mapping(connection.execute(_sql("SELECT * FROM project WHERE id=:id FOR UPDATE"), {"id": project_id}))
            if not project or project["row_version"] != payload["expected_project_version"]:
                raise ApiError(code="VERSION_CONFLICT", message="Project has changed", http_status=409)
            source = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id AND project_id=:pid"), {"id": int(payload["source_version_id"]), "pid": project_id}))
            if not source:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Source version not found", http_status=404)
            next_no = int(connection.execute(_sql("SELECT COUNT(*) FROM project_version WHERE project_id=:pid"), {"pid": project_id}).scalar_one()) + 1
            now = _now()
            result = connection.execute(_sql("INSERT INTO project_version (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_id,parent_version_id,version_no,version_name,creation_reason,lifecycle_status,workflow_node,is_working) VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:pid,:parent,:version_no,:version_no,:reason,:lifecycle,:node,0)"), {"now": now, "uid": user_id, "pid": project_id, "parent": source["id"], "version_no": f"V{next_no}", "reason": payload["change_reason"], "lifecycle": source["lifecycle_status"], "node": source["workflow_node"]})
            version_id = int(result.lastrowid)
            command_id = _command_id()
            connection.execute(_sql("INSERT INTO version_change_record (created_at,created_by,project_id,from_version_id,to_version_id,source_issue_id,change_type,change_reason,inheritance_summary_json,trace_id) VALUES (:now,:uid,:pid,:source,:target,:issue,:change_type,:reason,:inheritance,:trace)"), {"now": now, "uid": user_id, "pid": project_id, "source": source["id"], "target": version_id, "issue": int(payload["source_issue_id"]) if payload.get("source_issue_id") else None, "change_type": payload["change_type"], "reason": payload["change_reason"], "inheritance": json.dumps(payload["inheritance_choices"]), "trace": trace_id})
            connection.execute(_sql("UPDATE project SET updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE id=:pid"), {"now": now, "uid": user_id, "pid": project_id})
            _audit(connection, actor_user_id=user_id, operation="project_version.derive", object_type="project_version", object_id=version_id, object_version_id=version_id, trace_id=trace_id, command_id=command_id, reason=payload["change_reason"])
            _outbox(connection, aggregate_type="project_version", aggregate_id=version_id, aggregate_version=1, event_name="project.version.derived", payload={"from_version_id": str(source["id"]), "inheritance_summary": payload["inheritance_choices"], "source_issue_id": payload.get("source_issue_id")}, trace_id=trace_id, command_id=command_id, module="project", user_id=user_id, project_id=project_id, project_version_id=version_id)
            _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(version_id))
            row = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id"), {"id": version_id}))
            assert row
            return _version_summary(row)

    def compare_versions(self, *, left_id: int, right_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            rows = connection.execute(_sql("SELECT * FROM project_version WHERE id IN (:left,:right)"), {"left": left_id, "right": right_id}).mappings().all()
            if len(rows) != 2 or rows[0]["project_id"] != rows[1]["project_id"]:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Comparable versions not found", http_status=404)
            _require_action(connection, project_id=rows[0]["project_id"], user_id=user_id, action="version:view-history")
            by_id = {row["id"]: row for row in rows}
            left, right = by_id[left_id], by_id[right_id]
            domains = [field for field in ("lifecycle_status", "workflow_node", "parent_version_id") if left[field] != right[field]]
            return {"left_version_id": str(left_id), "right_version_id": str(right_id), "changed_domains": domains, "summary": f"{len(domains)} version domains changed", "source_refs": []}

    def _signer(self) -> S3Signer:
        if not self.settings.object_storage_access_key or not self.settings.object_storage_secret_key:
            raise ApiError(code="STORAGE_UNAVAILABLE", message="Object storage is not configured", http_status=503)
        return S3Signer(endpoint=self.settings.object_storage_endpoint, bucket=self.settings.object_storage_bucket, region=self.settings.object_storage_region, access_key=self.settings.object_storage_access_key, secret_key=self.settings.object_storage_secret_key)

    def _storage(self) -> S3ObjectStorage:
        return S3ObjectStorage(self._signer())

    def _upload_token(self, payload: dict[str, Any]) -> str:
        secret = self.settings.upload_signing_secret
        if not secret:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Upload signing secret is not configured", http_status=503)
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def init_upload(self, *, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        project_id = int(payload["project_id"])
        endpoint = "POST:/api/v1/files/uploads"
        signer = self._signer()
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            _require_action(connection, project_id=project_id, user_id=user_id, action="file:upload")
            if payload.get("relation"):
                _validate_relation_target(
                    connection, project_id=project_id, relation=payload["relation"]
                )
            if replay:
                version_id = int(replay)
                row = _mapping(connection.execute(_sql("SELECT fv.*,sf.id stored_id FROM file_version fv JOIN stored_file sf ON sf.id=fv.stored_file_id WHERE fv.id=:id"), {"id": version_id}))
                assert row
                stored_id, object_key = row["stored_id"], row["object_key"]
            else:
                now = _now()
                file_result = connection.execute(_sql("INSERT INTO stored_file (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,owner_user_id,project_id,logical_name,status,current_version_id) VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:uid,:pid,:name,'pending',NULL)"), {"now": now, "uid": user_id, "pid": project_id, "name": payload["logical_name"]})
                stored_id = int(file_result.lastrowid)
                object_key = f"projects/{project_id}/files/{stored_id}/{uuid.uuid4().hex}"
                pending_metadata = json.dumps(
                    {
                        "actor_user_id": user_id,
                        "relation": payload.get("relation"),
                    },
                    separators=(",", ":"),
                )
                version_result = connection.execute(_sql("INSERT INTO file_version (created_at,created_by,stored_file_id,version_no,object_key,mime_type,extension,size_bytes,checksum_sha256,storage_status,change_note) VALUES (:now,:uid,:stored,'V1',:object_key,:mime,:extension,:size,:checksum,'pending',:metadata)"), {"now": now, "uid": user_id, "stored": stored_id, "object_key": object_key, "mime": payload["mime_type"], "extension": payload.get("extension"), "size": payload["size_bytes"], "checksum": payload["checksum_sha256"], "metadata": pending_metadata})
                version_id = int(version_result.lastrowid)
                command_id = _command_id()
                _audit(
                    connection,
                    actor_user_id=user_id,
                    operation="file.upload_init",
                    object_type="file_version",
                    object_id=stored_id,
                    object_version_id=version_id,
                    trace_id=trace_id,
                    command_id=command_id,
                )
                _outbox(
                    connection,
                    aggregate_type="stored_file",
                    aggregate_id=stored_id,
                    aggregate_version=1,
                    event_name="file.upload.started",
                    payload={
                        "file_version_id": str(version_id),
                        "size_bytes": payload["size_bytes"],
                        "mime_type": payload["mime_type"],
                    },
                    trace_id=trace_id,
                    command_id=command_id,
                    module="file",
                    user_id=user_id,
                    project_id=project_id,
                )
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(version_id))
            signed = signer.presign(
                method="PUT",
                object_key=object_key,
                required_headers={
                    "content-type": payload["mime_type"],
                    "x-amz-checksum-sha256": checksum_sha256_base64(
                        payload["checksum_sha256"]
                    ),
                },
            )
            upload_id = self._upload_token({"v": version_id, "u": user_id, "exp": int(signed.expires_at.timestamp())})
            return {"upload_id": upload_id, "stored_file_id": str(stored_id), "pending_file_version_id": str(version_id), "upload_url": signed.url, "http_method": "PUT", "required_headers": signed.required_headers, "expires_at": signed.expires_at.isoformat(), "max_size_bytes": 52_428_800}

    def update_project(self, *, project_id: int, user_id: int, payload: dict[str, Any], trace_id: str) -> dict[str, Any]:
        with transaction() as connection:
            _require_action(connection, project_id=project_id, user_id=user_id, action="project:update")
            project = _mapping(connection.execute(_sql("SELECT * FROM project WHERE id=:id FOR UPDATE"), {"id": project_id}))
            if not project or project["row_version"] != payload["expected_version"]:
                raise ApiError(code="VERSION_CONFLICT", message="Project has changed", http_status=409)
            connection.execute(_sql("UPDATE project SET name=:name,description=:description,updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE id=:id"), {"name": payload.get("name", project["name"]), "description": payload.get("description", project["description"]), "now": _now(), "uid": user_id, "id": project_id})
            _audit(connection, actor_user_id=user_id, operation="project.update", object_type="project", object_id=project_id, object_version_id=None, trace_id=trace_id, command_id=_command_id())
            return _project_summary(connection, project_id, user_id)

    def project_lifecycle(self, *, project_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str, restore: bool) -> dict[str, Any]:
        action = "project:restore" if restore else "project:archive"
        endpoint = f"POST:/api/v1/projects/{project_id}:{'restore' if restore else 'archive'}"
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            _require_action(connection, project_id=project_id, user_id=user_id, action=action)
            project = _mapping(connection.execute(_sql("SELECT * FROM project WHERE id=:id FOR UPDATE"), {"id": project_id}))
            if not project or (not replay and project["row_version"] != payload["expected_version"]):
                raise ApiError(code="VERSION_CONFLICT", message="Project has changed", http_status=409)
            desired = "active" if restore else "archived"
            if not replay and project["status"] != desired:
                now = _now()
                connection.execute(_sql("UPDATE project SET status=:status,archived_at=:archived_at,archived_by=:archived_by,updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE id=:id"), {"status": desired, "archived_at": None if restore else now, "archived_by": None if restore else user_id, "now": now, "uid": user_id, "id": project_id})
                command_id = _command_id()
                _audit(connection, actor_user_id=user_id, operation=f"project.{'restore' if restore else 'archive'}", object_type="project", object_id=project_id, object_version_id=None, trace_id=trace_id, command_id=command_id, reason=payload["reason"])
                _outbox(connection, aggregate_type="project", aggregate_id=project_id, aggregate_version=project["row_version"] + 1, event_name=f"project.project.{'restored' if restore else 'archived'}", payload={"reason_class": "user_command"}, trace_id=trace_id, command_id=command_id, module="project", user_id=user_id, project_id=project_id)
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(project_id))
            elif not replay:
                _audit(connection, actor_user_id=user_id, operation=f"project.{'restore' if restore else 'archive'}_noop", object_type="project", object_id=project_id, object_version_id=None, trace_id=trace_id, command_id=_command_id(), reason=payload["reason"])
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(project_id))
            return _project_summary(connection, project_id, user_id)

    def get_version(self, *, version_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            row = _mapping(connection.execute(_sql("SELECT * FROM project_version WHERE id=:id"), {"id": version_id}))
            if not row:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            _require_action(connection, project_id=row["project_id"], user_id=user_id, action="version:view-history")
            return _version_summary(row)

    def get_context(self, *, project_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            _require_action(connection, project_id=project_id, user_id=user_id, action="project:view")
            row = _mapping(connection.execute(_sql("SELECT * FROM project_context WHERE project_id=:id"), {"id": project_id}))
            if not row:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Context not found", http_status=404)
            return {"background": row["background"], "business_goal": row["business_goal"], "target_user": row["target_user"], "core_modules": row["core_module_json"], "key_constraint": row["key_constraint"], "decision_summary": row["decision_summary"], "history_summary": row["history_summary"], "content_hash": row["content_hash"], "version": row["row_version"]}

    def update_context(self, *, project_id: int, user_id: int, payload: dict[str, Any], trace_id: str) -> dict[str, Any]:
        with transaction() as connection:
            _require_action(connection, project_id=project_id, user_id=user_id, action="project:update")
            row = _mapping(connection.execute(_sql("SELECT * FROM project_context WHERE project_id=:id FOR UPDATE"), {"id": project_id}))
            if not row or row["row_version"] != payload["expected_version"]:
                raise ApiError(code="VERSION_CONFLICT", message="Project Context has changed", http_status=409)
            fields = {name: payload.get(name, row["core_module_json" if name == "core_modules" else name]) for name in ("background", "business_goal", "target_user", "core_modules", "key_constraint", "decision_summary", "history_summary")}
            digest = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            sql_fields = {**fields, "core_modules": json.dumps(fields["core_modules"]) if fields["core_modules"] is not None else None}
            connection.execute(_sql("UPDATE project_context SET background=:background,business_goal=:business_goal,target_user=:target_user,core_module_json=:core_modules,key_constraint=:key_constraint,decision_summary=:decision_summary,history_summary=:history_summary,content_hash=:hash,updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE project_id=:pid"), {**sql_fields, "hash": digest, "now": _now(), "uid": user_id, "pid": project_id})
            _audit(connection, actor_user_id=user_id, operation="project_context.update", object_type="project_context", object_id=row["id"], object_version_id=None, trace_id=trace_id, command_id=_command_id())
        return self.get_context(project_id=project_id, user_id=user_id)

    def list_members(self, *, project_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            _require_action(connection, project_id=project_id, user_id=user_id, action="project:view")
            rows = connection.execute(_sql("SELECT user_id,role_code,status,row_version FROM project_member WHERE project_id=:pid ORDER BY user_id,role_code"), {"pid": project_id}).mappings().all()
            grouped: dict[int, dict[str, Any]] = {}
            for row in rows:
                item = grouped.setdefault(row["user_id"], {"user_id": str(row["user_id"]), "roles": [], "status": row["status"], "permission_version": row["row_version"]})
                item["roles"].append(row["role_code"])
                item["permission_version"] = max(item["permission_version"], row["row_version"])
            return {"items": list(grouped.values())}

    def put_member(self, *, project_id: int, target_user_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        endpoint = f"PUT:/api/v1/projects/{project_id}/members/{target_user_id}"
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            _require_action(connection, project_id=project_id, user_id=user_id, action="project:manage-members")
            current = connection.execute(_sql("SELECT * FROM project_member WHERE project_id=:pid AND user_id=:uid FOR UPDATE"), {"pid": project_id, "uid": target_user_id}).mappings().all()
            latest = max((row["row_version"] for row in current), default=0)
            if not replay and latest != payload["expected_permission_version"]:
                raise ApiError(code="VERSION_CONFLICT", message="Permission version has changed", http_status=409)
            if not replay:
                roles = sorted(set(payload["roles"]))
                if target_user_id == user_id and "owner" not in roles:
                    raise ApiError(code="FORBIDDEN", message="Owner cannot remove own owner role")
                connection.execute(_sql("DELETE FROM project_member WHERE project_id=:pid AND user_id=:uid"), {"pid": project_id, "uid": target_user_id})
                now = _now()
                for role in roles:
                    connection.execute(_sql("INSERT INTO project_member (created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,role_code,status) VALUES (:now,:actor,:now,:actor,:version,:pid,:uid,:role,'active')"), {"now": now, "actor": user_id, "version": latest + 1, "pid": project_id, "uid": target_user_id, "role": role})
                command_id = _command_id()
                _audit(connection, actor_user_id=user_id, operation="project_member.put", object_type="project_member", object_id=target_user_id, object_version_id=None, trace_id=trace_id, command_id=command_id, metadata={"roles": roles})
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(target_user_id))
            rows = connection.execute(_sql("SELECT role_code,row_version,status FROM project_member WHERE project_id=:pid AND user_id=:uid"), {"pid": project_id, "uid": target_user_id}).mappings().all()
            return {"user_id": str(target_user_id), "roles": [row["role_code"] for row in rows], "status": rows[0]["status"], "permission_version": max(row["row_version"] for row in rows)}

    def _decode_upload_token(
        self,
        upload_id: str,
        user_id: int,
        *,
        allow_expired: bool = False,
    ) -> dict[str, Any]:
        secret = self.settings.upload_signing_secret
        if not secret:
            raise ApiError(code="DEPENDENCY_UNAVAILABLE", message="Upload signing secret is not configured", http_status=503)
        try:
            body, supplied = upload_id.rsplit(".", 1)
            expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, supplied):
                raise ValueError("signature")
            claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if claims["u"] != user_id:
                raise ValueError("claims")
            if not allow_expired and claims["exp"] < int(datetime.now(UTC).timestamp()):
                raise ValueError("expired")
            return claims
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ApiError(code="UPLOAD_INCOMPLETE", message="Upload reference is invalid or expired", http_status=409) from exc

    def complete_upload(self, *, upload_id: str, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        claims = self._decode_upload_token(upload_id, user_id, allow_expired=True)
        version_id = int(claims["v"])
        endpoint = f"POST:/api/v1/files/uploads/{{upload_id}}:complete:v{version_id}"
        with readonly() as connection:
            replay = _idempotency_lookup(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            if replay:
                return self.get_file(file_id=int(replay), user_id=user_id)
        if claims["exp"] < int(datetime.now(UTC).timestamp()):
            raise ApiError(code="UPLOAD_INCOMPLETE", message="Upload reference is expired", http_status=409)
        with readonly() as connection:
            pending = _mapping(connection.execute(_sql("SELECT fv.*,sf.project_id,sf.owner_user_id FROM file_version fv JOIN stored_file sf ON sf.id=fv.stored_file_id WHERE fv.id=:id"), {"id": version_id}))
        if not pending or pending["storage_status"] != "pending":
            raise ApiError(code="UPLOAD_INCOMPLETE", message="Upload is not pending", http_status=409)
        if pending["owner_user_id"] != user_id:
            raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
        if pending["checksum_sha256"] != payload["checksum_sha256"]:
            raise ApiError(code="CHECKSUM_MISMATCH", message="Checksum does not match the initialized upload", http_status=409)
        # Storage verification/finalization is intentionally outside the MySQL
        # transaction. A DB failure leaves a server-owned orphan for cleanup,
        # never an available business file.
        temporary_key = pending["object_key"]
        final_key = (
            f"projects/{pending['project_id']}/files/{pending['stored_file_id']}/"
            f"final/{version_id}-{pending['checksum_sha256']}"
        )
        finalized = self._storage().finalize(
            temporary_key=temporary_key,
            final_key=final_key,
            expected_size=pending["size_bytes"],
            expected_content_type=pending["mime_type"],
            expected_checksum_hex=pending["checksum_sha256"],
        )
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            row = _mapping(connection.execute(_sql("SELECT fv.*,sf.project_id,sf.owner_user_id FROM file_version fv JOIN stored_file sf ON sf.id=fv.stored_file_id WHERE fv.id=:id FOR UPDATE"), {"id": version_id}))
            assert row
            _require_action(connection, project_id=row["project_id"], user_id=user_id, action="file:upload")
            if not replay and row["storage_status"] != "pending":
                raise ApiError(code="UPLOAD_INCOMPLETE", message="Upload was already finalized", http_status=409)
            if not replay:
                updated = connection.execute(
                    _sql(
                        "UPDATE file_version SET storage_status='available',object_key=:object_key,"
                        "storage_version_id=:storage_version_id "
                        "WHERE id=:id AND storage_status='pending'"
                    ),
                    {
                        "id": version_id,
                        "object_key": finalized.object_key,
                        "storage_version_id": finalized.storage_version_id,
                    },
                )
                if updated.rowcount != 1:
                    raise ApiError(code="UPLOAD_INCOMPLETE", message="Upload was concurrently finalized", http_status=409)
                connection.execute(_sql("UPDATE stored_file SET status='active',current_version_id=:version,updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE id=:file"), {"version": version_id, "now": _now(), "uid": user_id, "file": row["stored_file_id"]})
                metadata = json.loads(row["change_note"] or "{}")
                relation = metadata.get("relation")
                relation_id = None
                if relation:
                    _validate_relation_target(
                        connection, project_id=row["project_id"], relation=relation
                    )
                    relation_result = connection.execute(_sql("INSERT INTO file_relation (created_at,created_by,file_version_id,object_type,object_id,object_version_id,relation_type) VALUES (:now,:uid,:version,:object_type,:object_id,:object_version_id,:relation_type)"), {"now": _now(), "uid": user_id, "version": version_id, "object_type": relation["object_type"], "object_id": int(relation["object_id"]), "object_version_id": int(relation["object_version_id"]) if relation.get("object_version_id") else None, "relation_type": relation["relation_type"]})
                    relation_id = int(relation_result.lastrowid)
                command_id = _command_id()
                _audit(connection, actor_user_id=user_id, operation="file.upload_complete", object_type="file_version", object_id=row["stored_file_id"], object_version_id=version_id, trace_id=trace_id, command_id=command_id, metadata={"relation_id": relation_id})
                _outbox(connection, aggregate_type="stored_file", aggregate_id=row["stored_file_id"], aggregate_version=1, event_name="file.upload.completed", payload={"file_version_id": str(version_id), "checksum_sha256": row["checksum_sha256"], "duration_ms": 0}, trace_id=trace_id, command_id=command_id, module="file", user_id=user_id, project_id=row["project_id"])
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(row["stored_file_id"]))
        return self.get_file(file_id=row["stored_file_id"], user_id=user_id)

    def abort_upload(self, *, upload_id: str, user_id: int, reason: str, key: str, trace_id: str) -> dict[str, Any]:
        claims = self._decode_upload_token(upload_id, user_id, allow_expired=True)
        version_id = int(claims["v"])
        endpoint = f"POST:/api/v1/files/uploads/{{upload_id}}:abort:v{version_id}"
        with transaction() as connection:
            existing = _idempotency_lookup(
                connection,
                user_id=user_id,
                endpoint=endpoint,
                key=key,
                payload={"reason": reason},
            )
            if existing:
                return {"aborted": True}
            if claims["exp"] < int(datetime.now(UTC).timestamp()):
                raise ApiError(code="UPLOAD_INCOMPLETE", message="Upload reference is expired", http_status=409)
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload={"reason": reason})
            row = _mapping(connection.execute(_sql("SELECT fv.*,sf.project_id,sf.owner_user_id FROM file_version fv JOIN stored_file sf ON sf.id=fv.stored_file_id WHERE fv.id=:id FOR UPDATE"), {"id": version_id}))
            if not row or row["owner_user_id"] != user_id:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            if not replay and row["storage_status"] == "pending":
                connection.execute(_sql("UPDATE file_version SET storage_status='aborted',change_note=:reason WHERE id=:id"), {"reason": reason, "id": row["id"]})
                connection.execute(_sql("UPDATE stored_file SET status='failed',updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE id=:id"), {"now": _now(), "uid": user_id, "id": row["stored_file_id"]})
                _audit(connection, actor_user_id=user_id, operation="file.upload_abort", object_type="file_version", object_id=row["stored_file_id"], object_version_id=row["id"], trace_id=trace_id, command_id=_command_id(), reason=reason, metadata={"orphan_cleanup_candidate": True})
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(row["id"]))
            elif not replay:
                raise ApiError(
                    code="UPLOAD_INCOMPLETE",
                    message=f"Upload is already in terminal state: {row['storage_status']}",
                    http_status=409,
                )
            return {"aborted": True}

    def get_file(self, *, file_id: int, user_id: int) -> dict[str, Any]:
        with readonly() as connection:
            row = _mapping(connection.execute(_sql("SELECT sf.*,fv.id version_id,fv.version_no,fv.mime_type,fv.extension,fv.size_bytes,fv.checksum_sha256,fv.storage_status,fv.created_at version_created_at FROM stored_file sf LEFT JOIN file_version fv ON fv.id=sf.current_version_id AND fv.storage_status='available' WHERE sf.id=:id"), {"id": file_id}))
            if not row or not row["project_id"]:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            _require_action(connection, project_id=row["project_id"], user_id=user_id, action="file:download")
            relations = [dict(item) for item in connection.execute(_sql("SELECT object_type,object_id,object_version_id,relation_type FROM file_relation WHERE file_version_id=:id"), {"id": row["version_id"]}).mappings().all()] if row["version_id"] else []
            current = None if not row["version_id"] else {"id": str(row["version_id"]), "stored_file_id": str(file_id), "version_no": row["version_no"], "mime_type": row["mime_type"], "extension": row["extension"], "size_bytes": row["size_bytes"], "checksum_sha256": row["checksum_sha256"], "storage_status": row["storage_status"], "created_at": row["version_created_at"].replace(tzinfo=UTC).isoformat()}
            return {"file": {"id": str(file_id), "project_id": str(row["project_id"]), "logical_name": row["logical_name"], "status": row["status"], "current_version_id": str(row["current_version_id"]) if row["current_version_id"] else None, "version": row["row_version"]}, "current_version": current, "relations": [{**relation, "object_id": str(relation["object_id"]), "object_version_id": str(relation["object_version_id"]) if relation["object_version_id"] else None} for relation in relations]}

    def list_file_versions(self, *, file_id: int, user_id: int) -> dict[str, Any]:
        file_data = self.get_file(file_id=file_id, user_id=user_id)
        with readonly() as connection:
            rows = connection.execute(_sql("SELECT * FROM file_version WHERE stored_file_id=:id AND storage_status='available' ORDER BY created_at DESC,id DESC"), {"id": file_id}).mappings().all()
            items = [{"id": str(row["id"]), "stored_file_id": str(file_id), "version_no": row["version_no"], "mime_type": row["mime_type"], "extension": row["extension"], "size_bytes": row["size_bytes"], "checksum_sha256": row["checksum_sha256"], "storage_status": row["storage_status"], "created_at": row["created_at"].replace(tzinfo=UTC).isoformat()} for row in rows]
        return {"items": items, "next_cursor": None, "has_more": False}

    def download(self, *, version_id: int, user_id: int, disposition: str, trace_id: str) -> dict[str, Any]:
        with transaction() as connection:
            row = _mapping(connection.execute(_sql("SELECT fv.*,sf.project_id,sf.logical_name FROM file_version fv JOIN stored_file sf ON sf.id=fv.stored_file_id WHERE fv.id=:id AND fv.storage_status='available'"), {"id": version_id}))
            if not row:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            _require_action(connection, project_id=row["project_id"], user_id=user_id, action="file:download")
            _audit(connection, actor_user_id=user_id, operation="file.download_sign", object_type="file_version", object_id=row["stored_file_id"], object_version_id=version_id, trace_id=trace_id, command_id=_command_id(), metadata={"disposition": disposition})
        signed = self._signer().presign(method="GET", object_key=row["object_key"], expires_seconds=300)
        return {"download_url": signed.url, "expires_at": signed.expires_at.isoformat(), "file_name": row["logical_name"], "mime_type": row["mime_type"], "size_bytes": row["size_bytes"]}

    def create_relation(self, *, version_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        endpoint = f"POST:/api/v1/file-versions/{version_id}/relations"
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            row = _mapping(connection.execute(_sql("SELECT fv.*,sf.project_id FROM file_version fv JOIN stored_file sf ON sf.id=fv.stored_file_id WHERE fv.id=:id AND fv.storage_status='available'"), {"id": version_id}))
            if not row:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            _require_action(connection, project_id=row["project_id"], user_id=user_id, action="file:relate")
            _validate_relation_target(
                connection, project_id=row["project_id"], relation=payload
            )
            if not replay:
                result = connection.execute(_sql("INSERT INTO file_relation (created_at,created_by,file_version_id,object_type,object_id,object_version_id,relation_type) VALUES (:now,:uid,:version,:object_type,:object_id,:object_version_id,:relation_type)"), {"now": _now(), "uid": user_id, "version": version_id, "object_type": payload["object_type"], "object_id": int(payload["object_id"]), "object_version_id": int(payload["object_version_id"]) if payload.get("object_version_id") else None, "relation_type": payload["relation_type"]})
                relation_id = int(result.lastrowid)
                command_id = _command_id()
                _audit(connection, actor_user_id=user_id, operation="file.relate", object_type="file_relation", object_id=relation_id, object_version_id=version_id, trace_id=trace_id, command_id=command_id)
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(relation_id))
            return payload

    def archive_file(self, *, file_id: int, user_id: int, payload: dict[str, Any], key: str, trace_id: str) -> dict[str, Any]:
        endpoint = f"POST:/api/v1/files/{file_id}:archive"
        with transaction() as connection:
            replay = _idempotency_begin(connection, user_id=user_id, endpoint=endpoint, key=key, payload=payload)
            row = _mapping(connection.execute(_sql("SELECT * FROM stored_file WHERE id=:id FOR UPDATE"), {"id": file_id}))
            if not row or not row["project_id"]:
                raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", http_status=404)
            roles = _project_roles(connection, row["project_id"], user_id)
            if "owner" not in roles and row["owner_user_id"] != user_id:
                raise ApiError(code="FORBIDDEN", message="File archive is not allowed", http_status=403)
            if not replay and row["row_version"] != payload["expected_version"]:
                raise ApiError(code="VERSION_CONFLICT", message="File has changed", http_status=409)
            if not replay and row["status"] != "archived":
                now = _now()
                connection.execute(_sql("UPDATE stored_file SET status='archived',archived_at=:now,archived_by=:uid,updated_at=:now,updated_by=:uid,row_version=row_version+1 WHERE id=:id"), {"now": now, "uid": user_id, "id": file_id})
                command_id = _command_id()
                _audit(connection, actor_user_id=user_id, operation="file.archive", object_type="stored_file", object_id=file_id, object_version_id=row["current_version_id"], trace_id=trace_id, command_id=command_id, reason=payload["reason"])
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(file_id))
            elif not replay:
                _idempotency_complete(connection, user_id=user_id, endpoint=endpoint, key=key, response_ref=str(file_id))
        return self.get_file(file_id=file_id, user_id=user_id)
