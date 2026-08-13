from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObjectRef(StrictModel):
    object_type: str = Field(min_length=1, max_length=64)
    object_id: str = Field(pattern=r"^[1-9][0-9]*$")
    object_version_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")


class SourceRef(StrictModel):
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(pattern=r"^[1-9][0-9]*$")
    source_version_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")
    requirement: Literal["required", "optional"]


class CapabilitySelection(StrictModel):
    skill_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
    prompt_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
    template_version_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")
    context_strategy_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
    model_catalog_id: str = Field(pattern=r"^[1-9][0-9]*$")
    provider_profile_id: str = Field(pattern=r"^[1-9][0-9]*$")


class TaskEnvelope(StrictModel):
    task_public_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(pattern=r"^[1-9][0-9]*$")
    project_id: str = Field(pattern=r"^[1-9][0-9]*$")
    project_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
    module: str = Field(min_length=1, max_length=32)
    task_type: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    target: ObjectRef
    target_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_refs: tuple[SourceRef, ...]
    capability_selection: CapabilitySelection | None = None
    risk_acceptances: tuple[dict[str, Any], ...] = ()
    command_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(min_length=1, max_length=64)
    requested_at: datetime
