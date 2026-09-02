from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

from app.platform.mvp3_contract import install_mvp3_contract


OPENAPI_PATH = Path(__file__).parents[3] / "packages" / "contracts" / "openapi" / "openapi.json"
# Accepted MVP2 artifact immediately before MVP3 contract materialization.
# The current HEAD artifact already contains later MVP phases and cannot be
# used as the pre-materialization input for this historical materializer test.
MVP2_AUTHORITY_COMMIT = "1ca41c531475e62af026301684353657c567c6fa"
EXPECTED_OPERATIONS = {
    "listProjectVersionImplementationPlans",
    "createProjectVersionImplementationPlan",
    "getImplementationPlan",
    "createImplementationPlanVersion",
    "setEffectiveImplementationPlanVersion",
    "listImplementationPlanConfirmationRounds",
    "createImplementationPlanConfirmationRound",
    "getConfirmationRound",
    "updateConfirmationRoundDraft",
    "confirmConfirmationRound",
}

FROZEN_OPERATIONS = {
    "listProjectVersionImplementationPlans": {
        "path": "/api/v1/project-versions/{version_id}/implementation-plans", "method": "get", "status": 200,
        "errors": ["NOT_FOUND", "FORBIDDEN"], "idem": False, "expected_version": False, "request": None,
        "permissions": ["owner", "implementer", "other_active_member"],
    },
    "createProjectVersionImplementationPlan": {
        "path": "/api/v1/project-versions/{version_id}/implementation-plans", "method": "post", "status": 201,
        "errors": ["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "SOURCE_BINDING_MISMATCH", "IDEMPOTENCY_CONFLICT"],
        "idem": True, "expected_version": False, "request": "Mvp3CreateImplementationPlanRequest", "permissions": ["owner"],
    },
    "getImplementationPlan": {
        "path": "/api/v1/implementation-plans/{id}", "method": "get", "status": 200,
        "errors": ["NOT_FOUND", "FORBIDDEN"], "idem": False, "expected_version": False, "request": None,
        "permissions": ["owner", "implementer", "other_active_member"],
    },
    "createImplementationPlanVersion": {
        "path": "/api/v1/implementation-plans/{id}/versions", "method": "post", "status": 201,
        "errors": ["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "SOURCE_BINDING_MISMATCH", "IDEMPOTENCY_CONFLICT"],
        "idem": True, "expected_version": True, "request": "Mvp3CreateImplementationPlanVersionRequest", "permissions": ["owner"],
    },
    "setEffectiveImplementationPlanVersion": {
        "path": "/api/v1/plan-versions/{id}:set-effective", "method": "post", "status": 200,
        "errors": ["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"],
        "idem": True, "expected_version": True, "request": "Mvp3SetEffectiveImplementationPlanVersionRequest", "permissions": ["owner"],
    },
    "listImplementationPlanConfirmationRounds": {
        "path": "/api/v1/implementation-plans/{id}/confirmation-rounds", "method": "get", "status": 200,
        "errors": ["NOT_FOUND", "FORBIDDEN"], "idem": False, "expected_version": False, "request": None,
        "permissions": ["owner", "implementer", "other_active_member"],
    },
    "createImplementationPlanConfirmationRound": {
        "path": "/api/v1/implementation-plans/{id}/confirmation-rounds", "method": "post", "status": 201,
        "errors": ["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "CONFIRMATION_ALREADY_EXISTS", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"],
        "idem": True, "expected_version": False, "request": "Mvp3CreateConfirmationRoundRequest", "permissions": ["owner", "implementer"],
    },
    "getConfirmationRound": {
        "path": "/api/v1/confirmation-rounds/{id}", "method": "get", "status": 200,
        "errors": ["NOT_FOUND", "FORBIDDEN"], "idem": False, "expected_version": False, "request": None,
        "permissions": ["owner", "implementer", "other_active_member"],
    },
    "updateConfirmationRoundDraft": {
        "path": "/api/v1/confirmation-rounds/{id}", "method": "patch", "status": 200,
        "errors": ["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "CONFIRMATION_NOT_DRAFT", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH"],
        "idem": False, "expected_version": True, "request": "Mvp3UpdateConfirmationRoundDraftRequest", "permissions": ["owner", "implementer"],
    },
    "confirmConfirmationRound": {
        "path": "/api/v1/confirmation-rounds/{id}:confirm", "method": "post", "status": 200,
        "errors": ["NOT_FOUND", "FORBIDDEN", "VALIDATION_ERROR", "VERSION_CONFLICT", "CONFIRMATION_NOT_DRAFT", "PLAN_VERSION_NOT_CURRENT", "PLAN_VERSION_BINDING_MISMATCH", "SOURCE_PRD_NOT_CONFIRMED", "SOURCE_REVIEW_NOT_PASSED", "READINESS_INCOMPLETE", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"],
        "idem": True, "expected_version": True, "request": "Mvp3ConfirmConfirmationRoundRequest", "permissions": ["owner"],
    },
}


def _materialized() -> tuple[dict, dict]:
    baseline = subprocess.run(
        ["git", "show", f"{MVP2_AUTHORITY_COMMIT}:packages/contracts/openapi/openapi.json"],
        check=True,
        capture_output=True,
    ).stdout
    schema = json.loads(baseline)
    before = copy.deepcopy(schema)
    install_mvp3_contract(schema)
    return before, schema


def _operations(schema: dict) -> dict[str, dict]:
    return {
        operation["operationId"]: operation
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }


def _operation_list(schema: dict) -> list[dict]:
    return [
        operation
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]


def test_mvp3_adds_exactly_seven_paths_and_ten_operations() -> None:
    before, schema = _materialized()
    assert len(before["paths"]) == 50
    assert len(schema["paths"]) == 57
    assert sum(len(path) for path in schema["paths"].values()) == 66
    assert set(_operations(schema)) - set(_operations(before)) == EXPECTED_OPERATIONS


def test_mvp2_paths_are_unchanged_by_materialization() -> None:
    before, schema = _materialized()
    for path, path_item in before["paths"].items():
        assert schema["paths"][path] == path_item


def test_mvp3_operations_consume_frozen_request_and_error_rules() -> None:
    _, schema = _materialized()
    operations = _operations(schema)
    all_ids = [operation["operationId"] for operation in _operation_list(schema)]
    assert len(all_ids) == 66
    assert len(set(all_ids)) == 66
    assert set(FROZEN_OPERATIONS) == EXPECTED_OPERATIONS
    for operation_id, frozen in FROZEN_OPERATIONS.items():
        operation = schema["paths"][frozen["path"]][frozen["method"]]
        assert operation["operationId"] == operation_id
        assert operation["x-permissions"]["allowed_project_roles"] == frozen["permissions"]
        assert operation["x-idempotency"] is frozen["idem"]
        assert operation["x-expected-version"] is frozen["expected_version"]
        assert set(operation["responses"]) == {str(frozen["status"])} | {
            str({"NOT_FOUND": 404, "FORBIDDEN": 403, "VALIDATION_ERROR": 422, "VERSION_CONFLICT": 409, "SOURCE_PRD_NOT_CONFIRMED": 409, "SOURCE_REVIEW_NOT_PASSED": 409, "SOURCE_BINDING_MISMATCH": 409, "IDEMPOTENCY_CONFLICT": 409, "PLAN_VERSION_NOT_CURRENT": 409, "PLAN_VERSION_BINDING_MISMATCH": 409, "CONFIRMATION_ALREADY_EXISTS": 409, "INVALID_STATE": 409, "CONFIRMATION_NOT_DRAFT": 409, "READINESS_INCOMPLETE": 409}[code]) for code in frozen["errors"]}
        for error_code in frozen["errors"]:
            status = {"NOT_FOUND": 404, "FORBIDDEN": 403, "VALIDATION_ERROR": 422, "VERSION_CONFLICT": 409, "SOURCE_PRD_NOT_CONFIRMED": 409, "SOURCE_REVIEW_NOT_PASSED": 409, "SOURCE_BINDING_MISMATCH": 409, "IDEMPOTENCY_CONFLICT": 409, "PLAN_VERSION_NOT_CURRENT": 409, "PLAN_VERSION_BINDING_MISMATCH": 409, "CONFIRMATION_ALREADY_EXISTS": 409, "INVALID_STATE": 409, "CONFIRMATION_NOT_DRAFT": 409, "READINESS_INCOMPLETE": 409}[error_code]
            assert operation["responses"][str(status)]["x-error-codes"] == [code for code in frozen["errors"] if {"NOT_FOUND": 404, "FORBIDDEN": 403, "VALIDATION_ERROR": 422, "VERSION_CONFLICT": 409, "SOURCE_PRD_NOT_CONFIRMED": 409, "SOURCE_REVIEW_NOT_PASSED": 409, "SOURCE_BINDING_MISMATCH": 409, "IDEMPOTENCY_CONFLICT": 409, "PLAN_VERSION_NOT_CURRENT": 409, "PLAN_VERSION_BINDING_MISMATCH": 409, "CONFIRMATION_ALREADY_EXISTS": 409, "INVALID_STATE": 409, "CONFIRMATION_NOT_DRAFT": 409, "READINESS_INCOMPLETE": 409}[code] == status]
        assert ("$ref" in operation["requestBody"]["content"]["application/json"]["schema"] if frozen["request"] else "requestBody" not in operation)
        if frozen["request"]:
            assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(frozen["request"])
            required = schema["components"]["schemas"][frozen["request"]]["required"]
            assert ("expected_version" in required) is frozen["expected_version"]
        has_idem = {"$ref": "#/components/parameters/IdempotencyKey"} in operation["parameters"]
        assert has_idem is frozen["idem"]
    new_operations = [operations[operation_id] for operation_id in EXPECTED_OPERATIONS]
    assert not any(
        parameter.get("in") == "query"
        for operation in new_operations
        for parameter in operation["parameters"]
        if "in" in parameter
    )


def test_mvp3_optional_fields_empty_blockers_and_frozen_metadata() -> None:
    _, schema = _materialized()
    schemas = schema["components"]["schemas"]
    assert set(schemas["Mvp3ImplementationPlan"]["required"]) >= {"id", "row_version"}
    assert not {"current_version_id", "effective_version_id"} & set(schemas["Mvp3ImplementationPlan"]["required"])
    assert not {"source_version_id", "created_by"} & set(schemas["Mvp3ImplementationPlanVersion"]["required"])
    assert not {"source_round_id", "confirm_status", "confirmed_by", "confirmed_at", "superseded_at"} & set(schemas["Mvp3ConfirmationRound"]["required"])
    assert schemas["Mvp3Readiness"]["properties"]["known_blockers"]["minItems"] == 0
    assert schemas["Mvp3PlanContent"]["x-max-utf8-bytes"] == 262144
    assert schemas["Mvp3PlanContent"]["x-null-policy"] == "prohibited everywhere"
    assert schemas["Mvp3Readiness"]["x-complete-predicate"].endswith("known_blockers empty")
    assert schemas["Mvp3ImplementationSummary"]["x-length-unit"] == "Unicode code points"
    assert schemas["Mvp3ImplementationSummary"]["x-semantics"].startswith("human implementation-scope description only")


def test_committed_openapi_is_baseline_plus_materialization() -> None:
    before, materialized = _materialized()
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    # Later MVP phases are intentionally present in the committed artifact.
    # Verify the current artifact still retains the exact MVP3 materialized
    # paths, schemas, and metadata without treating the whole later artifact
    # as an MVP3-only snapshot.
    added_paths = set(materialized["paths"]) - set(before["paths"])
    for path in added_paths:
        assert committed["paths"][path] == materialized["paths"][path]
    for name, schema in materialized["components"]["schemas"].items():
        if name.startswith("Mvp3"):
            assert committed["components"]["schemas"][name] == schema
    assert committed["x-mvp3"] == materialized["x-mvp3"]
