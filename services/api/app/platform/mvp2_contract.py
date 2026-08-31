from __future__ import annotations

from typing import Any


MVP2_CONTRACT_VERSION = "mvp2.prd-review.rc02.v1"
MVP2_FREEZE_ID = "RC-02-FREEZE-11-20260821-MVP2-PRD-REVIEW-V1"
MVP2_PRD_STATES = ["draft", "in_review", "changes_requested", "confirmed"]
MVP2_REVIEW_STATES = ["open", "changes_requested", "passed"]
MVP2_REVIEW_DECISIONS = ["changes_requested", "pass"]
MVP2_ERROR_MAPPING = {
    "INVALID_STATE": 409,
    "VERSION_CONFLICT": 409,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "IDEMPOTENCY_CONFLICT": 409,
}


def _id_schema(*, nullable: bool = False) -> dict[str, Any]:
    return {"type": ["string", "null"] if nullable else "string", "minLength": 1}


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _response(schema_name: str, description: str = "Success") -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": f"#/components/schemas/{schema_name}"}
            }
        },
    }


def _responses(success_schema: str, success_status: str = "200") -> dict[str, Any]:
    responses = {success_status: _response(success_schema)}
    responses["401"] = {"$ref": "#/components/responses/StandardError"}
    for status in ("403", "404", "409", "422"):
        responses[status] = {"$ref": f"#/components/responses/Mvp2Error{status}"}
    return responses


def _path_parameter(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": _id_schema(),
    }


def _operation(
    *,
    operation_id: str,
    summary: str,
    response_schema: str,
    parameters: list[dict[str, Any]],
    request_schema: str | None = None,
    success_status: str = "200",
    write: bool = False,
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "summary": summary,
        "tags": ["MVP2 PRD Review"],
        "security": [{"bearerAuth": []}],
        "parameters": parameters,
        "responses": _responses(response_schema, success_status),
        "x-contract-version": MVP2_CONTRACT_VERSION,
        "x-freeze-id": MVP2_FREEZE_ID,
        "x-permission": {
            "allowed_project_roles": (
                ["owner"] if write else ["owner", "reviewer", "implementer", "tester"]
            ),
            "admin_bypass": False,
        },
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
    return operation


def _schemas() -> dict[str, Any]:
    string = {"type": "string", "minLength": 1}
    string_array = {"type": "array", "items": string, "uniqueItems": True}
    content_properties = {
        "schema_version": {"type": "string", "const": "prd.mvp2.v1"},
        "background": string,
        "goal": string,
        "primary_user": string,
        "in_scope": {**string_array, "minItems": 1},
        "out_of_scope": {**string_array, "minItems": 1},
        "core_workflow": {**string_array, "minItems": 1},
        "key_rules": {**string_array, "minItems": 1},
        "exceptions_and_boundaries": string_array,
        "acceptance_criteria": {**string_array, "minItems": 1},
    }
    prd = _object(
        {
            "id": _id_schema(),
            "project_version_id": _id_schema(),
            "source_requirement_version_id": _id_schema(),
            "name": string,
            "status": {"type": "string", "enum": MVP2_PRD_STATES},
            "current_version_id": _id_schema(nullable=True),
            "row_version": {"type": "integer", "minimum": 1},
        },
        [
            "id",
            "project_version_id",
            "source_requirement_version_id",
            "name",
            "status",
            "current_version_id",
            "row_version",
        ],
    )
    version = _object(
        {
            "id": _id_schema(),
            "prd_id": _id_schema(),
            "source_version_id": _id_schema(nullable=True),
            "version_no": string,
            "content_json": {"$ref": "#/components/schemas/Mvp2PrdContent"},
            "content_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "is_effective": {"type": "boolean"},
        },
        [
            "id",
            "prd_id",
            "source_version_id",
            "version_no",
            "content_json",
            "content_hash",
            "is_effective",
        ],
    )
    review = _object(
        {
            "id": _id_schema(),
            "project_version_id": _id_schema(),
            "round_no": {"type": "integer", "minimum": 1},
            "status": {"type": "string", "enum": MVP2_REVIEW_STATES},
            "summary": {"type": ["string", "null"]},
            "row_version": {"type": "integer", "minimum": 1},
            "scope": _object(
                {
                    "prd_id": _id_schema(),
                    "prd_version_id": _id_schema(),
                    "content_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                },
                ["prd_id", "prd_version_id", "content_hash"],
            ),
        },
        ["id", "project_version_id", "round_no", "status", "summary", "row_version", "scope"],
    )
    def success_response(data_schema: str) -> dict[str, Any]:
        return _object(
            {
                "code": {"type": "string", "const": "OK"},
                "message": {"type": "string"},
                "data": {"$ref": f"#/components/schemas/{data_schema}"},
                "trace_id": {"type": "string"},
            },
            ["code", "message", "data", "trace_id"],
        )

    return {
        "Mvp2PrdStatus": {"type": "string", "enum": MVP2_PRD_STATES},
        "Mvp2DesignReviewStatus": {"type": "string", "enum": MVP2_REVIEW_STATES},
        "Mvp2ReviewDecision": {"type": "string", "enum": MVP2_REVIEW_DECISIONS},
        "Mvp2ErrorCode": {"type": "string", "enum": list(MVP2_ERROR_MAPPING)},
        "Mvp2ErrorResponse": _object(
            {
                "code": {"$ref": "#/components/schemas/Mvp2ErrorCode"},
                "message": string,
                "details": {"type": "array", "items": {"$ref": "#/components/schemas/FieldError"}},
                "trace_id": string,
            },
            ["code", "message", "details", "trace_id"],
        ),
        "Mvp2PrdContent": _object(content_properties, list(content_properties)),
        "Mvp2Prd": prd,
        "Mvp2PrdVersion": version,
        "Mvp2DesignReview": review,
        "Mvp2PrdData": _object(
            {"prd": prd, "design_review": {"oneOf": [review, {"type": "null"}]}},
            ["prd", "design_review"],
        ),
        "Mvp2PrdVersionData": _object({"prd_version": version}, ["prd_version"]),
        "Mvp2DesignReviewData": _object({"design_review": review}, ["design_review"]),
        "Mvp2CreatePrdRequest": _object(
            {"source_requirement_version_id": _id_schema(), "name": string},
            ["source_requirement_version_id", "name"],
        ),
        "Mvp2CreatePrdVersionRequest": _object(
            {
                "expected_version": {"type": "integer", "minimum": 1},
                "content_json": {"$ref": "#/components/schemas/Mvp2PrdContent"},
                "change_note": string,
            },
            ["expected_version", "content_json", "change_note"],
        ),
        "Mvp2SubmitDesignReviewRequest": _object(
            {
                "prd_id": _id_schema(),
                "prd_version_id": _id_schema(),
                "content_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_version": {"type": "integer", "minimum": 1},
            },
            ["prd_id", "prd_version_id", "content_hash", "expected_version"],
        ),
        "Mvp2DecideDesignReviewRequest": {
            "oneOf": [
                _object(
                    {
                        "expected_version": {"type": "integer", "minimum": 1},
                        "decision": {"type": "string", "const": "changes_requested"},
                        "summary": string,
                    },
                    ["expected_version", "decision", "summary"],
                ),
                _object(
                    {
                        "expected_version": {"type": "integer", "minimum": 1},
                        "decision": {"type": "string", "const": "pass"},
                    },
                    ["expected_version", "decision"],
                ),
            ]
        },
        "Mvp2PrdListData": _object(
            {"items": {"type": "array", "items": prd}, "has_more": {"const": False}},
            ["items", "has_more"],
        ),
        "Mvp2PrdResponse": success_response("Mvp2PrdData"),
        "Mvp2PrdVersionResponse": success_response("Mvp2PrdVersionData"),
        "Mvp2DesignReviewResponse": success_response("Mvp2DesignReviewData"),
        "Mvp2PrdListResponse": success_response("Mvp2PrdListData"),
    }


def install_mvp2_contract(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    components.setdefault("schemas", {}).update(_schemas())
    for status in (403, 404, 409, 422):
        codes = [code for code, mapped in MVP2_ERROR_MAPPING.items() if mapped == status]
        components.setdefault("responses", {})[f"Mvp2Error{status}"] = {
            "description": "MVP2 frozen error response",
            "content": {
                "application/json": {
                    "schema": {
                        "allOf": [
                            {"$ref": "#/components/schemas/Mvp2ErrorResponse"},
                            {"properties": {"code": {"type": "string", "enum": codes}}},
                        ]
                    }
                }
            },
        }

    idempotency = {"$ref": "#/components/parameters/IdempotencyKey"}
    version_id = _path_parameter("version_id")
    prd_id = _path_parameter("prd_id")
    review_id = _path_parameter("review_id")
    paths = schema.setdefault("paths", {})
    paths["/api/v1/project-versions/{version_id}/prds"] = {
        "get": _operation(
            operation_id="listProjectVersionPrds",
            summary="Get the main PRD for a project version",
            response_schema="Mvp2PrdListResponse",
            parameters=[version_id],
        ),
        "post": _operation(
            operation_id="createProjectVersionPrd",
            summary="Create a PRD identity from a confirmed Requirement Version",
            response_schema="Mvp2PrdResponse",
            request_schema="Mvp2CreatePrdRequest",
            parameters=[version_id, idempotency],
            success_status="201",
            write=True,
        ),
    }
    paths["/api/v1/prds/{prd_id}"] = {
        "get": _operation(
            operation_id="getPrd",
            summary="Get a PRD aggregate",
            response_schema="Mvp2PrdResponse",
            parameters=[prd_id],
        )
    }
    paths["/api/v1/prd-versions/{version_id}"] = {
        "get": _operation(
            operation_id="getPrdVersion",
            summary="Get an immutable PRD Version",
            response_schema="Mvp2PrdVersionResponse",
            parameters=[version_id],
        )
    }
    paths["/api/v1/prds/{prd_id}/versions"] = {
        "post": _operation(
            operation_id="createPrdVersion",
            summary="Explicitly save a new immutable PRD Version",
            response_schema="Mvp2PrdVersionResponse",
            request_schema="Mvp2CreatePrdVersionRequest",
            parameters=[prd_id, idempotency],
            success_status="201",
            write=True,
        )
    }
    paths["/api/v1/project-versions/{version_id}/design-reviews"] = {
        "post": _operation(
            operation_id="submitPrdDesignReview",
            summary="Submit an exact PRD Version for a new review round",
            response_schema="Mvp2DesignReviewResponse",
            request_schema="Mvp2SubmitDesignReviewRequest",
            parameters=[version_id, idempotency],
            success_status="201",
            write=True,
        )
    }
    paths["/api/v1/design-reviews/{review_id}"] = {
        "get": _operation(
            operation_id="getDesignReview",
            summary="Get a minimal Design Review",
            response_schema="Mvp2DesignReviewResponse",
            parameters=[review_id],
        )
    }
    paths["/api/v1/design-reviews/{review_id}:decide"] = {
        "post": _operation(
            operation_id="decideDesignReview",
            summary="Decide changes requested or pass and atomically confirm",
            response_schema="Mvp2DesignReviewResponse",
            request_schema="Mvp2DecideDesignReviewRequest",
            parameters=[review_id, idempotency],
            write=True,
        )
    }
    schema["x-mvp2-prd-review"] = {
        "contract_version": MVP2_CONTRACT_VERSION,
        "freeze_id": MVP2_FREEZE_ID,
        "mode": "R3_ADDITIVE_ONLY",
        "schema_version": "prd.mvp2.v1",
        "error_http_mapping": MVP2_ERROR_MAPPING,
        "ai_boundary": "OUT",
    }
