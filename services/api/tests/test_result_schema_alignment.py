from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from app.modules.ai_tasks.service import _result_view, _safe_validation
from app.platform.sprint2_contract import REQUIREMENT_DIMENSIONS, SPRINT2_SCHEMAS


def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "#/components/schemas/AiResultContent",
            "components": {"schemas": SPRINT2_SCHEMAS},
        }
    )


def _source_ref() -> dict[str, object]:
    return {
        "source_type": "requirement_raw_input",
        "source_id": "source-1",
        "source_version_id": "1",
        "content_hash": "a" * 64,
        "label": "Requirement raw input",
    }


def _dimension() -> dict[str, object]:
    return {
        "status": "complete",
        "reasons": ["The requirement states this fact."],
        "missing_items": [],
        "source_refs": [_source_ref()],
    }


def _dimensions() -> dict[str, object]:
    return {dimension: _dimension() for dimension in REQUIREMENT_DIMENSIONS}


def _baseline() -> dict[str, object]:
    return {
        "dimensions": {
            dimension: {
                "confirmed_facts": ["Confirmed fact"],
                "source_refs": [_source_ref()],
                "deferred_items": [],
                "not_applicable_items": [],
            }
            for dimension in REQUIREMENT_DIMENSIONS
        },
        "assumptions": [],
        "unresolved_items": [],
    }


def _quality() -> dict[str, object]:
    return {
        "format_status": "passed",
        "traceability_status": "passed",
        "safety_status": "passed",
        "major_error": False,
        "blocker_codes": [],
        "required_items_total": 8,
        "required_items_met": 8,
    }


def _valid_result(result_kind: str = "baseline") -> dict[str, object]:
    content: dict[str, object] = {
        "schema_version": "0.2.0",
        "task_public_id": "task-result-schema-parity",
        "task_type": "requirement.clarify",
        "target_snapshot_hash": "b" * 64,
        "mode": "auto",
        "round_no": 0,
        "result_kind": result_kind,
        "status": "ready",
        "dimensions": _dimensions(),
        "assessment": None,
        "questions": [],
        "baseline": None,
        "convergence": {
            "should_finish": True,
            "finish_reason": "no_new_high_value_question",
            "next_round_no": None,
        },
        "quality": _quality(),
    }
    if result_kind == "assessment":
        content["assessment"] = {
            "dimension_completeness": _dimensions(),
            "complexity_band": "low",
            "reasons": ["The requirement is sufficiently complete."],
            "recommended_mode": "auto",
            "missing_items": [],
            "source_refs": [_source_ref()],
        }
    elif result_kind == "questions":
        content["questions"] = [
            {
                "question_id": "q-1",
                "dimension": "goal",
                "question_text": "What outcome is required?",
                "reason": "The outcome needs confirmation.",
                "source_refs": [_source_ref()],
            }
        ]
        content["convergence"] = {
            "should_finish": False,
            "finish_reason": None,
            "next_round_no": 1,
        }
    else:
        content["baseline"] = _baseline()
    return content


def _assert_invalid(content: dict[str, object]) -> None:
    assert list(_validator().iter_errors(content))


def test_authoritative_result_content_passes_backend_and_safe_projection() -> None:
    content = _valid_result()
    _safe_validation(content, _validator(), "AI result content is invalid")

    view = _result_view(
        {
            "id": 1,
            "task_public_id": content["task_public_id"],
            "status": "ready",
            "target_snapshot_hash": content["target_snapshot_hash"],
            "content_summary": "Safe summary",
        },
        content,
    )

    assert view["content_json"] == content
    assert view["quality_summary"] == content["quality"]
    assert view["convergence"] == content["convergence"]
    assert "content_ref" not in view


@pytest.mark.parametrize("result_kind", ["assessment", "questions", "baseline"])
def test_each_authoritative_result_kind_invariant_passes(result_kind: str) -> None:
    _validator().validate(_valid_result(result_kind))


@pytest.mark.parametrize(
    ("result_kind", "mutation"),
    [
        ("baseline", "missing_quality"),
        ("baseline", "additional_property"),
        ("assessment", "missing_assessment"),
        ("questions", "missing_questions"),
        ("baseline", "missing_baseline"),
    ],
)
def test_required_additional_and_result_kind_invariants_fail(
    result_kind: str, mutation: str
) -> None:
    content = _valid_result(result_kind)
    if mutation == "missing_quality":
        content.pop("quality")
    elif mutation == "additional_property":
        content["unexpected"] = True
    elif mutation == "missing_assessment":
        content["assessment"] = None
    elif mutation == "missing_questions":
        content["questions"] = []
    else:
        content["baseline"] = None
    _assert_invalid(content)


def test_authoritative_field_families_and_source_ref_objects_are_enforced() -> None:
    obsolete_dimension = _valid_result()
    obsolete_dimension["dimensions"]["goal"] = {
        "status": "complete",
        "missing_items": [],
        "source_refs": ["source-1"],
    }
    _assert_invalid(obsolete_dimension)

    obsolete_assessment = _valid_result("assessment")
    obsolete_assessment["assessment"] = {
        "dimensions": _dimensions(),
        "complexity_band": "low",
        "complexity_reason": "Legacy field",
        "recommended_mode": "auto",
        "missing_items": [],
        "source_refs": [_source_ref()],
    }
    _assert_invalid(obsolete_assessment)

    obsolete_quality = _valid_result()
    obsolete_quality["quality"] = {
        "structure": "passed",
        "traceability": "passed",
        "security": "passed",
        "major_error": False,
        "blocker_codes": [],
    }
    _assert_invalid(obsolete_quality)


def test_question_and_convergence_constraints_match_authoritative_schema() -> None:
    bad_question = _valid_result("questions")
    bad_question["questions"][0]["question_id"] = "q-0"
    _assert_invalid(bad_question)

    bad_next_round = _valid_result("questions")
    bad_next_round["convergence"]["next_round_no"] = 0
    _assert_invalid(bad_next_round)

    contradictory_finish = _valid_result("questions")
    contradictory_finish["convergence"]["finish_reason"] = "round_limit"
    _assert_invalid(contradictory_finish)


def test_committed_semantic_mapping_matches_authoritative_result_contract() -> None:
    content = SPRINT2_SCHEMAS["AiResultContent"]
    dimension = SPRINT2_SCHEMAS["AiResultDimension"]
    assessment = SPRINT2_SCHEMAS["AiResultAssessment"]
    quality = SPRINT2_SCHEMAS["AiResultQuality"]

    assert "oneOf" not in content
    assert len(content["allOf"]) == 5
    assert set(content["required"]) == {
        "schema_version", "task_public_id", "task_type", "target_snapshot_hash", "mode",
        "round_no", "result_kind", "status", "dimensions", "assessment", "questions",
        "baseline", "convergence", "quality",
    }
    assert set(dimension["required"]) == {"status", "reasons", "missing_items", "source_refs"}
    assert dimension["properties"]["source_refs"]["items"] == {"$ref": "#/components/schemas/SourceRef"}
    assert set(assessment["required"]) == {
        "dimension_completeness", "complexity_band", "reasons", "recommended_mode",
        "missing_items", "source_refs",
    }
    assert set(quality["required"]) == {
        "format_status", "traceability_status", "safety_status", "major_error",
        "blocker_codes", "required_items_total", "required_items_met",
    }
    question = content["properties"]["questions"]["items"]
    assert question["properties"]["question_id"]["pattern"] == "^q-[1-9][0-9]*$"
    assert question["properties"]["source_refs"]["items"] == {"$ref": "#/components/schemas/SourceRef"}
