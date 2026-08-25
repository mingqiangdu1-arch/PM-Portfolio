"""Runtime materialization for the frozen MVP5 validation-feedback contract."""

from __future__ import annotations

from typing import Any


MVP5_CONTRACT_VERSION = "MVP5-v1"
MVP5_FREEZE_ID = "MVP5-VALIDATION-FEEDBACK-CONTRACT-FREEZE-20260825-V1"


def _response(data: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "message", "data", "trace_id"],
        "properties": {
            "code": {"const": "OK"},
            "message": {"type": "string"},
            "data": {"$ref": f"#/components/schemas/{data}"},
            "trace_id": {"type": "string"},
        },
    }


def _operation(
    operation_id: str,
    response_schema: str,
    *,
    method: str,
    request_schema: str | None = None,
    idempotent: bool = False,
    created: bool = False,
    parameters: list[dict[str, Any]] | None = None,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    success = "201" if created else "200"
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "tags": ["validation-feedback"],
        "security": [{"bearerAuth": []}],
        "parameters": list(parameters or []),
        "responses": {
            success: {
                "description": "Success",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{response_schema}"}
                    }
                },
            },
            "401": {"$ref": "#/components/responses/StandardError"},
            "403": {"$ref": "#/components/responses/StandardError"},
            "404": {"$ref": "#/components/responses/StandardError"},
            "409": {"$ref": "#/components/responses/StandardError"},
            "422": {"$ref": "#/components/responses/StandardError"},
        },
        "x-contract-phase": "mvp5-validation-feedback-v1",
        "x-permission": {
            "admin_bypass": False,
            "allowed_project_roles": list(roles or []),
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
    if idempotent:
        operation["parameters"].append({"$ref": "#/components/parameters/IdempotencyKey"})
        operation["x-idempotency"] = {
            "required": True,
            "scope": "authenticated-user+endpoint-object-id+key+request-hash",
            "replay": "same key and request replays the original successful response",
        }
    if request_schema and request_schema != "Mvp5IssueCreateRequest" and method in {"post", "patch"}:
        operation["x-expected-version"] = {
            "field": "expected_version",
            "required": True,
            "stale_error": "VERSION_CONFLICT",
        }
    return operation


def install_mvp5_contract(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    errors = schemas.get("ErrorCode", {}).setdefault("enum", [])
    for code in (
        "TEST_RECORD_NOT_SUBMITTED",
        "TEST_RECORD_HAS_ISSUES",
        "VALIDATION_ALREADY_CONCLUDED",
        "ISSUE_VALIDATION_CONFLICT",
        "ISSUE_NOT_OPEN",
    ):
        if code not in errors:
            errors.append(code)

    test_record = schemas.get("Mvp4TestRecord")
    if test_record:
        for field in ("project_id", "project_version_id", "no_issue_conclusion"):
            if field not in test_record.setdefault("required", []):
                test_record["required"].append(field)
        test_record.setdefault("properties", {})["project_id"] = {"type": "string", "pattern": "^[1-9][0-9]*$"}
        test_record["properties"]["project_version_id"] = {"type": "string", "pattern": "^[1-9][0-9]*$"}
        test_record.setdefault("properties", {})["no_issue_conclusion"] = {"type": "boolean"}

    derive = schemas.get("DeriveProjectVersionRequest")
    if derive:
        derive["properties"]["change_type"] = {
            "type": "string",
            "enum": ["bug_fix", "optimization", "scope_change"],
        }
        derive["properties"]["inheritance_choices"] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["requirements", "prd", "implementation_plan"],
            "properties": {
                "requirements": {"type": "boolean"},
                "prd": {"type": "boolean"},
                "implementation_plan": {"type": "boolean"},
            },
        }

    string_id = {"type": "string", "pattern": "^[1-9][0-9]*$"}
    nullable_id = {"type": ["string", "null"], "pattern": "^[1-9][0-9]*$"}
    timestamp = {"type": "string", "format": "date-time"}
    issue_type = {"type": "string", "enum": ["defect", "feedback", "data_anomaly", "optimization"]}
    priority = {"type": "string", "enum": ["low", "medium", "high", "urgent"]}
    severity = {"type": "string", "enum": ["low", "medium", "high", "critical"]}
    issue_status = {
        "type": "string",
        "enum": [
            "open_needs_disposition",
            "routed_current_fix",
            "routed_new_version",
            "deferred",
            "rejected",
        ],
    }
    disposition_type = {
        "type": "string",
        "enum": ["current_version_fix", "derive_new_version", "defer", "reject"],
    }
    request_disposition_type = {
        "type": "string",
        "enum": ["current_version_fix", "defer", "reject"],
    }

    schemas.update(
        {
            "Mvp5BugDetailInput": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reproduce_steps", "expected_result", "actual_result", "environment"],
                "properties": {
                    "reproduce_steps": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "expected_result": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "actual_result": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "environment": {"type": ["object", "null"], "additionalProperties": True},
                },
            },
            "Mvp5OptimizationDetailInput": {
                "type": "object",
                "additionalProperties": False,
                "required": ["problem_evidence", "hypothesis", "expected_outcome", "impact_scope", "need_new_version"],
                "properties": {
                    "problem_evidence": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "hypothesis": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "expected_outcome": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "impact_scope": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "need_new_version": {"type": "boolean"},
                },
            },
            "Mvp5IssueCreateRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["test_record_id", "issue_type", "title", "description", "priority", "severity", "assignee_id", "bug_detail", "optimization_detail"],
                "properties": {
                    "test_record_id": string_id,
                    "issue_type": issue_type,
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "description": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "priority": priority,
                    "severity": severity,
                    "assignee_id": nullable_id,
                    "bug_detail": {"oneOf": [{"$ref": "#/components/schemas/Mvp5BugDetailInput"}, {"type": "null"}]},
                    "optimization_detail": {"oneOf": [{"$ref": "#/components/schemas/Mvp5OptimizationDetailInput"}, {"type": "null"}]},
                },
            },
            "Mvp5IssueUpdateRequest": {
                "allOf": [
                    {"$ref": "#/components/schemas/VersionedCommand"},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["expected_version"],
                        "properties": {
                            "expected_version": {"type": "integer", "minimum": 1},
                            "title": {"type": "string", "minLength": 1, "maxLength": 200},
                            "description": {"type": "string", "minLength": 1, "maxLength": 12000},
                            "priority": priority,
                            "severity": severity,
                            "assignee_id": nullable_id,
                            "bug_detail": {"oneOf": [{"$ref": "#/components/schemas/Mvp5BugDetailInput"}, {"type": "null"}]},
                            "optimization_detail": {"oneOf": [{"$ref": "#/components/schemas/Mvp5OptimizationDetailInput"}, {"type": "null"}]},
                        },
                    },
                ]
            },
            "Mvp5NoIssueConclusionRequest": {"$ref": "#/components/schemas/VersionedCommand"},
            "Mvp5IssueDispositionRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["expected_version", "disposition_type", "reason", "responsible_user_id"],
                "properties": {
                    "expected_version": {"type": "integer", "minimum": 1},
                    "disposition_type": request_disposition_type,
                    "reason": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "responsible_user_id": string_id,
                },
            },
            "Mvp5IssueDisposition": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "sequence_no", "disposition_type", "reason", "target_project_version_id", "responsible_user_id", "decided_by", "decided_at"],
                "properties": {
                    "id": string_id,
                    "sequence_no": {"type": "integer", "minimum": 1},
                    "disposition_type": disposition_type,
                    "reason": {"type": "string"},
                    "target_project_version_id": nullable_id,
                    "responsible_user_id": string_id,
                    "decided_by": string_id,
                    "decided_at": timestamp,
                },
            },
            "Mvp5Issue": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "project_version_id", "test_record_id", "source_type", "issue_type", "title", "description", "priority", "severity", "status", "assignee_id", "row_version", "bug_detail", "optimization_detail", "dispositions", "created_at", "updated_at"],
                "properties": {
                    "id": string_id,
                    "project_version_id": string_id,
                    "test_record_id": nullable_id,
                    "source_type": {"const": "test_record"},
                    "issue_type": issue_type,
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": priority,
                    "severity": severity,
                    "status": issue_status,
                    "assignee_id": nullable_id,
                    "row_version": {"type": "integer", "minimum": 1},
                    "bug_detail": {"oneOf": [{"$ref": "#/components/schemas/Mvp5BugDetailInput"}, {"type": "null"}]},
                    "optimization_detail": {"oneOf": [{"$ref": "#/components/schemas/Mvp5OptimizationDetailInput"}, {"type": "null"}]},
                    "dispositions": {"type": "array", "items": {"$ref": "#/components/schemas/Mvp5IssueDisposition"}},
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            },
            "Mvp5IssueData": {
                "type": "object",
                "additionalProperties": False,
                "required": ["issue"],
                "properties": {"issue": {"$ref": "#/components/schemas/Mvp5Issue"}},
            },
            "Mvp5IssueListData": {
                "type": "object",
                "additionalProperties": False,
                "required": ["items", "next_cursor", "has_more"],
                "properties": {
                    "items": {"type": "array", "items": {"$ref": "#/components/schemas/Mvp5Issue"}},
                    "next_cursor": {"type": ["string", "null"]},
                    "has_more": {"type": "boolean"},
                },
            },
            "Mvp5IssueResponse": _response("Mvp5IssueData"),
            "Mvp5IssueListResponse": _response("Mvp5IssueListData"),
        }
    )

    version_id = {"name": "version_id", "in": "path", "required": True, "schema": string_id}
    issue_id = {"name": "issue_id", "in": "path", "required": True, "schema": string_id}
    test_id = {"name": "id", "in": "path", "required": True, "schema": string_id}
    paths = schema.setdefault("paths", {})
    conclude = _operation(
            "concludeTestRecordNoIssue",
            "Mvp4TestRecordResponse",
            method="post",
            request_schema="Mvp5NoIssueConclusionRequest",
            idempotent=True,
            parameters=[test_id],
            roles=["owner", "tester"],
        )
    conclude["x-mutual-exclusion"] = "no Issue may exist for this Test Record"
    paths["/api/v1/test-records/{id}:conclude-no-issue"] = {"post": conclude}
    cursor = {"name": "cursor", "in": "query", "required": False, "schema": {"type": "string", "pattern": "^[1-9][0-9]*$"}}
    page_size = {"name": "page_size", "in": "query", "required": False, "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}
    create_issue = _operation(
        "createProjectVersionIssue",
        "Mvp5IssueResponse",
        method="post",
        request_schema="Mvp5IssueCreateRequest",
        idempotent=True,
        created=True,
        parameters=[version_id],
        roles=["owner", "tester"],
    )
    create_issue["x-mutual-exclusion"] = "no_issue_conclusion must be false"
    paths["/api/v1/project-versions/{version_id}/issues"] = {
        "get": _operation("listProjectVersionIssues", "Mvp5IssueListResponse", method="get", parameters=[version_id, cursor, page_size], roles=["active_project_member"]),
        "post": create_issue,
    }
    paths["/api/v1/issues/{issue_id}"] = {
        "get": _operation("getIssue", "Mvp5IssueResponse", method="get", parameters=[issue_id], roles=["active_project_member"]),
        "patch": _operation(
            "updateIssue",
            "Mvp5IssueResponse",
            method="patch",
            request_schema="Mvp5IssueUpdateRequest",
            idempotent=True,
            parameters=[issue_id],
            roles=["owner", "tester"],
        ),
    }
    disposition = _operation(
            "createIssueDisposition",
            "Mvp5IssueResponse",
            method="post",
            request_schema="Mvp5IssueDispositionRequest",
            idempotent=True,
            parameters=[issue_id],
            roles=["owner"],
        )
    disposition["x-derived-version-atomic-command"] = True
    paths["/api/v1/issues/{issue_id}/dispositions"] = {"post": disposition}
    schema["x-mvp5"] = {
        "contract_version": MVP5_CONTRACT_VERSION,
        "freeze_id": MVP5_FREEZE_ID,
        "product_goal": "REAL_AI_REQUIREMENT_TO_VALIDATION_FEEDBACK_CLOSURE",
        "paths_added": 4,
        "operations_added": 6,
        "schema_change_required": False,
        "new_migration_required": False,
        "state_machine_change_required": False,
    }
