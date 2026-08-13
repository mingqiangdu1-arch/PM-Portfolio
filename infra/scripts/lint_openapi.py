from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "packages" / "contracts" / "openapi" / "openapi.json"


def main() -> None:
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))
    errors: list[str] = []
    if schema.get("openapi") != "3.1.0":
        errors.append("openapi must be 3.1.0")
    if schema.get("x-api-prefix") != "/api/v1":
        errors.append("x-api-prefix must be /api/v1")
    required_paths = {
        "/health/live",
        "/health/ready",
        "/api/v1/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/projects",
        "/api/v1/projects/{project_id}/versions/{version_id}:set-working",
        "/api/v1/projects/{project_id}/versions:derive",
        "/api/v1/project-versions/{left_id}:compare",
        "/api/v1/files/uploads",
        "/api/v1/files/uploads/{upload_id}:complete",
        "/internal/v1/health",
    }
    if not required_paths.issubset(schema.get("paths", {})):
        errors.append("health paths are incomplete")
    components = schema.get("components", {})
    for component in ("ErrorResponse", "CursorPage", "VersionedCommand"):
        if component not in components.get("schemas", {}):
            errors.append(f"missing schema component {component}")
    if "IdempotencyKey" not in components.get("parameters", {}):
        errors.append("missing Idempotency-Key parameter")
    expected_roles = ["owner", "reviewer", "implementer", "tester"]
    if components.get("schemas", {}).get("ProjectRole", {}).get("enum") != expected_roles:
        errors.append("ProjectRole must contain only the four fixed project roles")
    operation_ids = [
        operation.get("operationId")
        for path in schema.get("paths", {}).values()
        for operation in path.values()
        if isinstance(operation, dict) and operation.get("operationId")
    ]
    if len(operation_ids) != len(set(operation_ids)):
        errors.append("operationId values must be unique")
    if errors:
        raise SystemExit("OpenAPI lint failed:\n- " + "\n- ".join(errors))
    print(f"OpenAPI lint passed: {CONTRACT}")


if __name__ == "__main__":
    main()
