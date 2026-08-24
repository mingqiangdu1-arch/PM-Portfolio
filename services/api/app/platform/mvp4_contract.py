"""Runtime materialization for the frozen MVP4 Test Record contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


MVP4_CONTRACT_VERSION = "MVP4-v1"
MVP4_FREEZE_ID = "MVP4-TEST-RECORD-CONTRACT-FREEZE-20260824-V1"
MVP4_PATHS = (
    "/api/v1/confirmation-rounds/{round_id}/test-records",
    "/api/v1/test-records/{id}",
    "/api/v1/test-records/{id}:submit",
)


def _artifact() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    path = root / "packages" / "contracts" / "openapi" / "openapi.json"
    return json.loads(path.read_text(encoding="utf-8"))


def install_mvp4_contract(schema: dict[str, Any]) -> None:
    """Copy only frozen MVP4 components and paths into runtime OpenAPI."""
    artifact = _artifact()
    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    artifact_schemas = artifact["components"]["schemas"]
    for name, value in artifact_schemas.items():
        if name.startswith("Mvp4"):
            schemas[name] = deepcopy(value)
    if "ErrorCode" in schemas:
        schemas["ErrorCode"]["enum"] = list(artifact_schemas["ErrorCode"]["enum"])
    paths = schema.setdefault("paths", {})
    for path in MVP4_PATHS:
        paths[path] = deepcopy(artifact["paths"][path])
    schema["x-mvp4"] = {
        "contract_version": MVP4_CONTRACT_VERSION,
        "freeze_id": MVP4_FREEZE_ID,
        "flow_end": "SUBMITTED_READ_ONLY",
        "paths_added": 3,
        "operations_added": 5,
        "schema_change_required": False,
        "new_migration_required": False,
        "ai_change_required": False,
    }
