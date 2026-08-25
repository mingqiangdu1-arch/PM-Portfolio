from __future__ import annotations

import json

import unittest

from app.providers.base import ProviderMalformedResponse, ProviderResponse, ProviderUsage
from app.requirement_clarification.formal_mock import DIMENSIONS
from app.requirement_clarification.models import ClarificationSource, RequirementClarifyTask
from app.requirement_clarification.real_provider import RealRequirementClarifier


def task(*, mode: str = "auto", round_no: int = 0) -> RequirementClarifyTask:
    return RequirementClarifyTask.model_validate(
        {
            "schema_version": "0.2.0",
            "task_public_id": "task-real-1",
            "user_id": "7",
            "project_id": "11",
            "project_version_id": "13",
            "module": "product_design",
            "task_type": "requirement.clarify",
            "target": {"object_type": "requirement", "object_id": "17", "object_version_id": "19"},
            "target_snapshot_hash": "a" * 64,
            "source_ref_ids": ["17"],
            "capability_selection": None,
            "risk_acceptances": [],
            "command_id": "command-real-1",
            "trace_id": "trace-real-1",
            "requested_at": "2026-08-25T00:00:00Z",
            "input": {"mode": mode, "round_no": round_no, "continue_deep_confirmed": False},
            "status": "queued",
        }
    )


def source() -> ClarificationSource:
    return ClarificationSource(
        source_type="requirement_version",
        source_id="17",
        source_version_id="19",
        content_fingerprint="b" * 64,
        label="Requirement Version 19",
        token_count=80,
    )


def dimensions() -> dict:
    return {
        name: {"status": "complete", "reasons": [f"{name} is explicit"], "missing_items": []}
        for name in DIMENSIONS
    }


class JsonProvider:
    def __init__(self, content: object) -> None:
        self.content = content
        self.request = None

    def generate(self, request):
        self.request = request
        return ProviderResponse(
            provider="deepseek",
            model=request.model,
            provider_request_id="provider-request-1",
            content=json.dumps(self.content),
            finish_reason="stop",
            usage=ProviderUsage(
                input_tokens=120,
                output_tokens=80,
                billed_tokens=200,
                estimated_cost="0.000100",
                currency_code="USD",
                cost_source="profile_calculated",
                pricing_version="fixture",
            ),
        )


class RealRequirementClarificationTests(unittest.TestCase):
    def test_real_provider_result_is_candidate_only_traceable_and_human_gated(self) -> None:
        provider = JsonProvider(
            {
                "result_kind": "assessment",
                "dimensions": dimensions(),
                "assessment": {
                    "complexity_band": "medium",
                    "reasons": ["cross-module workflow"],
                    "recommended_mode": "standard",
                    "missing_items": [],
                },
                "questions": [],
                "baseline": None,
                "convergence": {"should_finish": False, "finish_reason": None, "next_round_no": 1},
            }
        )
        execution = RealRequirementClarifier(provider).run(
            task(),
            (source(),),
            requirement_content={"raw_input": "需要一个清晰的审批流程"},
        )

        self.assertEqual(execution.truth_label, "REAL_PROVIDER")
        self.assertFalse(execution.formalization_allowed)
        self.assertEqual(execution.result["status"], "ready")
        self.assertEqual(execution.result["assessment"]["source_refs"][0]["source_id"], "17")
        self.assertEqual(execution.provider_response["provider_request_id"], "provider-request-1")
        self.assertEqual(execution.provider_response["usage"]["estimated_cost"], "0.000100")
        self.assertEqual(provider.request.model, "deepseek-v4-flash")
        self.assertIn("Return only JSON", provider.request.input_text)
        prompt = json.loads(provider.request.input_text)
        self.assertEqual(prompt["output_schema"]["result_kind"], "assessment")
        self.assertEqual(prompt["output_schema"]["questions"], [])
        self.assertIsNone(prompt["output_schema"]["baseline"])

    def test_real_provider_rejects_stage_mismatch_and_more_than_three_questions(self) -> None:
        mismatch = JsonProvider(
            {
                "result_kind": "baseline",
                "dimensions": dimensions(),
                "baseline": None,
                "convergence": {},
            }
        )
        with self.assertRaisesRegex(ProviderMalformedResponse, "result_kind"):
            RealRequirementClarifier(mismatch).run(
                task(), (source(),), requirement_content={"raw_input": "fixture"}
            )

        too_many = JsonProvider(
            {
                "result_kind": "questions",
                "dimensions": dimensions(),
                "questions": [
                    {"question_id": f"q-{index}", "dimension": "goal", "question_text": "question", "reason": "reason"}
                    for index in range(1, 5)
                ],
                "convergence": {},
            }
        )
        with self.assertRaisesRegex(ProviderMalformedResponse, "1 to 3"):
            RealRequirementClarifier(too_many).run(
                task(mode="standard", round_no=1),
                (source(),),
                requirement_content={"raw_input": "fixture"},
            )

    def test_prompt_exposes_only_the_requested_stage_shape(self) -> None:
        assessment = json.loads(
            RealRequirementClarifier._prompt(task(), {"raw_input": "fixture"})
        )["output_schema"]
        questions = json.loads(
            RealRequirementClarifier._prompt(
                task(mode="standard", round_no=1), {"raw_input": "fixture"}
            )
        )["output_schema"]
        baseline = json.loads(
            RealRequirementClarifier._prompt(
                task(mode="skip", round_no=0), {"raw_input": "fixture"}
            )
        )["output_schema"]

        self.assertEqual(assessment["result_kind"], "assessment")
        self.assertEqual(assessment["questions"], [])
        self.assertIsNone(assessment["baseline"])
        self.assertEqual(questions["result_kind"], "questions")
        self.assertIsNone(questions["assessment"])
        self.assertIsNone(questions["baseline"])
        self.assertEqual(baseline["result_kind"], "baseline")
        self.assertIsNone(baseline["assessment"])
        self.assertEqual(baseline["questions"], [])


if __name__ == "__main__":
    unittest.main()
