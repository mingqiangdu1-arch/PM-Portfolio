from __future__ import annotations

import json
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "packages" / "contracts" / "openapi" / "openapi.json"
MVP4_PATHS = {
    "/api/v1/confirmation-rounds/{round_id}/test-records",
    "/api/v1/test-records/{id}",
    "/api/v1/test-records/{id}:submit",
}
MVP4_OPERATION_IDS = {
    "listConfirmationRoundTestRecords",
    "createConfirmationRoundTestRecord",
    "getTestRecord",
    "updateTestRecordDraft",
    "submitTestRecord",
}


def _operations(schema: dict) -> list[dict]:
    return [
        operation
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]


def test_runtime_materializes_frozen_mvp4_surface_exactly() -> None:
    artifact = json.loads(OPENAPI.read_text(encoding="utf-8"))
    runtime = app.openapi()
    operations = _operations(runtime)
    ids = [operation["operationId"] for operation in operations]

    assert len(runtime["paths"]) == 60
    assert len(operations) == 71
    assert len(ids) == len(set(ids))
    assert set(ids) >= MVP4_OPERATION_IDS
    assert set(runtime["paths"]) >= MVP4_PATHS
    assert runtime["x-mvp4"] == {
        "contract_version": "MVP4-v1",
        "freeze_id": "MVP4-TEST-RECORD-CONTRACT-FREEZE-20260824-V1",
        "flow_end": "SUBMITTED_READ_ONLY",
        "paths_added": 3,
        "operations_added": 5,
        "schema_change_required": False,
        "new_migration_required": False,
        "ai_change_required": False,
    }
    for path in MVP4_PATHS:
        assert runtime["paths"][path] == artifact["paths"][path]
    assert runtime["components"]["schemas"]["Mvp4TestRecord"] == artifact["components"]["schemas"]["Mvp4TestRecord"]


def test_mvp4_contract_freezes_lifecycle_guards_and_permissions() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    create = paths["/api/v1/confirmation-rounds/{round_id}/test-records"]["post"]
    update = paths["/api/v1/test-records/{id}"]["patch"]
    submit = paths["/api/v1/test-records/{id}:submit"]["post"]

    assert create["x-permission"] == {
        "admin_bypass": False,
        "allowed_project_roles": ["owner", "tester"],
    }
    assert update["x-expected-version"]["stale_error"] == "VERSION_CONFLICT"
    assert submit["x-expected-version"]["field"] == "expected_version"
    assert submit["x-idempotency"]["replay"].startswith("same key")
    assert submit["x-outbox-event"] == "test.record.submitted"
    assert submit["x-audit-event"] == "test.record.submitted"
    assert schema["components"]["schemas"]["Mvp4ResultStatus"]["enum"] == [
        "success",
        "failed",
        "partial",
    ]
    record = schema["components"]["schemas"]["Mvp4TestRecord"]
    assert record["properties"]["status"]["enum"] == ["draft", "submitted"]
    assert record["properties"]["test_type"]["const"] == "manual"
