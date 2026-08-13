from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_public_id: str
    project_id: str = Field(pattern=r"^[1-9][0-9]*$")
    project_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
    requested_source_ids: tuple[str, ...]
    token_budget: int = Field(gt=0)


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_type: str
    source_id: str
    source_version_id: str | None
    role: Literal["authoritative", "user_asserted", "advisory", "historical", "candidate"]
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_summary: str
    token_count: int = Field(ge=0)


class ContextSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_public_id: str
    injected: tuple[ContextItem, ...]
    excluded_source_ids: tuple[str, ...]
    total_tokens: int = Field(ge=0)


class ContextProvider(Protocol):
    def get_snapshot(self, request: ContextRequest) -> ContextSnapshot: ...
