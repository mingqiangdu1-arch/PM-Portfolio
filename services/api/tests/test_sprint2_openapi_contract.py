import json
import subprocess
import unittest
from pathlib import Path

from app.main import app


DIMENSIONS = [
    "goal", "users_and_roles", "usage_scenarios", "functional_scope",
    "business_rules", "exception_cases", "permission_requirements", "acceptance_criteria",
]
TASK_STATES = [
    "prechecking", "blocked", "queued", "preparing", "generating", "checking", "ready",
    "partial_result", "quality_blocked", "cancel_requested", "cancelled", "failed", "expired", "stale_target",
]
RESULT_STATES = ["ready", "partial_result", "quality_blocked", "failed", "expired", "stale_target"]
S2_PATHS = {
    "/api/v1/project-versions/{version_id}/requirements", "/api/v1/requirements/{requirement_id}",
    "/api/v1/requirement-versions/{version_id}", "/api/v1/requirement-versions/{version_id}:set-clarification-mode",
    "/api/v1/requirement-versions/{version_id}/clarification-answers", "/api/v1/requirement-versions/{version_id}/clarification-result",
    "/api/v1/requirements/{requirement_id}/versions",
    "/api/v1/requirement-versions/{version_id}:confirm", "/api/v1/ai/tasks", "/api/v1/ai/tasks/{task_id}",
    "/api/v1/ai/tasks/{task_id}/events", "/api/v1/ai/tasks/{task_id}:cancel", "/api/v1/ai/tasks/{task_id}:retry",
    "/api/v1/ai/results/{result_id}", "/api/v1/ai/results/{result_id}:formalize",
}


class Sprint2OpenApiCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = app.openapi()
        cls.components = cls.schema["components"]["schemas"]

    def test_candidate_metadata_and_deferred_scope(self) -> None:
        phase = self.schema["x-sprint-2-phase-a"]
        self.assertEqual(phase["status"], "pending_review")
        self.assertEqual(phase["candidate_version"], "R4")
        self.assertTrue(phase["implementation_authorized"])
        self.assertEqual(self.schema["info"]["x-contract-status"], "candidate")
        self.assertEqual(
            self.schema["info"]["summary"],
            "Sprint 2 Requirement/Baseline R4 implementation candidate",
        )
        self.assertIn("PORTFOLIO-P1-RUNTIME-01", self.schema["info"]["description"])
        self.assertIn("pending Review", self.schema["info"]["description"])
        self.assertTrue(phase["feature_flags"]["persistence_adapter_enabled"] is False)
        self.assertTrue(phase["feature_flags"]["flow_enabled"] is False)
        self.assertNotIn("review_blockers", phase)
        self.assertIn("BE-202", self.schema["x-sprint-2-phase-a"]["x-deferred-scope"])
        top_level_metadata = json.dumps(
            {"info": self.schema["info"], "phase": phase},
            ensure_ascii=False,
        )
        self.assertNotIn("R2", top_level_metadata)
        self.assertNotIn("contract-only-r2-candidate", top_level_metadata)
        serialized = json.dumps(self.schema, ensure_ascii=False)
        self.assertNotIn("x-review-blocker", serialized)
        self.assertNotIn("pending-m2-contracts-frozen", serialized)

    def test_enumerations_and_canonical_dimensions(self) -> None:
        self.assertEqual(self.components["RequirementDimension"]["enum"], DIMENSIONS)
        self.assertEqual(self.components["AiTaskStatus"]["enum"], TASK_STATES)
        self.assertEqual(self.components["AiResultStatus"]["enum"], RESULT_STATES)
        self.assertEqual(self.components["AiResultKind"]["enum"], ["assessment", "questions", "baseline"])
        self.assertEqual(self.components["RequirementSourceType"]["enum"], ["manual", "file_import"])
        self.assertEqual(self.components["RequirementPriority"]["enum"], ["low", "normal", "high", "critical"])
        self.assertEqual(self.components["AdoptionStatus"]["enum"], ["adopted", "adopted_after_edit", "rejected"])

    def test_requirement_content_and_baseline_shape(self) -> None:
        content = self.components["RequirementContent"]
        raw_input = content["properties"]["raw_input"]
        self.assertEqual(raw_input["type"], "string")
        self.assertEqual(raw_input["minLength"], 1)
        self.assertTrue(raw_input["readOnly"])
        self.assertIn("raw_input", content["required"])
        self.assertTrue(content["properties"]["raw_input_ref"]["readOnly"])
        source_ref = self.components["SourceRef"]
        self.assertEqual(
            set(source_ref["properties"]),
            {"source_type", "source_id", "source_version_id", "content_hash", "label"},
        )
        self.assertEqual(
            source_ref["required"],
            ["source_type", "source_id", "source_version_id", "content_hash", "label"],
        )
        baseline = self.components["RequirementBaseline"]
        dimensions = baseline["properties"]["dimensions"]
        self.assertEqual(dimensions["required"], DIMENSIONS)
        self.assertFalse(dimensions["additionalProperties"])
        for dimension in DIMENSIONS:
            self.assertEqual(
                self.components["RequirementBaselineDimension"]["required"],
                ["confirmed_facts", "source_refs", "deferred_items", "not_applicable_items"],
            )
        self.assertEqual(self.components["ClarificationAnswer"]["required"], ["question_id", "answer"])
        answer_data = self.components["ClarificationAnswerData"]
        self.assertNotIn("next_task_ref", answer_data["properties"])
        self.assertTrue(answer_data["properties"]["task_creation"]["properties"]["decoupled"]["const"])

    def test_raw_input_persistence_and_immutability_policy(self) -> None:
        expected_policy = {
            "persisted_path": "requirement_version.content_json.raw_input",
            "immutable_across_versions": True,
            "ref_content_hash": "sha256(utf8(raw_input))",
        }
        self.assertEqual(self.schema["x-raw-input-policy"], expected_policy)
        create = self.schema["paths"][
            "/api/v1/project-versions/{version_id}/requirements"
        ]["post"]
        self.assertEqual(create["x-raw-input-policy"], expected_policy)
        self.assertIn("Persists raw_input unchanged", create["description"])
        self.assertIn("inherit raw_input and cannot modify it", create["description"])
        revise = self.schema["paths"]["/api/v1/requirement-versions/{version_id}"]["patch"]
        create_version = self.schema["paths"]["/api/v1/requirements/{requirement_id}/versions"]["post"]
        self.assertIn("raw_input is inherited and cannot be modified", revise["description"])
        self.assertIn("raw_input is inherited and cannot be modified", create_version["description"])
        request = self.components["CreateRequirementRequest"]
        self.assertIn("raw_input", request["required"])
        self.assertEqual(request["properties"]["raw_input"]["minLength"], 1)

    def test_task_envelope_and_public_create_are_separated(self) -> None:
        envelope = self.components["RequirementClarifyTaskEnvelope"]
        self.assertEqual(envelope["properties"]["schema_version"]["const"], "0.2.0")
        self.assertEqual(envelope["properties"]["module"]["const"], "product_design")
        self.assertEqual(envelope["properties"]["task_type"]["const"], "requirement.clarify")
        public = self.components["CreateAiTaskRequest"]
        self.assertNotIn("input", public["properties"])
        for derived in ("user_id", "command_id", "trace_id", "requested_at", "project_id", "project_version_id", "module"):
            self.assertNotIn(derived, public["properties"])
        operation = self.schema["paths"]["/api/v1/ai/tasks"]["post"]
        self.assertEqual(operation["x-command-envelope"]["ref"], "#/components/schemas/RequirementClarifyTaskEnvelope")
        task_summary = self.components["AiTaskSummary"]
        self.assertIn("result_refs", task_summary["required"])
        self.assertEqual(
            task_summary["properties"]["result_refs"]["items"]["$ref"],
            "#/components/schemas/AiTaskResultRef",
        )
        task_result_ref = self.components["AiTaskResultRef"]
        self.assertEqual(
            set(task_result_ref["properties"]),
            {"result_id", "status", "target_snapshot_hash"},
        )
        self.assertEqual(
            task_result_ref["required"],
            ["result_id", "status", "target_snapshot_hash"],
        )

    def test_result_payload_conditions_and_formalization_rules(self) -> None:
        content = self.components["AiResultContent"]
        self.assertNotIn("oneOf", content)
        self.assertEqual(len(content["allOf"]), 5)
        self.assertEqual(
            self.components["AiResultQuality"]["required"],
            [
                "format_status",
                "traceability_status",
                "safety_status",
                "major_error",
                "blocker_codes",
                "required_items_total",
                "required_items_met",
            ],
        )
        formalize = self.components["FormalizeAiResultRequest"]
        self.assertEqual(len(formalize["oneOf"]), 4)
        self.assertNotIn("not_reviewed", self.components["FormalizeAiResultData"]["properties"]["adoption_status"]["enum"])

    def test_operation_permissions_transactions_and_errors(self) -> None:
        self.assertEqual(set(self.schema["paths"]) & S2_PATHS, S2_PATHS)
        for path in S2_PATHS:
            for operation in self.schema["paths"][path].values():
                if not isinstance(operation, dict) or "operationId" not in operation:
                    continue
                self.assertEqual(operation["x-contract-phase"], "sprint-2-p1-runtime-r4-candidate")
                self.assertEqual(operation["x-implementation-status"], "implemented-p1-runtime-r4-candidate")
                self.assertNotIn("x-r2-decisions", operation)
                self.assertIn("x-permission", operation)
                self.assertFalse(operation["x-permission"]["admin_bypass"])
                for status in ("401", "403", "404", "409", "422", "429", "503"):
                    self.assertEqual(operation["responses"][status]["$ref"], f"#/components/responses/Sprint2Error{status}")
        sse = self.schema["paths"]["/api/v1/ai/tasks/{task_id}/events"]["get"]
        self.assertEqual(sse["x-sse-authorization"]["recheck"], ["connect", "before_each_event", "before_heartbeat"])
        for op_id in ("cancelAiTask", "retryAiTask"):
            op = next(o for p in self.schema["paths"].values() for o in p.values() if isinstance(o, dict) and o.get("operationId") == op_id)
            self.assertEqual(op["x-permission"]["allowed_project_roles"], ["owner"])
            self.assertEqual(op["x-permission"]["additional_actor_predicate"], "task_initiator")
        formalize = self.schema["paths"]["/api/v1/ai/results/{result_id}:formalize"]["post"]
        self.assertFalse(formalize["x-formalize-branches"]["reject"]["creates_requirement_version"])

        recovery = self.schema["paths"]["/api/v1/requirement-versions/{version_id}/clarification-result"]["get"]
        self.assertEqual(recovery["operationId"], "getRequirementVersionClarificationResult")
        self.assertEqual(recovery["responses"]["200"]["content"]["application/json"]["schema"]["$ref"], "#/components/schemas/AiResultResponse")
        self.assertTrue(recovery["x-read-only"])
        self.assertEqual(recovery["x-side-effects"], {
            "task_creation": False,
            "provider_call": False,
            "requirement_mutation": False,
            "result_mutation": False,
        })

    def test_error_mapping_and_events_are_explicit(self) -> None:
        mapping = self.schema["x-error-http-mapping"]
        self.assertEqual(mapping["AUTH_REQUIRED"], 401)
        self.assertEqual(mapping["FORBIDDEN"], 403)
        self.assertEqual(mapping["RESOURCE_NOT_FOUND"], 404)
        self.assertEqual(mapping["VERSION_CONFLICT"], 409)
        self.assertEqual(mapping["VALIDATION_ERROR"], 422)
        self.assertEqual(mapping["AI_QUOTA_EXCEEDED"], 429)
        self.assertEqual(mapping["QUEUE_UNAVAILABLE"], 503)
        events = self.schema["x-requirement-events"]
        self.assertEqual(events["schema_version"], "0.2.0")
        self.assertEqual(events["producer"], "Business API")
        self.assertEqual(events["envelope_excludes"], ["ingested_at"])
        self.assertIn("explicitly_closed", events["adoption_events"]["ai.result.left_unreviewed"])
        self.assertIn("analytics_status=not_reviewed", events["adoption_events"]["ai.result.left_unreviewed"])
        self.assertIn("RequirementEventEnvelope", self.components)
        event = self.components["RequirementEventEnvelope"]
        expected = [
            "schema_version", "event_id", "event_name", "occurred_at", "producer", "module",
            "result_status", "source_type", "privacy_class", "user_id", "project_id",
            "project_version_id", "object_type", "object_id", "object_version_id", "trace_id",
            "command_id", "payload_json",
        ]
        self.assertEqual(event["required"], expected)
        self.assertEqual(set(event["properties"]), set(expected))
        self.assertNotIn("ingested_at", event["properties"])
        self.assertEqual(event["properties"]["producer"]["const"], "Business API")
        self.assertEqual(event["properties"]["object_type"]["const"], "requirement")
        formal_payload = self.components["ArtifactVersionFormalizedPayload"]
        self.assertEqual(formal_payload["required"], ["artifact_type", "formal_version_id", "source_ai_result_id"])
        for event_name, schema_name in {
            "requirement.clarification.assessed": "RequirementClarificationAssessedPayload",
            "requirement.clarification.mode_selected": "RequirementClarificationModeSelectedPayload",
            "requirement.clarification.round_completed": "RequirementClarificationRoundCompletedPayload",
            "requirement.clarification.finished": "RequirementClarificationFinishedPayload",
        }.items():
            self.assertEqual(events["events"][event_name]["payload_schema"], f"#/components/schemas/{schema_name}")
            self.assertEqual(events["events"][event_name]["payload"], self.components[schema_name]["required"])

    def test_old_module1_paths_operations_and_security_are_preserved(self) -> None:
        root = Path(__file__).resolve().parents[3]
        old = json.loads(subprocess.check_output(["git", "show", "HEAD:packages/contracts/openapi/openapi.json"], cwd=root))
        self.assertEqual(len(old["paths"]), 29)
        self.assertEqual(sum(1 for path in old["paths"].values() for value in path.values() if isinstance(value, dict) and "operationId" in value), 32)
        self.assertEqual(set(old["components"]["securitySchemes"]), set(self.schema["components"]["securitySchemes"]))
        for path, path_item in old["paths"].items():
            self.assertIn(path, self.schema["paths"])
            for method, old_operation in path_item.items():
                if not isinstance(old_operation, dict) or "operationId" not in old_operation:
                    continue
                current = self.schema["paths"][path][method]
                self.assertEqual(current["operationId"], old_operation["operationId"])
                self.assertEqual(current.get("security"), old_operation.get("security"))


if __name__ == "__main__":
    unittest.main()
