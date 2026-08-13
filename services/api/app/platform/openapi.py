from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.platform.sprint1_contract import install_sprint1_contract
from app.platform.sprint2_contract import install_sprint2_contract


ERROR_CODES = [
    "VALIDATION_ERROR",
    "AUTH_REQUIRED",
    "UNAUTHORIZED",
    "FORBIDDEN",
    "PERMISSION_CHANGED",
    "RESOURCE_NOT_FOUND",
    "NOT_FOUND",
    "EMAIL_EXISTS",
    "WEAK_PASSWORD",
    "INVALID_CREDENTIALS",
    "RATE_LIMITED",
    "REFRESH_INVALID",
    "TOKEN_REUSE_DETECTED",
    "ORIGIN_REQUIRED",
    "ORIGIN_MISMATCH",
    "CSRF_INVALID",
    "SERVICE_TOKEN_INVALID",
    "VERSION_CONFLICT",
    "HISTORICAL_READ_ONLY",
    "FEATURE_DISABLED",
    "IDEMPOTENCY_KEY_REQUIRED",
    "IDEMPOTENCY_CONFLICT",
    "UPLOAD_INCOMPLETE",
    "CHECKSUM_MISMATCH",
    "FILE_TOO_LARGE",
    "FILE_TYPE_NOT_ALLOWED",
    "STORAGE_UNAVAILABLE",
    "DEPENDENCY_UNAVAILABLE",
    "HTTP_ERROR",
    "INTERNAL_ERROR",
]


def configure_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
            openapi_version="3.1.0",
        )
        schema["info"]["x-contract-status"] = "candidate"
        schema["info"]["x-contract-reviewers"] = ["frontend", "ai-data", "review"]
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        components.setdefault("parameters", {}).update(
            {
                "IdempotencyKey": {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "minLength": 8, "maxLength": 128},
                },
                "Cursor": {
                    "name": "cursor",
                    "in": "query",
                    "required": False,
                    "schema": {"type": ["string", "null"]},
                },
                "PageSize": {
                    "name": "page_size",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                },
            }
        )
        components.setdefault("schemas", {})["ErrorCode"] = {
            "type": "string",
            "enum": ERROR_CODES,
        }
        components["schemas"].update(
            {
                "FieldError": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["reason"],
                    "properties": {
                        "field": {"type": ["string", "null"]},
                        "reason": {"type": "string"},
                    },
                },
                "ErrorResponse": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["code", "message", "details", "trace_id"],
                    "properties": {
                        "code": {"$ref": "#/components/schemas/ErrorCode"},
                        "message": {"type": "string"},
                        "details": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/FieldError"},
                        },
                        "trace_id": {"type": "string"},
                    },
                },
                "VersionedCommand": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["expected_version"],
                    "properties": {
                        "expected_version": {"type": "integer", "minimum": 1}
                    },
                },
                "CursorPage": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["items", "has_more"],
                    "properties": {
                        "items": {"type": "array", "items": {}},
                        "next_cursor": {"type": ["string", "null"]},
                        "has_more": {"type": "boolean"},
                    },
                },
            }
        )
        components.setdefault("responses", {})["StandardError"] = {
            "description": "Standard error envelope",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            },
        }
        install_sprint1_contract(schema)
        install_sprint2_contract(schema)
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict) or "responses" not in operation:
                    continue
                # R4 operations carry their split HTTP error responses in
                # install_sprint2_contract. Preserve the Sprint 1 response
                # surface byte-for-byte (including its 422 response).
                if operation.get("x-contract-phase") == "sprint-2-p1-runtime-r4-candidate":
                    continue
                for status_code in ("400", "401", "403", "404", "409", "422", "500"):
                    operation["responses"].setdefault(
                        status_code, {"$ref": "#/components/responses/StandardError"}
                    )
        schema["x-api-prefix"] = "/api/v1"
        schema["x-internal-api-prefix"] = "/internal/v1"
        schema["x-optimistic-lock-field"] = "expected_version"
        schema["x-id-format"] = "string"
        schema["x-datetime-format"] = "UTC RFC3339"
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
