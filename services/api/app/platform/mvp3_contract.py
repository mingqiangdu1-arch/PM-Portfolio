"""MVP3 implementation-plan/confirmation contract materialization.

This module only installs the frozen OpenAPI surface.  It deliberately does not
register routes or implement persistence/business commands.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


MVP3_CONTRACT_VERSION = "MVP3-v1"
MVP3_FREEZE_ID = "MVP3-SCOPE-CONTRACT-FREEZE-20260823-V1"

ERROR_HTTP_STATUS = {
    "NOT_FOUND": 404,
    "FORBIDDEN": 403,
    "VALIDATION_ERROR": 422,
    "VERSION_CONFLICT": 409,
    "SOURCE_PRD_NOT_CONFIRMED": 409,
    "SOURCE_REVIEW_NOT_PASSED": 409,
    "SOURCE_BINDING_MISMATCH": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "PLAN_VERSION_NOT_CURRENT": 409,
    "PLAN_VERSION_BINDING_MISMATCH": 409,
    "CONFIRMATION_ALREADY_EXISTS": 409,
    "INVALID_STATE": 409,
    "CONFIRMATION_NOT_DRAFT": 409,
    "READINESS_INCOMPLETE": 409,
}

ERROR_CODES = list(ERROR_HTTP_STATUS)


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _id(*, nullable: bool = False) -> dict[str, Any]:
    return {
        "type": ["string", "null"] if nullable else "string",
        "pattern": "^[1-9][0-9]*$",
    }


def _normalized_string(min_length: int, max_length: int) -> dict[str, Any]:
    return {"type": "string", "minLength": min_length, "maxLength": max_length}


def _response(schema_name: str, status: str = "200") -> dict[str, Any]:
    return {
        status: {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                }
            },
        }
    }


def _error_response(status: int, codes: list[str]) -> dict[str, Any]:
    """Build an operation-local error response with its exact code set."""
    return {
        "description": f"MVP3 frozen error response ({status})",
        "content": {
            "application/json": {
                "schema": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Mvp3ErrorResponse"},
                        {"properties": {"code": {"type": "string", "enum": codes}}},
                    ]
                }
            }
        },
        "x-http-status": status,
        "x-error-codes": codes,
    }


def _path_parameter(name: str) -> dict[str, Any]:
    return {"name": name, "in": "path", "required": True, "schema": _id()}


def _operation(
    *,
    operation_id: str,
    method: str,
    path_parameter: str,
    response_schema: str,
    success_status: int,
    errors: list[str],
    permissions: list[str],
    request_schema: str | None = None,
    idempotent: bool = False,
    expected_version: bool = False,
) -> dict[str, Any]:
    parameters = [_path_parameter(path_parameter)]
    if idempotent:
        parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "tags": ["MVP3 Implementation Plan"],
        "security": [{"bearerAuth": []}],
        "parameters": parameters,
        "responses": _response(response_schema, str(success_status)),
        "x-contract-version": MVP3_CONTRACT_VERSION,
        "x-freeze-id": MVP3_FREEZE_ID,
        "x-permissions": {"allowed_project_roles": permissions, "admin_bypass": False},
        "x-permission": {"allowed_project_roles": permissions, "admin_bypass": False},
        "x-idempotency": idempotent,
        "x-expected-version": expected_version,
    }
    if request_schema:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{request_schema}"}
                }
            },
        }
    errors_by_status: dict[int, list[str]] = {}
    for code in errors:
        errors_by_status.setdefault(ERROR_HTTP_STATUS[code], []).append(code)
    for status, codes in errors_by_status.items():
        operation["responses"][str(status)] = _error_response(status, codes)
    return operation


def _plan_item() -> dict[str, Any]:
    return _object(
        {
            "key": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{0,63}$"},
            "description": _normalized_string(1, 4000),
        },
        ["key", "description"],
    )


def _plan_content() -> dict[str, Any]:
    item = _plan_item()
    sections = {
        "features": {"type": "array", "items": item, "minItems": 1, "maxItems": 200},
        "business_rules": {"type": "array", "items": item, "minItems": 0, "maxItems": 200},
        "state_requirements": {"type": "array", "items": item, "minItems": 0, "maxItems": 200},
        "exceptions": {"type": "array", "items": item, "minItems": 0, "maxItems": 200},
        "interactions": {"type": "array", "items": item, "minItems": 0, "maxItems": 200},
        "dependencies": {"type": "array", "items": item, "minItems": 0, "maxItems": 200},
        "acceptance_scope": {"type": "array", "items": item, "minItems": 1, "maxItems": 200},
    }
    schema = _object(
        {"schema_version": {"type": "string", "const": "implementation_plan.mvp3.v1"}, **sections},
        ["schema_version", *sections],
    )
    schema.update(
        {
            "x-normalization": ["CRLF/CR->LF", "NFC", "trim Unicode whitespace", "preserve internal whitespace"],
            "x-canonicalization": "semantic normalization -> RFC8785 JCS; arrays preserved; UTF-8 no BOM",
            "x-max-utf8-bytes": 262144,
            "x-null-policy": "prohibited everywhere",
            "x-duplicate-rules": [
                "key unique across all sections",
                "description unique after normalization within section",
            ],
        }
    )
    return schema


def _readiness() -> dict[str, Any]:
    schema = _object(
        {
            "schema_version": {
                "type": "string",
                "const": "implementation_confirmation.readiness.mvp3.v1",
            },
            "scope_status": {"type": "string", "enum": ["ready", "not_ready"]},
            "implementation_status": {"type": "string", "enum": ["ready", "not_ready"]},
            "configuration_status": {
                "type": "string",
                "enum": ["ready", "not_ready", "not_applicable"],
            },
            "data_change_status": {
                "type": "string",
                "enum": ["ready", "not_ready", "not_applicable"],
            },
            "known_blockers": {
                "type": "array",
                "items": _normalized_string(1, 500),
                "minItems": 0,
                "maxItems": 50,
                "uniqueItems": True,
            },
        },
        [
            "schema_version",
            "scope_status",
            "implementation_status",
            "configuration_status",
            "data_change_status",
            "known_blockers",
        ],
    )
    schema.update(
        {
            "x-normalization": ["CRLF/CR->LF", "NFC", "trim Unicode whitespace"],
            "x-null-policy": "prohibited everywhere",
            "x-complete-predicate": "scope=ready AND implementation=ready AND configuration IN ready/not_applicable AND data_change IN ready/not_applicable AND known_blockers empty",
            "x-semantics": "human readiness attestation only; not Test Passed/Release Ready/Deployment Ready/Production Ready",
        }
    )
    return schema


def _implementation_summary() -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 20,
        "maxLength": 8000,
        "x-length-unit": "Unicode code points",
        "x-normalization": ["CRLF/CR->LF", "NFC", "trim Unicode whitespace"],
        "x-null-policy": "prohibited",
        "x-semantics": "human implementation-scope description only; not test/release/deployment/production evidence",
    }


def _schemas() -> dict[str, Any]:
    plan_version = _object(
        {
            "id": _id(),
            "implementation_plan_id": _id(),
            "source_version_id": _id(nullable=True),
            "version_no": _normalized_string(1, 32),
            "review_id": _id(),
            "content_json": {"$ref": "#/components/schemas/Mvp3PlanContent"},
            "content_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "change_note": _normalized_string(1, 2000),
            "is_effective": {"type": "boolean"},
            "created_by": _id(nullable=True),
            "created_at": {"type": "string", "format": "date-time"},
        },
        [
            "id", "implementation_plan_id", "version_no", "review_id", "content_json",
            "content_hash", "change_note", "is_effective", "created_at",
        ],
    )
    round_schema = _object(
        {
            "id": _id(),
            "implementation_plan_id": _id(),
            "plan_version_id": _id(),
            "source_round_id": _id(nullable=True),
            "round_no": {"type": "integer", "minimum": 1},
            "status": {"type": "string", "enum": ["draft", "confirmed", "superseded"]},
            "confirm_status": {"type": ["string", "null"], "enum": ["confirmed", None]},
            "implementation_summary": {"$ref": "#/components/schemas/Mvp3ImplementationSummary"},
            "readiness_json": {"$ref": "#/components/schemas/Mvp3Readiness"},
            "row_version": {"type": "integer", "minimum": 1},
            "is_effective": {"type": "boolean"},
            "confirmed_by": _id(nullable=True),
            "confirmed_at": {"type": ["string", "null"], "format": "date-time"},
            "superseded_at": {"type": ["string", "null"], "format": "date-time"},
        },
        [
            "id", "implementation_plan_id", "plan_version_id", "round_no", "status",
            "implementation_summary", "readiness_json", "row_version", "is_effective",
        ],
    )
    plan = _object(
        {
            "id": _id(),
            "project_version_id": _id(),
            "source_prd_version_id": _id(),
            "source_design_review_id": _id(),
            "name": _normalized_string(1, 200),
            "status": {"type": "string", "enum": ["draft", "active"]},
            "current_version_id": _id(nullable=True),
            "effective_version_id": _id(nullable=True),
            "row_version": {"type": "integer", "minimum": 1},
            "confirmation_state": {
                "type": "string",
                "enum": ["not_ready", "needs_confirmation", "confirmed", "needs_reconfirmation"],
            },
            "versions": {"type": "array", "items": plan_version},
        },
        [
            "id", "project_version_id", "source_prd_version_id", "source_design_review_id", "name",
            "status", "row_version", "confirmation_state", "versions",
        ],
    )
    plan_without_versions = deepcopy(plan)
    plan_without_versions["properties"].pop("versions")
    plan_without_versions["required"].remove("versions")
    envelope = lambda data: _object(
        {
            "code": {"type": "string", "const": "OK"},
            "message": {"type": "string"},
            "data": {"$ref": f"#/components/schemas/{data}"},
            "trace_id": {"type": "string"},
        },
        ["code", "message", "data", "trace_id"],
    )
    return {
        "Mvp3ErrorCode": {"type": "string", "enum": ERROR_CODES},
        "Mvp3ErrorResponse": _object(
            {
                "code": {"$ref": "#/components/schemas/Mvp3ErrorCode"},
                "message": {"type": "string"},
                "details": {"type": "array", "items": {"$ref": "#/components/schemas/FieldError"}},
                "trace_id": {"type": "string"},
            },
            ["code", "message", "details", "trace_id"],
        ),
        "Mvp3PlanItem": _plan_item(),
        "Mvp3PlanContent": _plan_content(),
        "Mvp3Readiness": _readiness(),
        "Mvp3ImplementationSummary": _implementation_summary(),
        "Mvp3ImplementationPlanVersion": plan_version,
        "Mvp3ConfirmationRound": round_schema,
        "Mvp3ImplementationPlan": plan,
        "Mvp3ImplementationPlanWithoutVersions": plan_without_versions,
        "Mvp3ImplementationPlanListData": _object(
            {"items": {"type": "array", "items": plan_without_versions}}, ["items"]
        ),
        "Mvp3ConfirmationRoundListData": _object(
            {"items": {"type": "array", "items": round_schema}}, ["items"]
        ),
        "Mvp3ImplementationPlanData": _object({"implementation_plan": plan}, ["implementation_plan"]),
        "Mvp3ImplementationPlanVersionData": _object(
            {
                "implementation_plan_version": plan_version,
                "plan_row_version": {"type": "integer", "minimum": 1},
            },
            ["implementation_plan_version", "plan_row_version"],
        ),
        "Mvp3ConfirmationRoundData": _object({"confirmation_round": round_schema}, ["confirmation_round"]),
        "Mvp3ImplementationPlanListResponse": envelope("Mvp3ImplementationPlanListData"),
        "Mvp3ConfirmationRoundListResponse": envelope("Mvp3ConfirmationRoundListData"),
        "Mvp3ImplementationPlanResponse": envelope("Mvp3ImplementationPlanData"),
        "Mvp3ImplementationPlanVersionResponse": envelope("Mvp3ImplementationPlanVersionData"),
        "Mvp3ConfirmationRoundResponse": envelope("Mvp3ConfirmationRoundData"),
        "Mvp3ConfirmConfirmationRoundRequest": _object(
            {"expected_version": {"type": "integer", "minimum": 1}}, ["expected_version"]
        ),
        "Mvp3CreateConfirmationRoundRequest": _object(
            {
                "implementation_summary": {"$ref": "#/components/schemas/Mvp3ImplementationSummary"},
                "plan_version_id": _id(),
                "readiness_json": {"$ref": "#/components/schemas/Mvp3Readiness"},
            },
            ["plan_version_id", "implementation_summary", "readiness_json"],
        ),
        "Mvp3CreateImplementationPlanRequest": _object(
            {
                "source_prd_version_id": _id(),
                "source_design_review_id": _id(),
                "name": _normalized_string(1, 200),
            },
            ["source_prd_version_id", "source_design_review_id", "name"],
        ),
        "Mvp3CreateImplementationPlanVersionRequest": _object(
            {
                "expected_version": {"type": "integer", "minimum": 1},
                "content_json": {"$ref": "#/components/schemas/Mvp3PlanContent"},
                "change_note": _normalized_string(1, 2000),
            },
            ["expected_version", "content_json", "change_note"],
        ),
        "Mvp3SetEffectiveImplementationPlanVersionRequest": _object(
            {"expected_version": {"type": "integer", "minimum": 1}}, ["expected_version"]
        ),
        "Mvp3UpdateConfirmationRoundDraftRequest": _object(
            {
                "expected_version": {"type": "integer", "minimum": 1},
                "plan_version_id": _id(),
                "implementation_summary": {"$ref": "#/components/schemas/Mvp3ImplementationSummary"},
                "readiness_json": {"$ref": "#/components/schemas/Mvp3Readiness"},
            },
            ["expected_version", "plan_version_id", "implementation_summary", "readiness_json"],
        ),
    }


def install_mvp3_contract(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    components.setdefault("schemas", {}).update(_schemas())
    components.setdefault("responses", {})
    for status in sorted(set(ERROR_HTTP_STATUS.values())):
        codes = [code for code, value in ERROR_HTTP_STATUS.items() if value == status]
        components["responses"][f"Mvp3Error{status}"] = {
            "description": f"MVP3 frozen error response ({status})",
            "content": {
                "application/json": {
                    "schema": {
                        "allOf": [
                            {"$ref": "#/components/schemas/Mvp3ErrorResponse"},
                            {"properties": {"code": {"type": "string", "enum": codes}}},
                        ]
                    }
                }
            },
            "x-http-status": status,
            "x-error-codes": codes,
        }
    paths = schema.setdefault("paths", {})
    definitions = [
        ("/api/v1/project-versions/{version_id}/implementation-plans", "get", _operation(
            operation_id="listProjectVersionImplementationPlans", method="GET", path_parameter="version_id",
            response_schema="Mvp3ImplementationPlanListResponse", success_status=200,
            errors=["NOT_FOUND", "FORBIDDEN"], permissions=["owner", "implementer", "other_active_member"],
        )),
        ("/api/v1/project-versions/{version_id}/implementation-plans", "post", _operation(
            operation_id="createProjectVersionImplementationPlan", method="POST", path_parameter="version_id",
            response_schema="Mvp3ImplementationPlanResponse", success_status=201,
            errors=["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "SOURCE_BINDING_MISMATCH", "IDEMPOTENCY_CONFLICT"],
            permissions=["owner"], request_schema="Mvp3CreateImplementationPlanRequest", idempotent=True,
        )),
        ("/api/v1/implementation-plans/{id}", "get", _operation(
            operation_id="getImplementationPlan", method="GET", path_parameter="id",
            response_schema="Mvp3ImplementationPlanResponse", success_status=200,
            errors=["NOT_FOUND", "FORBIDDEN"], permissions=["owner", "implementer", "other_active_member"],
        )),
        ("/api/v1/implementation-plans/{id}/versions", "post", _operation(
            operation_id="createImplementationPlanVersion", method="POST", path_parameter="id",
            response_schema="Mvp3ImplementationPlanVersionResponse", success_status=201,
            errors=["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "SOURCE_BINDING_MISMATCH", "IDEMPOTENCY_CONFLICT"],
            permissions=["owner"], request_schema="Mvp3CreateImplementationPlanVersionRequest", idempotent=True, expected_version=True,
        )),
        ("/api/v1/plan-versions/{id}:set-effective", "post", _operation(
            operation_id="setEffectiveImplementationPlanVersion", method="POST", path_parameter="id",
            response_schema="Mvp3ImplementationPlanResponse", success_status=200,
            errors=["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"],
            permissions=["owner"], request_schema="Mvp3SetEffectiveImplementationPlanVersionRequest", idempotent=True, expected_version=True,
        )),
        ("/api/v1/implementation-plans/{id}/confirmation-rounds", "get", _operation(
            operation_id="listImplementationPlanConfirmationRounds", method="GET", path_parameter="id",
            response_schema="Mvp3ConfirmationRoundListResponse", success_status=200,
            errors=["NOT_FOUND", "FORBIDDEN"], permissions=["owner", "implementer", "other_active_member"],
        )),
        ("/api/v1/implementation-plans/{id}/confirmation-rounds", "post", _operation(
            operation_id="createImplementationPlanConfirmationRound", method="POST", path_parameter="id",
            response_schema="Mvp3ConfirmationRoundResponse", success_status=201,
            errors=["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "CONFIRMATION_ALREADY_EXISTS", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"],
            permissions=["owner", "implementer"], request_schema="Mvp3CreateConfirmationRoundRequest", idempotent=True,
        )),
        ("/api/v1/confirmation-rounds/{id}", "get", _operation(
            operation_id="getConfirmationRound", method="GET", path_parameter="id",
            response_schema="Mvp3ConfirmationRoundResponse", success_status=200,
            errors=["NOT_FOUND", "FORBIDDEN"], permissions=["owner", "implementer", "other_active_member"],
        )),
        ("/api/v1/confirmation-rounds/{id}", "patch", _operation(
            operation_id="updateConfirmationRoundDraft", method="PATCH", path_parameter="id",
            response_schema="Mvp3ConfirmationRoundResponse", success_status=200,
            errors=["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "CONFIRMATION_NOT_DRAFT", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH"],
            permissions=["owner", "implementer"], request_schema="Mvp3UpdateConfirmationRoundDraftRequest", expected_version=True,
        )),
        ("/api/v1/confirmation-rounds/{id}:confirm", "post", _operation(
            operation_id="confirmConfirmationRound", method="POST", path_parameter="id",
            response_schema="Mvp3ConfirmationRoundResponse", success_status=200,
            errors=["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "CONFIRMATION_NOT_DRAFT", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "READINESS_INCOMPLETE", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"],
            permissions=["owner"], request_schema="Mvp3ConfirmConfirmationRoundRequest", idempotent=True, expected_version=True,
        )),
    ]
    for path, method, operation in definitions:
        if path in paths and method in paths[path]:
            raise RuntimeError(f"MVP3 contract path already exists: {path} {method}")
        paths.setdefault(path, {})[method] = operation
    schema["x-mvp3"] = {
        "contract_version": MVP3_CONTRACT_VERSION,
        "freeze_id": MVP3_FREEZE_ID,
        "ai_boundary": "OUT",
        "paths_added": 7,
        "operations_added": 10,
    }
