import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_review_frozen_backend_snapshot_records_passed_runtime_and_keeps_risky_features_disabled() -> None:
    snapshot = json.loads((ROOT / "contracts" / "backend-sprint1-freeze.json").read_text(encoding="utf-8"))
    assert snapshot["review_status"] == "review_approved"
    assert snapshot["runtime_integration_status"] == "passed"
    assert snapshot["openapi"]["path_count"] == 29
    assert snapshot["openapi"]["sprint1_business_operation_count"] == 28
    assert snapshot["schema_overlay"]["head_revision"] == "20260729_0004"
    assert snapshot["observed_current_backend_overlay"]["status"] == "runtime_integration_passed"
    assert set(snapshot["migrations"]) == {
        "20260729_0001",
        "20260729_0002",
        "20260729_0003",
        "20260729_0004",
    }
    assert snapshot["migrations"]["20260729_0001"] == (
        "d304df59e8073b1e2bf19ff4cb3ff2929aa8e5b4384d67ac5d7929be9e31e4b5"
    )
    assert snapshot["internal_health"]["outbound_business_api"] == {
        "path": "/internal/v1/health",
        "issuer": "ai-api",
        "audience": "business-api",
        "scope": "health",
    }
    assert snapshot["persistence_adapter_enabled"] is False
    assert snapshot["flow_enabled"] is False
