from __future__ import annotations

import json
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "packages" / "contracts" / "openapi" / "openapi.json"
MVP5_PATHS = {
    "/api/v1/test-records/{id}:conclude-no-issue",
    "/api/v1/project-versions/{version_id}/issues",
    "/api/v1/issues/{issue_id}",
    "/api/v1/issues/{issue_id}/dispositions",
}
MVP5_OPERATIONS = {
    "concludeTestRecordNoIssue",
    "listProjectVersionIssues",
    "createProjectVersionIssue",
    "getIssue",
    "updateIssue",
    "createIssueDisposition",
}


def _operations(schema: dict) -> list[dict]:
    return [
        operation
        for item in schema["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]


def test_runtime_materializes_frozen_mvp5_surface_exactly() -> None:
    artifact = json.loads(OPENAPI.read_text(encoding="utf-8"))
    runtime = app.openapi()
    operations = _operations(runtime)
    ids = [operation["operationId"] for operation in operations]

    assert len(runtime["paths"]) == 64
    assert len(operations) == 77
    assert len(ids) == len(set(ids))
    assert set(ids) >= MVP5_OPERATIONS
    assert set(runtime["paths"]) >= MVP5_PATHS
    assert runtime["x-mvp5"] == {
        "contract_version": "MVP5-v1",
        "freeze_id": "MVP5-VALIDATION-FEEDBACK-CONTRACT-FREEZE-20260825-V1",
        "product_goal": "REAL_AI_REQUIREMENT_TO_VALIDATION_FEEDBACK_CLOSURE",
        "paths_added": 4,
        "operations_added": 6,
        "schema_change_required": False,
        "new_migration_required": False,
        "state_machine_change_required": False,
    }
    for path in MVP5_PATHS:
        assert runtime["paths"][path] == artifact["paths"][path]
    for name in ("Mvp4TestRecord", "Mvp5Issue", "Mvp5IssueDispositionRequest"):
        assert runtime["components"]["schemas"][name] == artifact["components"]["schemas"][name]


def test_mvp5_contract_freezes_mutual_exclusion_and_disposition_semantics() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    conclude = paths["/api/v1/test-records/{id}:conclude-no-issue"]["post"]
    create = paths["/api/v1/project-versions/{version_id}/issues"]["post"]
    dispose = paths["/api/v1/issues/{issue_id}/dispositions"]["post"]

    assert conclude["x-mutual-exclusion"] == "no Issue may exist for this Test Record"
    assert create["x-mutual-exclusion"] == "no_issue_conclusion must be false"
    assert dispose["x-derived-version-atomic-command"] is True
    assert dispose["x-permission"]["allowed_project_roles"] == ["owner"]
    assert schema["components"]["schemas"]["Mvp5IssueCreateRequest"]["properties"]["issue_type"]["enum"] == [
        "defect",
        "feedback",
        "data_anomaly",
        "optimization",
    ]
    assert schema["components"]["schemas"]["Mvp5IssueDispositionRequest"]["properties"]["disposition_type"]["enum"] == [
        "current_version_fix",
        "defer",
        "reject",
    ]
    request_dispositions = schema["components"]["schemas"][
        "Mvp5IssueDispositionRequest"
    ]["properties"]["disposition_type"]["enum"]
    assert "derive_new_version" not in request_dispositions
    response_dispositions = schema["components"]["schemas"]["Mvp5IssueDisposition"][
        "properties"
    ]["disposition_type"]["enum"]
    assert "derive_new_version" in response_dispositions
    assert (
        paths["/api/v1/projects/{project_id}/versions:derive"]["post"]["operationId"]
        == "deriveProjectVersion"
    )
