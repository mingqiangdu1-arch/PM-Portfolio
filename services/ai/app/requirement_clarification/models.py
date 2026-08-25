from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.task_state import TaskStatus


Mode = Literal["auto", "standard", "deep", "skip"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RequirementTarget(StrictModel):
    object_type: Literal["requirement"]
    object_id: str = Field(pattern=r"^[1-9][0-9]*$")
    object_version_id: str = Field(pattern=r"^[1-9][0-9]*$")


class ClarificationInput(StrictModel):
    mode: Mode
    round_no: int = Field(ge=0, le=5)
    continue_deep_confirmed: bool

    @model_validator(mode="after")
    def validate_round(self) -> "ClarificationInput":
        if self.mode in {"auto", "skip"}:
            if self.round_no != 0 or self.continue_deep_confirmed:
                raise ValueError("auto/skip require round 0 without deep confirmation")
        elif self.mode == "standard":
            if not 1 <= self.round_no <= 3 or self.continue_deep_confirmed:
                raise ValueError("standard requires rounds 1-3 without deep confirmation")
        elif not 1 <= self.round_no <= 5:
            raise ValueError("deep requires rounds 1-5")
        elif self.round_no >= 4 and not self.continue_deep_confirmed:
            raise ValueError("deep rounds 4-5 require explicit confirmation")
        return self


class RiskAcceptance(StrictModel):
    risk_id: str = Field(min_length=1, max_length=128)
    impact: Literal["low", "medium"]
    accepted: Literal[True]


class RequirementClarifyTask(StrictModel):
    schema_version: Literal["0.2.0"]
    task_public_id: str = Field(min_length=1, max_length=64)
    retry_of_task_id: str | None = Field(default=None, min_length=1, max_length=64)
    user_id: str = Field(pattern=r"^[1-9][0-9]*$")
    project_id: str = Field(pattern=r"^[1-9][0-9]*$")
    project_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
    module: Literal["product_design"]
    task_type: Literal["requirement.clarify"]
    target: RequirementTarget
    target_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_ref_ids: tuple[str, ...] = Field(min_length=1)
    capability_selection: dict[str, Any] | None
    risk_acceptances: tuple[RiskAcceptance, ...]
    command_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(min_length=1, max_length=64)
    requested_at: datetime
    input: ClarificationInput
    status: TaskStatus
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_code: str | None = Field(default=None, max_length=64)


class ClarificationSource(StrictModel):
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    source_version_id: str | None = Field(default=None, min_length=1, max_length=128)
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    label: str = Field(min_length=1, max_length=256)
    token_count: int = Field(ge=0)
    was_injected: bool = True
    exclusion_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_injection(self) -> "ClarificationSource":
        if self.was_injected and self.exclusion_reason is not None:
            raise ValueError("injected sources cannot have an exclusion reason")
        if not self.was_injected and self.exclusion_reason is None:
            raise ValueError("excluded sources require an exclusion reason")
        return self


class ManualRecovery(StrictModel):
    failure_code: Literal["DEPENDENCY_UNAVAILABLE", "TRACEABILITY_INCOMPLETE"]
    finish_reason: Literal["ai_unavailable_manual"]
    actions: tuple[
        Literal["manual_input", "manual_clarification", "manual_baseline", "confirm_after_gate", "retry_ai_task"],
        ...,
    ]
    retryable: bool


class ClarificationExecution(StrictModel):
    truth_label: Literal["FORMAL_MOCK", "REAL_PROVIDER"]
    provider_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(min_length=1, max_length=64)
    command_id: str = Field(min_length=1, max_length=64)
    task_statuses: tuple[TaskStatus, ...]
    result: dict[str, Any]
    context_snapshot: dict[str, Any]
    recovery: ManualRecovery | None
    formalization_allowed: Literal[False] = False
    provider_response: dict[str, Any] | None = None
