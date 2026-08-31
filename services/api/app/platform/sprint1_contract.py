from __future__ import annotations

from copy import deepcopy
from typing import Any


def _string(*, nullable: bool = False, **constraints: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": ["string", "null"] if nullable else "string"}
    schema.update(constraints)
    return schema


def _object(
    properties: dict[str, Any],
    required: list[str] | None = None,
    *,
    additional_properties: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": additional_properties,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _envelope(data_ref: str) -> dict[str, Any]:
    return _object(
        {
            "code": {"type": "string", "const": "OK"},
            "message": {"type": "string"},
            "data": {"$ref": f"#/components/schemas/{data_ref}"},
            "trace_id": {"type": "string"},
        },
        ["code", "message", "data", "trace_id"],
    )


def _parameter(name: str, *, location: str = "path", required: bool = True) -> dict[str, Any]:
    return {"name": name, "in": location, "required": required, "schema": {"type": "string"}}


PROJECT_ID = _parameter("project_id")
VERSION_ID = _parameter("version_id")
FILE_ID = _parameter("file_id")
UPLOAD_ID = _parameter("upload_id")
USER_ID = _parameter("user_id")


def _operation(
    operation_id: str,
    tag: str,
    response_schema: str,
    *,
    request_schema: str | None = None,
    security: list[dict[str, list[str]]] | None = None,
    parameters: list[dict[str, Any]] | None = None,
    idempotent: bool = False,
    description: str | None = None,
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "tags": [tag],
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{response_schema}"}
                    }
                },
            }
        },
        "security": security if security is not None else [{"bearerAuth": []}],
        "x-contract-phase": "sprint-1-candidate",
        "x-implementation-status": "implemented-candidate",
    }
    operation_parameters = deepcopy(parameters or [])
    if idempotent:
        operation_parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
        operation["x-idempotency-scope"] = "actor+endpoint+request-hash"
    if operation_parameters:
        operation["parameters"] = operation_parameters
    if request_schema:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{request_schema}"}
                }
            },
        }
    if description:
        operation["description"] = description
    return operation


SPRINT1_SCHEMAS: dict[str, dict[str, Any]] = {
    "UserSummary": _object(
        {
            "id": _string(),
            "email": _string(format="email"),
            "display_name": _string(),
            "system_roles": {"type": "array", "items": {"enum": ["admin"]}},
            "status": {"type": "string", "enum": ["active", "disabled", "archived"]},
        },
        ["id", "email", "display_name", "system_roles", "status"],
    ),
    "AuthRegisterRequest": _object(
        {
            "email": _string(format="email", maxLength=254),
            "password": _string(minLength=8, maxLength=128, format="password"),
            "display_name": _string(minLength=1, maxLength=128),
        },
        ["email", "password", "display_name"],
    ),
    "AuthLoginRequest": _object(
        {
            "email": _string(format="email", maxLength=254),
            "password": _string(format="password", maxLength=128),
        },
        ["email", "password"],
    ),
    "AuthTokenData": _object(
        {
            "user": {"$ref": "#/components/schemas/UserSummary"},
            "access_token": _string(),
            "token_type": {"type": "string", "const": "Bearer"},
            "expires_in": {"type": "integer", "minimum": 1},
        },
        ["user", "access_token", "token_type", "expires_in"],
    ),
    "AuthTokenResponse": _envelope("AuthTokenData"),
    "RefreshTokenData": _object(
        {
            "access_token": _string(),
            "token_type": {"type": "string", "const": "Bearer"},
            "expires_in": {"type": "integer", "minimum": 1},
        },
        ["access_token", "token_type", "expires_in"],
    ),
    "RefreshTokenResponse": _envelope("RefreshTokenData"),
    "LogoutData": _object({"logged_out": {"type": "boolean", "const": True}}, ["logged_out"]),
    "LogoutResponse": _envelope("LogoutData"),
    "SessionData": _object(
        {
            "user": {"$ref": "#/components/schemas/UserSummary"},
            "system_roles": {"type": "array", "items": {"enum": ["admin"]}},
            "session_id": _string(format="uuid"),
            "expires_at": _string(format="date-time"),
        },
        ["user", "system_roles", "session_id", "expires_at"],
    ),
    "SessionResponse": _envelope("SessionData"),
    "ProjectRole": {"type": "string", "enum": ["owner", "reviewer", "implementer", "tester"]},
    "PermissionSummary": _object(
        {
            "roles": {"type": "array", "items": {"$ref": "#/components/schemas/ProjectRole"}},
            "allowed_actions": {"type": "array", "items": {"type": "string"}},
            "permission_version": {"type": "integer", "minimum": 1},
        },
        ["roles", "allowed_actions", "permission_version"],
    ),
    "ProjectSummary": _object(
        {
            "id": _string(),
            "name": _string(),
            "description": _string(nullable=True),
            "status": {"type": "string", "enum": ["active", "archived"]},
            "working_version_id": _string(),
            "working_version_no": _string(),
            "last_module": _string(nullable=True),
            "updated_at": _string(format="date-time"),
            "version": {"type": "integer", "minimum": 1},
            "permissions": {"$ref": "#/components/schemas/PermissionSummary"},
        },
        ["id", "name", "status", "working_version_id", "working_version_no", "updated_at", "version", "permissions"],
    ),
    "ProjectVersionSummary": _object(
        {
            "id": _string(),
            "project_id": _string(),
            "parent_version_id": _string(nullable=True),
            "version_no": _string(),
            "version_name": _string(nullable=True),
            "creation_reason": _string(),
            "lifecycle_status": _string(),
            "workflow_node": _string(),
            "is_working": {"type": "boolean"},
            "version": {"type": "integer", "minimum": 1},
            "created_at": _string(format="date-time"),
        },
        ["id", "project_id", "version_no", "creation_reason", "lifecycle_status", "workflow_node", "is_working", "version", "created_at"],
    ),
    "CreateProjectRequest": _object(
        {
            "name": _string(minLength=1, maxLength=160),
            "description": _string(nullable=True, maxLength=5000),
            "start_mode": {"type": "string", "enum": ["new", "import"]},
        },
        ["name", "start_mode"],
    ),
    "CreateProjectData": _object(
        {
            "project": {"$ref": "#/components/schemas/ProjectSummary"},
            "version": {"$ref": "#/components/schemas/ProjectVersionSummary"},
            "working_version_id": _string(),
        },
        ["project", "version", "working_version_id"],
    ),
    "CreateProjectResponse": _envelope("CreateProjectData"),
    "ProjectResponse": _envelope("ProjectSummary"),
    "ProjectListData": _object(
        {
            "items": {"type": "array", "items": {"$ref": "#/components/schemas/ProjectSummary"}},
            "next_cursor": _string(nullable=True),
            "has_more": {"type": "boolean"},
        },
        ["items", "next_cursor", "has_more"],
    ),
    "ProjectListResponse": _envelope("ProjectListData"),
    "UpdateProjectRequest": _object(
        {
            "name": _string(minLength=1, maxLength=160),
            "description": _string(nullable=True, maxLength=5000),
            "expected_version": {"type": "integer", "minimum": 1},
        },
        ["expected_version"],
    ),
    "ProjectCommandRequest": _object(
        {"reason": _string(minLength=1, maxLength=1000), "expected_version": {"type": "integer", "minimum": 1}},
        ["reason", "expected_version"],
    ),
    "SetWorkingVersionRequest": _object(
        {"expected_project_version": {"type": "integer", "minimum": 1}, "reason": _string(minLength=1, maxLength=1000)},
        ["expected_project_version", "reason"],
    ),
    "WorkingVersionChangeData": _object(
        {
            "previous": {"$ref": "#/components/schemas/ProjectVersionSummary"},
            "current": {"$ref": "#/components/schemas/ProjectVersionSummary"},
            "project_version": {"type": "integer", "minimum": 1},
        },
        ["previous", "current", "project_version"],
    ),
    "WorkingVersionChangeResponse": _envelope("WorkingVersionChangeData"),
    "DeriveProjectVersionRequest": _object(
        {
            "source_version_id": _string(),
            "source_issue_id": _string(nullable=True),
            "change_type": _string(minLength=1, maxLength=32),
            "change_reason": _string(minLength=1, maxLength=2000),
            "inheritance_choices": {"type": "object", "additionalProperties": {"type": "boolean"}},
            "expected_project_version": {"type": "integer", "minimum": 1},
        },
        ["source_version_id", "change_type", "change_reason", "inheritance_choices", "expected_project_version"],
    ),
    "ProjectVersionResponse": _envelope("ProjectVersionSummary"),
    "ProjectVersionListData": _object(
        {
            "items": {"type": "array", "items": {"$ref": "#/components/schemas/ProjectVersionSummary"}},
            "next_cursor": _string(nullable=True),
            "has_more": {"type": "boolean"},
        },
        ["items", "next_cursor", "has_more"],
    ),
    "ProjectVersionListResponse": _envelope("ProjectVersionListData"),
    "ProjectVersionCompareData": _object(
        {
            "left_version_id": _string(),
            "right_version_id": _string(),
            "changed_domains": {"type": "array", "items": {"type": "string"}},
            "summary": _string(),
            "source_refs": {"type": "array", "items": {"type": "object"}},
        },
        ["left_version_id", "right_version_id", "changed_domains", "summary", "source_refs"],
    ),
    "ProjectVersionCompareResponse": _envelope("ProjectVersionCompareData"),
    "ProjectContext": _object(
        {
            "background": _string(nullable=True),
            "business_goal": _string(nullable=True),
            "target_user": _string(nullable=True),
            "core_modules": {"type": ["array", "null"], "items": {"type": "string"}},
            "key_constraint": _string(nullable=True),
            "decision_summary": _string(nullable=True),
            "history_summary": _string(nullable=True),
            "content_hash": _string(pattern="^[0-9a-f]{64}$"),
            "version": {"type": "integer", "minimum": 1},
        },
        ["content_hash", "version"],
    ),
    "ProjectContextResponse": _envelope("ProjectContext"),
    "UpdateProjectContextRequest": _object(
        {
            "background": _string(nullable=True),
            "business_goal": _string(nullable=True),
            "target_user": _string(nullable=True),
            "core_modules": {"type": ["array", "null"], "items": {"type": "string"}},
            "key_constraint": _string(nullable=True),
            "decision_summary": _string(nullable=True),
            "history_summary": _string(nullable=True),
            "expected_version": {"type": "integer", "minimum": 1},
        },
        ["expected_version"],
    ),
    "ProjectMember": _object(
        {
            "user_id": _string(),
            "roles": {"type": "array", "items": {"$ref": "#/components/schemas/ProjectRole"}, "minItems": 1, "uniqueItems": True},
            "status": {"type": "string", "enum": ["active", "disabled"]},
            "permission_version": {"type": "integer", "minimum": 1},
        },
        ["user_id", "roles", "status", "permission_version"],
    ),
    "ProjectMemberResponse": _envelope("ProjectMember"),
    "ProjectMemberList": _object({"items": {"type": "array", "items": {"$ref": "#/components/schemas/ProjectMember"}}}, ["items"]),
    "ProjectMemberListResponse": _envelope("ProjectMemberList"),
    "PutProjectMemberRequest": _object(
        {
            "roles": {"type": "array", "items": {"$ref": "#/components/schemas/ProjectRole"}, "minItems": 1, "uniqueItems": True},
            "expected_permission_version": {"type": "integer", "minimum": 1},
        },
        ["roles", "expected_permission_version"],
    ),
    "FileRelationInput": _object(
        {
            "object_type": _string(minLength=1, maxLength=64),
            "object_id": _string(),
            "object_version_id": _string(nullable=True),
            "relation_type": _string(minLength=1, maxLength=32),
        },
        ["object_type", "object_id", "relation_type"],
    ),
    "FileUploadInitRequest": _object(
        {
            "project_id": _string(),
            "logical_name": _string(minLength=1, maxLength=255),
            "size_bytes": {"type": "integer", "minimum": 1, "maximum": 52428800},
            "mime_type": _string(minLength=1, maxLength=128),
            "extension": _string(nullable=True, maxLength=32),
            "checksum_sha256": _string(pattern="^[0-9a-f]{64}$"),
            "relation": {"oneOf": [{"$ref": "#/components/schemas/FileRelationInput"}, {"type": "null"}]},
        },
        ["project_id", "logical_name", "size_bytes", "mime_type", "checksum_sha256"],
    ),
    "FileUploadData": _object(
        {
            "upload_id": _string(),
            "stored_file_id": _string(),
            "pending_file_version_id": _string(),
            "upload_url": _string(format="uri", writeOnly=True),
            "http_method": {"type": "string", "const": "PUT"},
            "required_headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "expires_at": _string(format="date-time"),
            "max_size_bytes": {"type": "integer"},
        },
        ["upload_id", "stored_file_id", "pending_file_version_id", "upload_url", "http_method", "required_headers", "expires_at", "max_size_bytes"],
    ),
    "FileUploadResponse": _envelope("FileUploadData"),
    "CompleteFileUploadRequest": _object(
        {
            "etag": _string(nullable=True),
            "checksum_sha256": _string(pattern="^[0-9a-f]{64}$"),
            "expected_file_version": {"type": ["integer", "null"], "minimum": 1},
        },
        ["checksum_sha256"],
    ),
    "AbortFileUploadRequest": _object({"reason": _string(minLength=1, maxLength=1000)}, ["reason"]),
    "AbortFileUploadData": _object(
        {"aborted": {"type": "boolean", "const": True}}, ["aborted"]
    ),
    "AbortFileUploadResponse": _envelope("AbortFileUploadData"),
    "StoredFile": _object(
        {
            "id": _string(),
            "project_id": _string(nullable=True),
            "logical_name": _string(),
            "status": {"type": "string", "enum": ["pending", "active", "archived", "failed"]},
            "current_version_id": {
                **_string(nullable=True),
                "description": "Set only after upload completion commits an available immutable version.",
            },
            "version": {"type": "integer", "minimum": 1},
        },
        ["id", "logical_name", "status", "current_version_id", "version"],
    ),
    "FileVersion": _object(
        {
            "id": _string(),
            "stored_file_id": _string(),
            "version_no": _string(),
            "mime_type": _string(),
            "extension": _string(nullable=True),
            "size_bytes": {"type": "integer", "minimum": 0},
            "checksum_sha256": _string(pattern="^[0-9a-f]{64}$"),
            "storage_status": {
                "type": "string",
                "enum": ["pending", "available", "failed", "aborted"],
                "description": "Pending versions are internal upload placeholders and are not downloadable, relatable, current, or list-visible.",
            },
            "created_at": _string(format="date-time"),
        },
        ["id", "stored_file_id", "version_no", "mime_type", "size_bytes", "checksum_sha256", "storage_status", "created_at"],
    ),
    "FileData": _object(
        {
            "file": {"$ref": "#/components/schemas/StoredFile"},
            "current_version": {"oneOf": [{"$ref": "#/components/schemas/FileVersion"}, {"type": "null"}]},
            "relations": {"type": "array", "items": {"$ref": "#/components/schemas/FileRelationInput"}},
        },
        ["file", "current_version", "relations"],
    ),
    "FileResponse": _envelope("FileData"),
    "ProjectFileList": _object(
        {"items": {"type": "array", "items": {"$ref": "#/components/schemas/FileData"}}},
        ["items"],
    ),
    "ProjectFileListResponse": _envelope("ProjectFileList"),
    "FileVersionList": {
        **_object(
        {
            "items": {"type": "array", "items": {"$ref": "#/components/schemas/FileVersion"}},
            "next_cursor": _string(nullable=True),
            "has_more": {"type": "boolean"},
        },
        ["items", "next_cursor", "has_more"],
        ),
        "description": "Contains available immutable versions only; pending/failed/aborted placeholders are excluded.",
    },
    "FileVersionListResponse": _envelope("FileVersionList"),
    "FileRelationResponse": _envelope("FileRelationInput"),
    "DownloadFileVersionRequest": _object(
        {"disposition": {"type": "string", "enum": ["inline", "download"]}}, ["disposition"]
    ),
    "DownloadFileVersionData": _object(
        {
            "download_url": _string(format="uri", writeOnly=True),
            "expires_at": _string(format="date-time"),
            "file_name": _string(),
            "mime_type": _string(),
            "size_bytes": {"type": "integer", "minimum": 0},
        },
        ["download_url", "expires_at", "file_name", "mime_type", "size_bytes"],
    ),
    "DownloadFileVersionResponse": _envelope("DownloadFileVersionData"),
    "InternalHealthData": _object(
        {
            "status": {"type": "string", "enum": ["ready", "degraded"]},
            "service": {"type": "string"},
            "release": {"type": "string"},
        },
        ["status", "service", "release"],
    ),
    "InternalHealthResponse": _envelope("InternalHealthData"),
}


SPRINT1_PATHS: dict[str, dict[str, Any]] = {
    "/api/v1/auth/register": {"post": _operation("register", "identity", "AuthTokenResponse", request_schema="AuthRegisterRequest", security=[])},
    "/api/v1/auth/login": {"post": _operation("login", "identity", "AuthTokenResponse", request_schema="AuthLoginRequest", security=[])},
    "/api/v1/auth/refresh": {"post": _operation("refreshAccessToken", "identity", "RefreshTokenResponse", security=[{"refreshCookie": []}], description="Rotates the seven-day refresh token. Reuse revokes the complete token family.")},
    "/api/v1/auth/logout": {"post": _operation("logout", "identity", "LogoutResponse", security=[{"bearerAuth": []}, {"refreshCookie": []}])},
    "/api/v1/session": {"get": _operation("getSession", "identity", "SessionResponse")},
    "/api/v1/projects": {
        "get": _operation("listProjects", "projects", "ProjectListResponse", parameters=[{"$ref": "#/components/parameters/Cursor"}, {"$ref": "#/components/parameters/Limit"}, _parameter("status", location="query", required=False), _parameter("query", location="query", required=False)]),
        "post": _operation("createProject", "projects", "CreateProjectResponse", request_schema="CreateProjectRequest", idempotent=True, description="Creates Project, V1, owner membership, audit and Outbox in one transaction."),
    },
    "/api/v1/projects/{project_id}": {
        "get": _operation("getProject", "projects", "ProjectResponse", parameters=[PROJECT_ID]),
        "patch": _operation("updateProject", "projects", "ProjectResponse", request_schema="UpdateProjectRequest", parameters=[PROJECT_ID]),
    },
    "/api/v1/projects/{project_id}:archive": {"post": _operation("archiveProject", "projects", "ProjectResponse", request_schema="ProjectCommandRequest", parameters=[PROJECT_ID], idempotent=True)},
    "/api/v1/projects/{project_id}:restore": {"post": _operation("restoreProject", "projects", "ProjectResponse", request_schema="ProjectCommandRequest", parameters=[PROJECT_ID], idempotent=True)},
    "/api/v1/projects/{project_id}/members": {"get": _operation("listProjectMembers", "permissions", "ProjectMemberListResponse", parameters=[PROJECT_ID])},
    "/api/v1/projects/{project_id}/members/{user_id}": {"put": _operation("putProjectMember", "permissions", "ProjectMemberResponse", request_schema="PutProjectMemberRequest", parameters=[PROJECT_ID, USER_ID], idempotent=True)},
    "/api/v1/projects/{project_id}/versions": {"get": _operation("listProjectVersions", "versions", "ProjectVersionListResponse", parameters=[PROJECT_ID, {"$ref": "#/components/parameters/Cursor"}, _parameter("lineage_from", location="query", required=False)])},
    "/api/v1/project-versions/{version_id}": {"get": _operation("getProjectVersion", "versions", "ProjectVersionResponse", parameters=[VERSION_ID])},
    "/api/v1/project-versions/{left_id}:compare": {"get": _operation("compareProjectVersions", "versions", "ProjectVersionCompareResponse", parameters=[_parameter("left_id"), _parameter("right_version_id", location="query")], description="Read-only comparison; never changes view context or the working version.")},
    "/api/v1/projects/{project_id}/versions/{version_id}:set-working": {"post": _operation("setWorkingProjectVersion", "versions", "WorkingVersionChangeResponse", request_schema="SetWorkingVersionRequest", parameters=[PROJECT_ID, VERSION_ID], idempotent=True, description="Does not change the user's view context or derive a version.")},
    "/api/v1/projects/{project_id}/versions:derive": {"post": _operation("deriveProjectVersion", "versions", "ProjectVersionResponse", request_schema="DeriveProjectVersionRequest", parameters=[PROJECT_ID], idempotent=True, description="Creates a new immutable version; it does not silently make it working.")},
    "/api/v1/projects/{project_id}/context": {
        "get": _operation("getProjectContext", "projects", "ProjectContextResponse", parameters=[PROJECT_ID]),
        "patch": _operation("updateProjectContext", "projects", "ProjectContextResponse", request_schema="UpdateProjectContextRequest", parameters=[PROJECT_ID]),
    },
    "/api/v1/files/uploads": {"post": _operation("initFileUpload", "files", "FileUploadResponse", request_schema="FileUploadInitRequest", idempotent=True)},
    "/api/v1/files/uploads/{upload_id}:complete": {"post": _operation("completeFileUpload", "files", "FileResponse", request_schema="CompleteFileUploadRequest", parameters=[UPLOAD_ID], idempotent=True)},
    "/api/v1/files/uploads/{upload_id}:abort": {"post": _operation("abortFileUpload", "files", "AbortFileUploadResponse", request_schema="AbortFileUploadRequest", parameters=[UPLOAD_ID], idempotent=True)},
    "/api/v1/files/{file_id}": {"get": _operation("getFile", "files", "FileResponse", parameters=[FILE_ID])},
    "/api/v1/projects/{project_id}/files": {"get": _operation("listProjectFiles", "files", "ProjectFileListResponse", parameters=[PROJECT_ID], description="Lists only completed, available project files so the Public UI can recover after reload.")},
    "/api/v1/files/{file_id}/versions": {"get": _operation("listFileVersions", "files", "FileVersionListResponse", parameters=[FILE_ID, {"$ref": "#/components/parameters/Cursor"}])},
    "/api/v1/file-versions/{version_id}:download": {"post": _operation("createFileVersionDownload", "files", "DownloadFileVersionResponse", request_schema="DownloadFileVersionRequest", parameters=[VERSION_ID])},
    "/api/v1/file-versions/{version_id}/relations": {"post": _operation("createFileRelation", "files", "FileRelationResponse", request_schema="FileRelationInput", parameters=[VERSION_ID], idempotent=True)},
    "/api/v1/files/{file_id}:archive": {"post": _operation("archiveFile", "files", "FileResponse", request_schema="ProjectCommandRequest", parameters=[FILE_ID], idempotent=True)},
    "/internal/v1/health": {"get": _operation("getInternalHealth", "internal", "InternalHealthResponse", security=[{"serviceBearerAuth": []}], description="Requires issuer/sub ai-api (or monitoring issuer), audience business-api and scope health.")},
}


def _set_refresh_cookie_contract(
    operation: dict[str, Any],
    *,
    action: str,
    origin_check: bool = False,
) -> None:
    operation["responses"]["200"].setdefault("headers", {})["Set-Cookie"] = {
        "description": (
            "Sets the rotated Secure, HttpOnly, SameSite refresh cookie."
            if action in {"set", "rotate"}
            else "Clears the refresh cookie with an expired Max-Age."
        ),
        "schema": {"type": "string"},
    }
    operation["x-refresh-cookie"] = {
        "action": action,
        "httpOnly": True,
        "secure-in-production": True,
        "sameSite": "Strict-or-Lax-by-deployment",
        "maxAgeSeconds": 604800 if action in {"set", "rotate"} else 0,
    }
    if origin_check:
        operation.setdefault("parameters", []).extend(
            [
                {"$ref": "#/components/parameters/Origin"},
                {"$ref": "#/components/parameters/Referer"},
                {"$ref": "#/components/parameters/CsrfToken"},
            ]
        )
        operation["x-cookie-command-origin-policy"] = {
            "requireOneOf": ["Origin", "Referer"],
            "sameOrigin": True,
            "csrfToken": "required-when-deployment-enables-double-submit",
            "failureCodes": ["ORIGIN_REQUIRED", "ORIGIN_MISMATCH", "CSRF_INVALID"],
        }


_set_refresh_cookie_contract(SPRINT1_PATHS["/api/v1/auth/register"]["post"], action="set")
_set_refresh_cookie_contract(SPRINT1_PATHS["/api/v1/auth/login"]["post"], action="set")
_set_refresh_cookie_contract(
    SPRINT1_PATHS["/api/v1/auth/refresh"]["post"], action="rotate", origin_check=True
)
_set_refresh_cookie_contract(
    SPRINT1_PATHS["/api/v1/auth/logout"]["post"], action="clear", origin_check=True
)

SPRINT1_PATHS["/api/v1/files/uploads"]["post"]["x-pending-file-version"] = {
    "visibility": "internal-only",
    "forbiddenBeforeComplete": ["list", "download", "relate", "set-current"],
}
SPRINT1_PATHS["/api/v1/files/uploads/{upload_id}:complete"]["post"].update(
    {
        "description": (
            "One-time pending-to-available finalization. Validates actor, expiry, object state, "
            "size, MIME and checksum. Only the successful metadata transaction may set current_version_id, "
            "create a relation, audit, Outbox and idempotency result."
        ),
        "x-file-version-finalization": {
            "from": "pending",
            "to": "available",
            "once": True,
            "immutableAfter": True,
            "uploadChecksumHeader": "x-amz-checksum-sha256",
            "finalObjectStrategy": "server-conditional-copy",
            "persistedImmutableIdentifier": "storage_version_id",
        },
    }
)
SPRINT1_PATHS["/api/v1/files/uploads/{upload_id}:abort"]["post"][
    "x-pending-file-version"
] = {
    "terminalStates": ["aborted", "failed"],
    "auditable": True,
    "orphanCleanupCandidate": True,
    "businessSuccess": False,
}


def install_sprint1_contract(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["refreshCookie"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": "refresh_token",
        "description": "Secure, HttpOnly, SameSite refresh cookie; default lifetime seven days.",
    }
    components["securitySchemes"]["serviceBearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Internal HS256 service JWT; fixed issuer/audience/scope and short lifetime.",
        "x-required-issuers": ["ai-api", "monitoring"],
        "x-ai-caller-subject": "ai-api",
        "x-required-audience": "business-api",
        "x-required-scope": "health",
    }
    components.setdefault("parameters", {})["Limit"] = {
        "name": "limit",
        "in": "query",
        "required": False,
        "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
    }
    components["parameters"].update(
        {
            "Origin": {
                "name": "Origin",
                "in": "header",
                "required": False,
                "schema": {"type": "string", "format": "uri"},
            },
            "Referer": {
                "name": "Referer",
                "in": "header",
                "required": False,
                "schema": {"type": "string", "format": "uri"},
            },
            "CsrfToken": {
                "name": "X-CSRF-Token",
                "in": "header",
                "required": False,
                "schema": {"type": "string", "minLength": 16, "maxLength": 256},
                "description": "Required only when the deployment enables double-submit CSRF protection.",
            },
        }
    )
    components.setdefault("schemas", {}).update(deepcopy(SPRINT1_SCHEMAS))
    for path, path_item in SPRINT1_PATHS.items():
        if path in schema.setdefault("paths", {}):
            raise RuntimeError(f"Sprint 1 contract path already exists: {path}")
        schema["paths"][path] = deepcopy(path_item)
    schema["x-contract-module"] = "sprint-1-identity-project-version-file"
    schema["x-critical-command-transaction"] = {
        "always": [
            "business_fact",
            "operation_audit_log",
            "completed_idempotency_record",
        ],
        "when_canonical_business_event_frozen": ["business_event_outbox"],
        "rollback_on": ["audit_failure", "required_outbox_failure"],
    }

    canonical_command_events = {
        ("/api/v1/projects", "post"): "project.project.created",
        ("/api/v1/projects/{project_id}:archive", "post"): "project.project.archived",
        ("/api/v1/projects/{project_id}:restore", "post"): "project.project.restored",
        (
            "/api/v1/projects/{project_id}/versions/{version_id}:set-working",
            "post",
        ): "project.version.working_set",
        ("/api/v1/projects/{project_id}/versions:derive", "post"): "project.version.derived",
        ("/api/v1/files/uploads", "post"): "file.upload.started",
        ("/api/v1/files/uploads/{upload_id}:complete", "post"): "file.upload.completed",
    }
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or "x-idempotency-scope" not in operation:
                continue
            event_name = canonical_command_events.get((path, method))
            if event_name is not None:
                operation["x-canonical-event-transaction"] = {
                    "required": True,
                    "only_when_frozen_canonical_event_exists": True,
                    "event_name": event_name,
                }
