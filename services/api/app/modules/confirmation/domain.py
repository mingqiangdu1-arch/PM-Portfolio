"""MVP3 foundation/domain mapping only.

These immutable value mappings describe the persisted fields and frozen status
vocabulary.  They intentionally contain no service commands or lifecycle
transitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class ImplementationPlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"


class ConfirmationStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class ConfirmationDecisionStatus(StrEnum):
    CONFIRMED = "confirmed"


class ConfirmationState(StrEnum):
    NOT_READY = "not_ready"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONFIRMED = "confirmed"
    NEEDS_RECONFIRMATION = "needs_reconfirmation"


@dataclass(frozen=True, slots=True)
class ImplementationPlanVersion:
    id: int
    implementation_plan_id: int
    source_version_id: int | None
    version_no: str
    review_id: int
    content_json: dict[str, Any]
    content_hash: str
    change_note: str
    is_effective: bool
    effective_owner_key: int | None
    created_by: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImplementationPlan:
    id: int
    project_version_id: int
    source_prd_version_id: int
    source_design_review_id: int
    name: str
    status: ImplementationPlanStatus
    current_version_id: int | None
    effective_version_id: int | None
    row_version: int
    confirmation_state: ConfirmationState
    versions: tuple[ImplementationPlanVersion, ...]


@dataclass(frozen=True, slots=True)
class ConfirmationRound:
    id: int
    implementation_plan_id: int
    plan_version_id: int
    source_round_id: int | None
    round_no: int
    status: ConfirmationStatus
    confirm_status: ConfirmationDecisionStatus | None
    implementation_summary: str
    readiness_json: dict[str, Any]
    row_version: int
    is_effective: bool
    effective_plan_key: int | None
    draft_plan_key: int | None
    confirmed_by: int | None
    confirmed_at: datetime | None
    superseded_at: datetime | None
