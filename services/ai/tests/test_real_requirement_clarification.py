from __future__ import annotations

import json

import unittest

from jsonschema import Draft202012Validator

from app.providers.base import (
    MalformedResponseSubtype,
    ProviderMalformedResponse,
    ProviderResponse,
    ProviderUsage,
)
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
    def __init__(self, content: object, *, raw: bool = False) -> None:
        self.content = content
        self.raw = raw
        self.request = None
        self.call_count = 0

    def generate(self, request):
        self.call_count += 1
        self.request = request
        return ProviderResponse(
            provider="deepseek",
            model=request.model,
            provider_request_id="provider-request-1",
            content=self.content if self.raw else json.dumps(self.content),
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
    @staticmethod
    def questions_candidate(questions: object) -> dict:
        return {
            "result_kind": "questions",
            "dimensions": dimensions(),
            "assessment": None,
            "questions": questions,
            "baseline": None,
            "convergence": {"should_finish": False, "finish_reason": None, "next_round_no": 2},
        }

    def assert_malformed(self, candidate: object, subtype: MalformedResponseSubtype, *, raw: bool = False) -> None:
        with self.assertRaises(ProviderMalformedResponse) as caught:
            RealRequirementClarifier(JsonProvider(candidate, raw=raw)).run(
                task(mode="standard", round_no=1),
                (source(),),
                requirement_content={"raw_input": "fixture"},
            )
        self.assertEqual(caught.exception.subtype, subtype)

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
        self.assertEqual(
            provider.request.response_schema_name,
            "requirement_clarification_candidate",
        )
        self.assertIn("Return only JSON", provider.request.input_text)
        prompt = json.loads(provider.request.input_text)
        self.assertEqual(prompt["output_schema"]["result_kind"], "assessment")
        self.assertEqual(prompt["output_schema"]["questions"], [])
        self.assertIsNone(prompt["output_schema"]["baseline"])
        Draft202012Validator.check_schema(provider.request.response_schema)
        Draft202012Validator(provider.request.response_schema).validate(
            json.loads(provider.content if provider.raw else json.dumps(provider.content))
        )

    def test_real_provider_rejects_stage_mismatch_and_more_than_three_questions(self) -> None:
        mismatch = JsonProvider(
            {
                "result_kind": "baseline",
                "dimensions": dimensions(),
                "assessment": None,
                "questions": [],
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
                "assessment": None,
                "questions": [
                    {"question_id": f"q-{index}", "dimension": "goal", "question_text": "question", "reason": "reason"}
                    for index in range(1, 5)
                ],
                "baseline": None,
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

    def test_response_schema_is_stage_specific_and_exact(self) -> None:
        assessment = RealRequirementClarifier._response_schema(task())
        questions = RealRequirementClarifier._response_schema(
            task(mode="standard", round_no=1)
        )
        baseline = RealRequirementClarifier._response_schema(
            task(mode="standard", round_no=3)
        )
        for schema in (assessment, questions, baseline):
            Draft202012Validator.check_schema(schema)
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(
                set(schema["required"]),
                {"result_kind", "dimensions", "assessment", "questions", "baseline", "convergence"},
            )
        self.assertEqual(assessment["properties"]["result_kind"], {"const": "assessment"})
        self.assertEqual(questions["properties"]["questions"]["minItems"], 1)
        self.assertEqual(questions["properties"]["questions"]["maxItems"], 3)
        self.assertEqual(baseline["properties"]["result_kind"], {"const": "baseline"})
        self.assertEqual(
            baseline["properties"]["convergence"]["properties"]["next_round_no"],
            {"const": None},
        )
        assessment_candidate = {
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
        question_candidate = self.questions_candidate(
            [
                {
                    "question_id": "q-1",
                    "dimension": "goal",
                    "question_text": "需要达成什么结果？",
                    "reason": "目标需要明确。",
                }
            ]
        )
        baseline_candidate = {
            "result_kind": "baseline",
            "dimensions": dimensions(),
            "assessment": None,
            "questions": [],
            "baseline": {
                "dimensions": {
                    key: {
                        "confirmed_facts": [f"{key} is confirmed"],
                        "deferred_items": [],
                        "not_applicable_items": [],
                    }
                    for key in DIMENSIONS
                },
                "assumptions": [],
                "unresolved_items": [],
            },
            "convergence": {
                "should_finish": True,
                "finish_reason": "round_limit",
                "next_round_no": None,
            },
        }
        Draft202012Validator(assessment).validate(assessment_candidate)
        Draft202012Validator(questions).validate(question_candidate)
        Draft202012Validator(baseline).validate(baseline_candidate)
        assessment_candidate["unexpected"] = "blocked"
        self.assertTrue(list(Draft202012Validator(assessment).iter_errors(assessment_candidate)))

    def test_valid_standard_questions_response_passes_and_prompt_is_hardened(self) -> None:
        provider = JsonProvider(
            self.questions_candidate(
                [
                    {
                        "question_id": "q-1",
                        "dimension": "goal",
                        "question_text": "需要达成什么结果？",
                        "reason": "目标需要明确。",
                    }
                ]
            )
        )
        execution = RealRequirementClarifier(provider).run(
            task(mode="standard", round_no=1),
            (source(),),
            requirement_content={"raw_input": "fixture"},
        )
        self.assertEqual(execution.result["result_kind"], "questions")
        self.assertEqual(execution.result["questions"][0]["question_id"], "q-1")
        instruction = json.loads(provider.request.input_text)["instruction"]
        self.assertIn("without Markdown fences", instruction)
        self.assertIn("1 to 3 questions", instruction)
        self.assertIn("q-[1-9][0-9]*", instruction)
        self.assertIn("Simplified Chinese", instruction)
        self.assertIn("never return an English-only question or reason", instruction)
        self.assertIn(
            "Simplified Chinese",
            provider.request.response_schema["description"],
        )

    def test_standard_questions_reject_english_only_human_visible_text(self) -> None:
        english_question = self.questions_candidate(
            [
                {
                    "question_id": "q-1",
                    "dimension": "goal",
                    "question_text": "What measurable outcome should this workflow achieve?",
                    "reason": "The success criteria must be explicit.",
                }
            ]
        )
        with self.assertRaises(ProviderMalformedResponse) as caught:
            RealRequirementClarifier(JsonProvider(english_question)).run(
                task(mode="standard", round_no=1),
                (source(),),
                requirement_content={"raw_input": "fixture"},
            )
        self.assertEqual(
            caught.exception.subtype,
            MalformedResponseSubtype.INVALID_OUTPUT_LANGUAGE,
        )
        self.assertEqual(caught.exception.field, "questions[].question_text")

    def test_standard_questions_validation_subtypes_cover_frozen_contract(self) -> None:
        valid = {
            "question_id": "q-1",
            "dimension": "goal",
            "question_text": "需要确认什么目标？",
            "reason": "目标需要明确。",
        }
        cases = (
            ("not json", MalformedResponseSubtype.INVALID_JSON, True),
            (
                {**self.questions_candidate([valid]), "result_kind": "assessment"},
                MalformedResponseSubtype.WRONG_RESULT_KIND,
                False,
            ),
            (
                {key: value for key, value in self.questions_candidate([valid]).items() if key != "questions"},
                MalformedResponseSubtype.MISSING_QUESTIONS,
                False,
            ),
            (self.questions_candidate([]), MalformedResponseSubtype.INVALID_QUESTION_COUNT, False),
            (self.questions_candidate([valid] * 4), MalformedResponseSubtype.INVALID_QUESTION_COUNT, False),
            (
                self.questions_candidate([{key: value for key, value in valid.items() if key != "question_id"}]),
                MalformedResponseSubtype.MISSING_QUESTION_ID,
                False,
            ),
            (
                self.questions_candidate([valid, valid]),
                MalformedResponseSubtype.DUPLICATE_QUESTION_ID,
                False,
            ),
            (
                self.questions_candidate([{**valid, "dimension": "unknown"}]),
                MalformedResponseSubtype.INVALID_DIMENSION,
                False,
            ),
            (
                self.questions_candidate([{**valid, "question_text": 42}]),
                MalformedResponseSubtype.INVALID_FIELD_TYPE,
                False,
            ),
            (
                self.questions_candidate([{**valid, "extra": "not allowed"}]),
                MalformedResponseSubtype.INVALID_QUESTION_SHAPE,
                False,
            ),
        )
        for candidate, subtype, raw in cases:
            with self.subTest(subtype=subtype):
                self.assert_malformed(candidate, subtype, raw=raw)

    def test_standard_questions_accepts_only_deterministic_json_normalization(self) -> None:
        candidate = self.questions_candidate(
            [
                {
                    "question_id": " q-1 ",
                    "dimension": "goal",
                    "question_text": " 需要确认什么目标？ ",
                    "reason": " 目标需要明确。 ",
                }
            ]
        )
        raw = f"  \n{json.dumps(candidate)}\n  "
        execution = RealRequirementClarifier(JsonProvider(raw, raw=True)).run(
            task(mode="standard", round_no=1),
            (source(),),
            requirement_content={"raw_input": "fixture"},
        )
        self.assertEqual(execution.result["questions"][0]["question_id"], "q-1")
        fenced = RealRequirementClarifier(JsonProvider(
            f"```json\n{json.dumps(candidate)}\n```",
            raw=True,
        )).run(
            task(mode="standard", round_no=1),
            (source(),),
            requirement_content={"raw_input": "fixture"},
        )
        self.assertEqual(fenced.result["questions"][0]["question_id"], "q-1")

    def test_standard_questions_fail_closed_for_ambiguous_or_malformed_envelopes(self) -> None:
        candidate = self.questions_candidate(
            [{
                "question_id": "q-1",
                "dimension": "goal",
                "question_text": "需要确认什么目标？",
                "reason": "目标需要明确。",
            }]
        )
        raw_candidate = json.dumps(candidate, ensure_ascii=False)
        cases = (
            (
                f"说明：{raw_candidate}\n补充：{raw_candidate}",
                "single_output_text:ambiguous_multiple_json_objects",
            ),
            (
                f"说明：{raw_candidate}",
                "single_output_text:prose_wrapped_single_json_object",
            ),
            (
                '{"result_kind":"questions"',
                "single_output_text:json_syntax_malformed",
            ),
            (
                f"```\n{raw_candidate}\n```",
                "single_output_text:unsupported_or_malformed_fence",
            ),
        )
        for raw, rule in cases:
            provider = JsonProvider(raw, raw=True)
            with self.subTest(rule=rule), self.assertRaises(ProviderMalformedResponse) as caught:
                RealRequirementClarifier(provider).run(
                    task(mode="standard", round_no=1),
                    (source(),),
                    requirement_content={"raw_input": "fixture"},
                )
            self.assertEqual(caught.exception.subtype, MalformedResponseSubtype.INVALID_JSON)
            self.assertEqual(caught.exception.field, "content")
            self.assertEqual(caught.exception.rule, rule)
            self.assertNotIn("说明", str(caught.exception))
            self.assertEqual(provider.call_count, 1)

    def test_semantic_contract_failure_does_not_retry_provider(self) -> None:
        provider = JsonProvider({"result_kind": "questions"})
        with self.assertRaises(ProviderMalformedResponse) as caught:
            RealRequirementClarifier(provider).run(
                task(mode="standard", round_no=1),
                (source(),),
                requirement_content={"raw_input": "fixture"},
            )
        self.assertEqual(caught.exception.subtype, MalformedResponseSubtype.MISSING_QUESTIONS)
        self.assertEqual(provider.call_count, 1)


if __name__ == "__main__":
    unittest.main()
