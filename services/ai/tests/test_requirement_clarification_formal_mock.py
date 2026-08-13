import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from app.domain.task_state import TaskStatus, transition
from app.requirement_clarification import (
    ClarificationSource,
    FormalMockRequirementClarifier,
    RequirementClarifyTask,
)


AI_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = AI_ROOT / "schemas" / "v0.2"


def schema_validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def task(
    mode: str = "auto",
    round_no: int = 0,
    *,
    confirmed: bool = False,
    task_id: str = "task-requirement-1",
) -> RequirementClarifyTask:
    return RequirementClarifyTask.model_validate(
        {
            "schema_version": "0.2.0",
            "task_public_id": task_id,
            "user_id": "7",
            "project_id": "11",
            "project_version_id": "13",
            "module": "product_design",
            "task_type": "requirement.clarify",
            "target": {"object_type": "requirement", "object_id": "17", "object_version_id": "19"},
            "target_snapshot_hash": "a" * 64,
            "source_ref_ids": ["requirement-version:19"],
            "capability_selection": None,
            "risk_acceptances": [],
            "command_id": "command-requirement-1",
            "trace_id": "trace-requirement-1",
            "requested_at": "2026-08-08T15:00:00Z",
            "input": {"mode": mode, "round_no": round_no, "continue_deep_confirmed": confirmed},
            "status": "queued",
        }
    )


def source(*, injected: bool = True) -> ClarificationSource:
    return ClarificationSource(
        source_type="requirement_version",
        source_id="requirement-version:19",
        source_version_id="19",
        content_fingerprint="b" * 64,
        label="Requirement Version 19",
        token_count=240 if injected else 0,
        was_injected=injected,
        exclusion_reason=None if injected else "not_selected",
    )


def assert_contracts(execution) -> None:
    schema_validator("requirement-clarify-result-content.schema.json").validate(execution.result)
    schema_validator("context-snapshot-0.2.schema.json").validate(execution.context_snapshot)
    for source_status, target_status in zip(execution.task_statuses, execution.task_statuses[1:]):
        transition(source_status, target_status)


def test_formal_mock_is_explicit_deterministic_traceable_and_never_formalizes() -> None:
    clarifier = FormalMockRequirementClarifier()
    first = clarifier.run(task(), (source(),))
    second = clarifier.run(task(), (source(),))
    assert first == second
    assert first.truth_label == "FORMAL_MOCK"
    assert first.provider_id == "requirement-clarify-formal-mock"
    assert first.trace_id == "trace-requirement-1"
    assert first.command_id == "command-requirement-1"
    assert first.formalization_allowed is False
    assert first.result["result_kind"] == "assessment"
    assert first.result["quality"]["required_items_total"] == 8
    assert first.result["quality"]["required_items_met"] == 3
    assert first.result["task_public_id"] == task().task_public_id
    assert first.result["target_snapshot_hash"] == task().target_snapshot_hash
    assert first.task_statuses[-1] is TaskStatus.READY
    assert first.context_snapshot["token_count"] == 240
    assert_contracts(first)


@pytest.mark.parametrize(
    ("mode", "round_no", "confirmed", "kind", "finish_reason"),
    [
        ("standard", 1, False, "questions", None),
        ("standard", 3, False, "baseline", "round_limit"),
        ("deep", 4, True, "questions", None),
        ("deep", 5, True, "baseline", "round_limit"),
        ("skip", 0, False, "baseline", "mode_skipped"),
    ],
)
def test_modes_round_limits_result_kinds_and_convergence(mode, round_no, confirmed, kind, finish_reason) -> None:
    execution = FormalMockRequirementClarifier().run(
        task(mode, round_no, confirmed=confirmed),
        (source(),),
    )
    assert execution.result["result_kind"] == kind
    assert execution.result["convergence"]["finish_reason"] == finish_reason
    if kind == "questions":
        assert 1 <= len(execution.result["questions"]) <= 3
        assert execution.result["convergence"]["next_round_no"] == round_no + 1
        assert execution.result["quality"]["required_items_total"] == 8
        assert execution.result["quality"]["required_items_met"] == 3
    else:
        assert set(execution.result["baseline"]["dimensions"]) == {
            "goal", "users_and_roles", "usage_scenarios", "functional_scope",
            "business_rules", "exception_cases", "permission_requirements", "acceptance_criteria",
        }
        assert execution.result["quality"]["required_items_total"] == 8
        assert execution.result["quality"]["required_items_met"] == 8
        assert execution.result["baseline"]["dimensions"]["business_rules"]["deferred_items"]
        assert execution.result["baseline"]["dimensions"]["acceptance_criteria"]["deferred_items"]
        assert execution.result["baseline"]["unresolved_items"]
    assert execution.truth_label == "FORMAL_MOCK"
    assert_contracts(execution)


def test_question_count_can_be_one_two_or_three_and_remains_deterministic() -> None:
    clarifier = FormalMockRequirementClarifier()
    counts = {
        len(clarifier.run(task("standard", 1, task_id=f"task-{index}"), (source(),)).result["questions"])
        for index in range(30)
    }
    assert counts == {1, 2, 3}


@pytest.mark.parametrize(
    ("mode", "round_no", "confirmed"),
    [("standard", 4, False), ("deep", 4, False), ("deep", 5, False), ("deep", 6, True), ("auto", 1, False)],
)
def test_invalid_rounds_and_missing_deep_confirmation_are_rejected(mode, round_no, confirmed) -> None:
    with pytest.raises(ValidationError):
        task(mode, round_no, confirmed=confirmed)


@pytest.mark.parametrize("failure_mode", ["rate_limited", "timeout", "unavailable"])
def test_provider_failure_returns_formal_manual_recovery_without_false_success(failure_mode) -> None:
    execution = FormalMockRequirementClarifier(failure_mode=failure_mode).run(task(), (source(),))
    assert execution.truth_label == "FORMAL_MOCK"
    assert execution.task_statuses[-1] is TaskStatus.FAILED
    assert execution.result["status"] == "failed"
    assert execution.result["convergence"] == {
        "should_finish": True,
        "finish_reason": "ai_unavailable_manual",
        "next_round_no": None,
    }
    assert execution.recovery is not None
    assert execution.recovery.failure_code == "DEPENDENCY_UNAVAILABLE"
    assert {"manual_input", "manual_clarification", "manual_baseline", "confirm_after_gate"}.issubset(
        execution.recovery.actions
    )
    assert execution.formalization_allowed is False
    assert_contracts(execution)


def test_missing_or_excluded_context_is_quality_blocked_and_manually_recoverable() -> None:
    for sources in ((), (source(injected=False),)):
        execution = FormalMockRequirementClarifier().run(task(), sources)
        assert execution.task_statuses[-1] is TaskStatus.QUALITY_BLOCKED
        assert execution.result["status"] == "quality_blocked"
        assert execution.result["quality"]["traceability_status"] == "failed"
        assert execution.result["quality"]["blocker_codes"] == ["TRACEABILITY_INCOMPLETE"]
        assert execution.recovery is not None
        assert execution.recovery.failure_code == "TRACEABILITY_INCOMPLETE"
        assert_contracts(execution)


def test_task_model_matches_frozen_envelope_and_result_avoids_technical_design_content() -> None:
    task_payload = task("standard", 1).model_dump(mode="json", exclude_none=True)
    task_payload["capability_selection"] = None
    schema_validator("requirement-clarify-task-envelope.schema.json").validate(task_payload)
    execution = FormalMockRequirementClarifier().run(task("standard", 3), (source(),))
    rendered = json.dumps(execution.result, ensure_ascii=False).lower()
    for forbidden in ("database", "endpoint", "api字段", "ui组件"):
        assert forbidden not in rendered
    source_ref = execution.result["baseline"]["dimensions"]["goal"]["source_refs"][0]
    assert source_ref == {
        "source_type": "requirement_version",
        "source_id": "requirement-version:19",
        "source_version_id": "19",
        "content_hash": "b" * 64,
        "label": "Requirement Version 19",
    }
