from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiResponse(ApiModel, Generic[T]):
    code: str
    message: str
    data: T
    trace_id: str


class FieldError(ApiModel):
    field: str | None = None
    reason: str


class ErrorResponse(ApiModel):
    code: str
    message: str
    details: list[FieldError] = Field(default_factory=list)
    trace_id: str


class CursorPage(ApiModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool


class HealthData(ApiModel):
    status: str
    service: str
    release: str
    environment: str


class VersionedCommand(ApiModel):
    expected_version: int = Field(ge=1)
