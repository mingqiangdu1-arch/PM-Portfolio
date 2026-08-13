import unittest
from typing import Any

from app.main import app


class OpenApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = app.openapi()

    def test_contract_metadata(self) -> None:
        self.assertEqual(self.schema["openapi"], "3.1.0")
        self.assertEqual(self.schema["info"]["x-contract-status"], "candidate")
        self.assertEqual(self.schema["x-api-prefix"], "/api/v1")
        self.assertEqual(self.schema["x-internal-api-prefix"], "/internal/v1")

    def test_shared_contract_components(self) -> None:
        components = self.schema["components"]
        self.assertIn("bearerAuth", components["securitySchemes"])
        self.assertIn("IdempotencyKey", components["parameters"])
        self.assertIn("Cursor", components["parameters"])
        self.assertIn("CursorPage", components["schemas"])
        self.assertIn("VersionedCommand", components["schemas"])
        self.assertIn("VERSION_CONFLICT", components["schemas"]["ErrorCode"]["enum"])

    def test_health_paths_and_error_envelopes(self) -> None:
        for path in ("/health/live", "/health/ready", "/api/v1/health"):
            operation = self.schema["paths"][path]["get"]
            self.assertIn("200", operation["responses"])
            self.assertEqual(
                operation["responses"]["409"]["$ref"],
                "#/components/responses/StandardError",
            )

    def test_sprint1_consumer_paths_are_published(self) -> None:
        required = {
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/session",
            "/api/v1/projects",
            "/api/v1/projects/{project_id}",
            "/api/v1/projects/{project_id}/versions",
            "/api/v1/projects/{project_id}/versions/{version_id}:set-working",
            "/api/v1/projects/{project_id}/versions:derive",
            "/api/v1/project-versions/{left_id}:compare",
            "/api/v1/files/uploads",
            "/api/v1/files/uploads/{upload_id}:complete",
            "/api/v1/file-versions/{version_id}:download",
            "/api/v1/file-versions/{version_id}/relations",
            "/internal/v1/health",
        }
        self.assertTrue(required.issubset(self.schema["paths"]))

    def test_internal_health_service_identity_is_frozen(self) -> None:
        operation = self.schema["paths"]["/internal/v1/health"]["get"]
        self.assertEqual(operation["security"], [{"serviceBearerAuth": []}])
        scheme = self.schema["components"]["securitySchemes"]["serviceBearerAuth"]
        self.assertEqual(scheme["x-required-issuers"], ["ai-api", "monitoring"])
        self.assertEqual(scheme["x-ai-caller-subject"], "ai-api")
        self.assertEqual(scheme["x-required-audience"], "business-api")
        self.assertEqual(scheme["x-required-scope"], "health")

    def test_version_compare_contract_is_read_only_and_explicit(self) -> None:
        operation = self.schema["paths"][
            "/api/v1/project-versions/{left_id}:compare"
        ]["get"]
        parameters = {
            (parameter.get("name"), parameter.get("in")): parameter
            for parameter in operation["parameters"]
        }
        self.assertTrue(parameters[("left_id", "path")]["required"])
        self.assertTrue(parameters[("right_version_id", "query")]["required"])
        self.assertIn("never changes", operation["description"])

    def test_critical_commands_have_idempotency_and_expected_version(self) -> None:
        commands = {
            ("/api/v1/projects/{project_id}:archive", "ProjectCommandRequest"),
            ("/api/v1/projects/{project_id}:restore", "ProjectCommandRequest"),
            (
                "/api/v1/projects/{project_id}/versions/{version_id}:set-working",
                "SetWorkingVersionRequest",
            ),
            (
                "/api/v1/projects/{project_id}/versions:derive",
                "DeriveProjectVersionRequest",
            ),
        }
        for path, request_schema in commands:
            operation = self.schema["paths"][path]["post"]
            parameter_refs = {item.get("$ref") for item in operation["parameters"]}
            self.assertIn("#/components/parameters/IdempotencyKey", parameter_refs)
            properties = self.schema["components"]["schemas"][request_schema]["properties"]
            self.assertTrue(
                "expected_version" in properties or "expected_project_version" in properties
            )

    def test_critical_transaction_outbox_is_conditional_on_frozen_event(self) -> None:
        transaction = self.schema["x-critical-command-transaction"]
        self.assertEqual(
            transaction["always"],
            ["business_fact", "operation_audit_log", "completed_idempotency_record"],
        )
        self.assertEqual(
            transaction["when_canonical_business_event_frozen"],
            ["business_event_outbox"],
        )
        self.assertEqual(
            transaction["rollback_on"],
            ["audit_failure", "required_outbox_failure"],
        )

        complete = self.schema["paths"][
            "/api/v1/files/uploads/{upload_id}:complete"
        ]["post"]
        relation = self.schema["paths"][
            "/api/v1/file-versions/{version_id}/relations"
        ]["post"]
        member = self.schema["paths"][
            "/api/v1/projects/{project_id}/members/{user_id}"
        ]["put"]
        archive_file = self.schema["paths"]["/api/v1/files/{file_id}:archive"]["post"]
        self.assertEqual(
            complete["x-canonical-event-transaction"],
            {
                "required": True,
                "only_when_frozen_canonical_event_exists": True,
                "event_name": "file.upload.completed",
            },
        )
        for operation in (relation, member, archive_file):
            self.assertNotIn("x-canonical-event-transaction", operation)

        abort = self.schema["paths"]["/api/v1/files/uploads/{upload_id}:abort"]["post"]
        self.assertNotIn("x-canonical-event-transaction", abort)

    def test_fixed_roles_and_refresh_cookie_are_explicit(self) -> None:
        roles = self.schema["components"]["schemas"]["ProjectRole"]["enum"]
        self.assertEqual(roles, ["owner", "reviewer", "implementer", "tester"])
        refresh = self.schema["components"]["securitySchemes"]["refreshCookie"]
        self.assertEqual(refresh["in"], "cookie")
        self.assertIn("seven days", refresh["description"])

    def test_browser_refresh_cookie_and_origin_contract_is_explicit(self) -> None:
        for path, action in (
            ("/api/v1/auth/register", "set"),
            ("/api/v1/auth/login", "set"),
            ("/api/v1/auth/refresh", "rotate"),
            ("/api/v1/auth/logout", "clear"),
        ):
            operation = self.schema["paths"][path]["post"]
            self.assertEqual(operation["x-refresh-cookie"]["action"], action)
            self.assertIn("Set-Cookie", operation["responses"]["200"]["headers"])
        for path in ("/api/v1/auth/refresh", "/api/v1/auth/logout"):
            operation = self.schema["paths"][path]["post"]
            policy = operation["x-cookie-command-origin-policy"]
            self.assertEqual(policy["requireOneOf"], ["Origin", "Referer"])
            self.assertIn("ORIGIN_MISMATCH", policy["failureCodes"])
            refs = {item.get("$ref") for item in operation["parameters"]}
            self.assertIn("#/components/parameters/Origin", refs)
            self.assertIn("#/components/parameters/Referer", refs)
            self.assertIn("#/components/parameters/CsrfToken", refs)

    def test_pending_file_version_is_not_public_before_finalization(self) -> None:
        init = self.schema["paths"]["/api/v1/files/uploads"]["post"]
        self.assertEqual(init["x-pending-file-version"]["visibility"], "internal-only")
        self.assertIn(
            "download", init["x-pending-file-version"]["forbiddenBeforeComplete"]
        )
        complete = self.schema["paths"][
            "/api/v1/files/uploads/{upload_id}:complete"
        ]["post"]
        finalization = complete["x-file-version-finalization"]
        self.assertEqual((finalization["from"], finalization["to"]), ("pending", "available"))
        self.assertTrue(finalization["once"])
        self.assertTrue(finalization["immutableAfter"])
        self.assertEqual(finalization["uploadChecksumHeader"], "x-amz-checksum-sha256")
        self.assertEqual(finalization["finalObjectStrategy"], "server-conditional-copy")
        self.assertEqual(finalization["persistedImmutableIdentifier"], "storage_version_id")
        version_list = self.schema["components"]["schemas"]["FileVersionList"]
        self.assertIn("available immutable", version_list["description"])

    def test_all_local_component_references_resolve(self) -> None:
        references: list[str] = []

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "$ref" and isinstance(item, str):
                        references.append(item)
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(self.schema)
        for reference in references:
            if not reference.startswith("#/"):
                continue
            current: Any = self.schema
            for part in reference[2:].split("/"):
                current = current[part.replace("~1", "/").replace("~0", "~")]
            self.assertIsNotNone(current, reference)
