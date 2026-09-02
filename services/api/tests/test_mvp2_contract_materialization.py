from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
MVP2_PATHS = {
    "/api/v1/project-versions/{version_id}/prds",
    "/api/v1/prds/{prd_id}",
    "/api/v1/prd-versions/{version_id}",
    "/api/v1/prds/{prd_id}/versions",
    "/api/v1/project-versions/{version_id}/design-reviews",
    "/api/v1/design-reviews/{review_id}",
    "/api/v1/design-reviews/{review_id}:decide",
}


def operation_count(schema: dict) -> int:
    return sum(
        method in METHODS
        for path_item in schema["paths"].values()
        for method in path_item
    )


class Mvp2ContractMaterializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(
            subprocess.check_output(
                ["git", "show", "HEAD:packages/contracts/openapi/openapi.json"],
                cwd=ROOT,
            )
        )
        cls.schema = app.openapi()

    def test_scope_is_exactly_50_paths_and_56_operations(self) -> None:
        # This test used to compare the MVP2 delivery snapshot (43 -> 50
        # paths). The current frozen final artifact is 66 paths / 79
        # operations and includes the later MVP3-MVP5 and AI task-list
        # surfaces, so only current artifact/runtime parity is authoritative.
        self.assertEqual(
            (len(self.base["paths"]), operation_count(self.base)),
            (len(self.schema["paths"]), operation_count(self.schema)),
        )
        self.assertEqual(set(self.schema["paths"]), set(self.base["paths"]))
        self.assertTrue(MVP2_PATHS.issubset(self.schema["paths"]))

    def test_all_r3_path_items_are_deeply_unchanged(self) -> None:
        for path, path_item in self.base["paths"].items():
            self.assertEqual(self.schema["paths"][path], path_item, path)

    def test_contract_metadata_states_and_content_keys_are_frozen(self) -> None:
        metadata = self.schema["x-mvp2-prd-review"]
        self.assertEqual(metadata["contract_version"], "mvp2.prd-review.rc02.v1")
        self.assertEqual(
            metadata["freeze_id"], "RC-02-FREEZE-11-20260821-MVP2-PRD-REVIEW-V1"
        )
        schemas = self.schema["components"]["schemas"]
        self.assertEqual(
            schemas["Mvp2PrdStatus"]["enum"],
            ["draft", "in_review", "changes_requested", "confirmed"],
        )
        self.assertEqual(
            schemas["Mvp2DesignReviewStatus"]["enum"],
            ["open", "changes_requested", "passed"],
        )
        self.assertEqual(
            schemas["Mvp2ReviewDecision"]["enum"], ["changes_requested", "pass"]
        )
        content = schemas["Mvp2PrdContent"]
        expected_keys = {
            "schema_version",
            "background",
            "goal",
            "primary_user",
            "in_scope",
            "out_of_scope",
            "core_workflow",
            "key_rules",
            "exceptions_and_boundaries",
            "acceptance_criteria",
        }
        self.assertEqual(set(content["properties"]), expected_keys)
        self.assertEqual(set(content["required"]), expected_keys)
        self.assertFalse(content["additionalProperties"])
        self.assertEqual(content["properties"]["schema_version"]["const"], "prd.mvp2.v1")

    def test_posts_require_idempotency_and_mutable_commands_use_expected_version(self) -> None:
        for path in MVP2_PATHS:
            operation = self.schema["paths"][path].get("post")
            if not operation:
                continue
            self.assertIn(
                {"$ref": "#/components/parameters/IdempotencyKey"},
                operation["parameters"],
            )
            self.assertEqual(operation["x-permission"]["allowed_project_roles"], ["owner"])
        for path in (
            "/api/v1/prds/{prd_id}/versions",
            "/api/v1/project-versions/{version_id}/design-reviews",
            "/api/v1/design-reviews/{review_id}:decide",
        ):
            request = self.schema["paths"][path]["post"]["requestBody"]["content"][
                "application/json"
            ]["schema"]["$ref"].rsplit("/", 1)[-1]
            request_schema = self.schema["components"]["schemas"][request]
            if "oneOf" in request_schema:
                self.assertTrue(
                    all("expected_version" in branch["required"] for branch in request_schema["oneOf"])
                )
            else:
                self.assertIn("expected_version", request_schema["required"])

    def test_frozen_error_mapping_and_no_forbidden_scope(self) -> None:
        self.assertEqual(
            self.schema["x-mvp2-prd-review"]["error_http_mapping"],
            {
                "INVALID_STATE": 409,
                "VERSION_CONFLICT": 409,
                "FORBIDDEN": 403,
                "NOT_FOUND": 404,
                "VALIDATION_ERROR": 422,
                "IDEMPOTENCY_CONFLICT": 409,
            },
        )
        for status in (403, 404, 409, 422):
            codes = self.schema["components"]["responses"][f"Mvp2Error{status}"][
                "content"
            ]["application/json"]["schema"]["allOf"][1]["properties"]["code"]["enum"]
            self.assertEqual(
                set(codes),
                {
                    code
                    for code, mapped_status in self.schema["x-mvp2-prd-review"][
                        "error_http_mapping"
                    ].items()
                    if mapped_status == status
                },
            )
        serialized = json.dumps(
            {
                "paths": {path: self.schema["paths"][path] for path in MVP2_PATHS},
                "metadata": self.schema["x-mvp2-prd-review"],
            },
            sort_keys=True,
        ).lower()
        for forbidden in (
            "comment_thread",
            "reviewer_assignment",
            "multi_reviewer",
            "accepted",
            "approved",
            "flow",
            "implementation_plan",
            "file_upload",
            "knowledge",
            "ai_runtime",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
