"""Verify the Review-frozen Sprint 1 OpenAPI + migration overlay without writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "contracts" / "backend-sprint1-freeze.json").read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(openapi_path: Path, delta_path: Path, migration_dir: Path) -> dict[str, object]:
    issues: list[str] = []
    openapi = json.loads(openapi_path.read_text(encoding="utf-8"))
    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    operations = [
        (path, operation)
        for path, path_item in openapi.get("paths", {}).items()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    sprint1_operations = [
        item
        for path, item in operations
        if path.startswith("/api/v1/")
        and item.get("x-implementation-status") in {"not-implemented", "implemented-candidate"}
    ]
    internal_health = openapi.get("paths", {}).get("/internal/v1/health", {}).get("get")
    if openapi.get("openapi") != EXPECTED["openapi"]["version"]:
        issues.append("openapi_version")
    if len(openapi.get("paths", {})) != EXPECTED["openapi"]["path_count"]:
        issues.append("openapi_path_count")
    if len(sprint1_operations) != EXPECTED["openapi"]["sprint1_business_operation_count"]:
        issues.append("sprint1_operation_count")
    if digest(openapi_path) != EXPECTED["openapi"]["sha256"]:
        issues.append("openapi_hash")

    expected_transaction = {
        "always": ["business_fact", "operation_audit_log", "completed_idempotency_record"],
        "when_canonical_business_event_frozen": ["business_event_outbox"],
        "rollback_on": ["audit_failure", "required_outbox_failure"],
    }
    if openapi.get("x-critical-command-transaction") != expected_transaction:
        issues.append("critical_command_transaction")

    expected_event_operations = {
        ("/api/v1/files/uploads", "post"): "file.upload.started",
        ("/api/v1/files/uploads/{upload_id}:complete", "post"): "file.upload.completed",
        ("/api/v1/projects", "post"): "project.project.created",
        ("/api/v1/projects/{project_id}/versions/{version_id}:set-working", "post"): "project.version.working_set",
        ("/api/v1/projects/{project_id}/versions:derive", "post"): "project.version.derived",
        ("/api/v1/projects/{project_id}:archive", "post"): "project.project.archived",
        ("/api/v1/projects/{project_id}:restore", "post"): "project.project.restored",
    }
    actual_event_operations: dict[tuple[str, str], str] = {}
    for path, path_item in openapi.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            marker = operation.get("x-canonical-event-transaction")
            if marker is None:
                continue
            if (
                marker.get("required") is not True
                or marker.get("only_when_frozen_canonical_event_exists") is not True
                or not marker.get("event_name")
            ):
                issues.append(f"canonical_event_marker:{method}:{path}")
                continue
            actual_event_operations[(path, method)] = marker["event_name"]
    if actual_event_operations != expected_event_operations:
        issues.append("canonical_event_operation_mapping")
    if (
        delta.get("base_catalog") != EXPECTED["schema_overlay"]["base_catalog"]
        or delta.get("revision") != EXPECTED["schema_overlay"]["head_revision"]
    ):
        issues.append("schema_overlay_lineage")
    if digest(delta_path) != EXPECTED["schema_overlay"]["sha256"]:
        issues.append("schema_overlay_hash")

    required_delta_fields = {
        "ai_task": {"target_snapshot_hash", "command_id"},
        "ai_call": {"capability_fingerprint", "cost_source", "pricing_version", "provider_error_class"},
        "user_session": {"token_family_id", "rotated_at", "replaced_by_session_id"},
        "file_version": {"storage_version_id"},
    }
    for table, fields in required_delta_fields.items():
        if not fields.issubset(delta.get("tables", {}).get(table, {}).get("add", {})):
            issues.append(f"delta_fields:{table}")
    if delta.get("tables", {}).get("user_session", {}).get("alter", {}).get("revoked_at", {}).get("nullable") is not True:
        issues.append("revoked_at_nullable")
    storage_version = delta.get("tables", {}).get("file_version", {}).get("add", {}).get("storage_version_id", {})
    if storage_version.get("nullable") is not True or storage_version.get("new_available_write_required") is not True:
        issues.append("storage_version_rollout_rule")

    if not internal_health:
        issues.append("internal_health_missing")
    else:
        scheme = openapi.get("components", {}).get("securitySchemes", {}).get("serviceBearerAuth", {})
        expected_health = EXPECTED["internal_health"]["outbound_business_api"]
        if expected_health["issuer"] not in scheme.get("x-required-issuers", []):
            issues.append("internal_health_issuer")
        if scheme.get("x-ai-caller-subject") != expected_health["issuer"]:
            issues.append("internal_health_subject")
        if scheme.get("x-required-audience") != expected_health["audience"]:
            issues.append("internal_health_audience")
        if scheme.get("x-required-scope") != expected_health["scope"]:
            issues.append("internal_health_scope")

    for revision, expected_hash in EXPECTED["migrations"].items():
        matches = list(migration_dir.glob(f"{revision}_*.py"))
        if len(matches) != 1 or digest(matches[0]) != expected_hash:
            issues.append(f"migration:{revision}")

    return {
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "openapi_paths": len(openapi.get("paths", {})),
        "sprint1_operations": len(sprint1_operations),
        "schema_head": delta.get("revision"),
        "persistence_adapter_enabled": False,
        "business_health_runtime": "contract_match" if not any(item.startswith("internal_health_") for item in issues) else "contract_mismatch",
        "transaction_contract": "conditional_outbox_match" if not any(item.startswith(("critical_command_", "canonical_event_")) for item in issues) else "contract_mismatch",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi", type=Path, required=True)
    parser.add_argument("--schema-delta", type=Path, required=True)
    parser.add_argument("--migration-dir", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.openapi, args.schema_delta, args.migration_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
