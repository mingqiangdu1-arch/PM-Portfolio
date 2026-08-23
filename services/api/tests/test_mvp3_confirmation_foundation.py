from __future__ import annotations

from datetime import datetime, timezone

from app.modules.confirmation.domain import (
    ConfirmationDecisionStatus,
    ConfirmationRound,
    ConfirmationState,
    ConfirmationStatus,
    ImplementationPlan,
    ImplementationPlanStatus,
    ImplementationPlanVersion,
)


def test_foundation_mapping_exposes_frozen_plan_version_round_fields() -> None:
    version = ImplementationPlanVersion(
        id=2,
        implementation_plan_id=1,
        source_version_id=None,
        version_no="V1",
        review_id=3,
        content_json={"schema_version": "implementation_plan.mvp3.v1"},
        content_hash="a" * 64,
        change_note="initial",
        is_effective=True,
        effective_owner_key=1,
        created_by=9,
        created_at=datetime.now(timezone.utc),
    )
    plan = ImplementationPlan(
        id=1,
        project_version_id=10,
        source_prd_version_id=11,
        source_design_review_id=12,
        name="Plan",
        status=ImplementationPlanStatus.ACTIVE,
        current_version_id=2,
        effective_version_id=2,
        row_version=2,
        confirmation_state=ConfirmationState.NEEDS_CONFIRMATION,
        versions=(version,),
    )
    round_ = ConfirmationRound(
        id=4,
        implementation_plan_id=1,
        plan_version_id=2,
        source_round_id=None,
        round_no=1,
        status=ConfirmationStatus.DRAFT,
        confirm_status=None,
        implementation_summary="A sufficiently detailed implementation scope.",
        readiness_json={"schema_version": "implementation_confirmation.readiness.mvp3.v1"},
        row_version=1,
        is_effective=False,
        effective_plan_key=None,
        draft_plan_key=1,
        confirmed_by=None,
        confirmed_at=None,
        superseded_at=None,
    )
    assert plan.versions == (version,)
    assert round_.status is ConfirmationStatus.DRAFT
    assert round_.confirm_status is None
    assert version.effective_owner_key == 1
    assert round_.effective_plan_key is None
    assert round_.draft_plan_key == 1
    assert ConfirmationDecisionStatus.CONFIRMED.value == "confirmed"
