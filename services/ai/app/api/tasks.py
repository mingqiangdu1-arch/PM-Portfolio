from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.config import Settings
from app.security import ServiceJwtError, ServiceJwtVerifier, ServicePrincipal
from app.tasking.repository import IdempotencyConflict, TaskRecord

router = APIRouter(prefix="/internal/v1/ai/tasks", tags=["ai-tasks"])
_repository = None
_queue = None

def configure_task_dependencies(*, repository=None, queue=None) -> None:
    global _repository, _queue
    _repository = repository
    _queue = queue

class Strict(BaseModel): model_config = ConfigDict(extra="forbid")
class Target(Strict): object_type: Literal["requirement"]; object_id: str = Field(pattern=r"^[1-9][0-9]*$"); object_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
class Input(Strict):
    mode: Literal["auto", "standard", "deep", "skip"]; round_no: int = Field(ge=0, le=5); continue_deep_confirmed: bool
    @model_validator(mode="after")
    def check(self) -> "Input":
        if self.mode in {"auto", "skip"} and (self.round_no != 0 or self.continue_deep_confirmed): raise ValueError("auto/skip combination invalid")
        if self.mode == "standard" and (not 1 <= self.round_no <= 3 or self.continue_deep_confirmed): raise ValueError("standard combination invalid")
        if self.mode == "deep" and not 1 <= self.round_no <= 5: raise ValueError("deep round must be between 1 and 5")
        if self.mode == "deep" and self.round_no >= 4 and not self.continue_deep_confirmed: raise ValueError("deep rounds 4-5 require confirmation")
        return self
class RiskAcceptance(Strict):
    risk_id: str = Field(min_length=1, max_length=128)
    impact: Literal["low", "medium"]
    accepted: Literal[True]
class ResultRef(Strict):
    ai_result_id: str = Field(pattern=r"^[1-9][0-9]*$")
    ai_call_id: str = Field(pattern=r"^[1-9][0-9]*$")
    result_no: int = Field(ge=1)
    status: Literal["ready", "partial_result", "quality_blocked", "failed", "expired", "stale_target"]
    target_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_ref: str = Field(min_length=1)
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
class InternalTaskResponse(Strict):
    task_public_id: str
    status: Literal["prechecking", "blocked", "queued", "preparing", "generating", "checking", "ready", "partial_result", "quality_blocked", "cancel_requested", "cancelled", "failed", "expired", "stale_target"]
    trace_id: str
    failure_code: str | None
    result_refs: list[ResultRef]
class TaskEnvelope(Strict):
    schema_version: Literal["0.2.0"]; task_public_id: str = Field(min_length=1, max_length=64); user_id: str = Field(pattern=r"^[1-9][0-9]*$"); project_id: str = Field(pattern=r"^[1-9][0-9]*$"); project_version_id: str = Field(pattern=r"^[1-9][0-9]*$"); module: Literal["product_design"]; task_type: Literal["requirement.clarify"]; target: Target; target_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$"); source_ref_ids: tuple[str, ...] = Field(min_length=1); capability_selection: None; risk_acceptances: tuple[RiskAcceptance, ...]; command_id: str = Field(min_length=1, max_length=64); trace_id: str = Field(min_length=1, max_length=64); requested_at: datetime; input: Input; status: Literal["queued"] = "queued"
    @model_validator(mode="after")
    def unique_sources(self) -> "TaskEnvelope":
        if len(set(self.source_ref_ids)) != len(self.source_ref_ids): raise ValueError("source_ref_ids must be unique")
        return self

def _principal(authorization: str | None, scope: str) -> ServicePrincipal:
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401, "SERVICE_TOKEN_REQUIRED")
    settings = Settings.from_env()
    if not settings.internal_jwt_secret: raise HTTPException(503, "SERVICE_AUTH_NOT_CONFIGURED")
    verifier = ServiceJwtVerifier(secret=settings.internal_jwt_secret, audience="ai-api", allowed_issuers={"business-api"})
    try: return verifier.verify(authorization.removeprefix("Bearer "), required_scopes={scope})
    except ServiceJwtError as exc: raise HTTPException(exc.status_code, exc.code) from exc

def write_principal(authorization: str | None = Header(default=None)) -> ServicePrincipal: return _principal(authorization, "ai.task:write")
def read_principal(authorization: str | None = Header(default=None)) -> ServicePrincipal: return _principal(authorization, "ai.task:read")

@router.post("", status_code=202)
def submit_task(envelope: TaskEnvelope, principal: ServicePrincipal = Depends(write_principal)) -> dict[str, Any]:
    if principal.task_id != envelope.task_public_id: raise HTTPException(403, "SERVICE_TASK_SCOPE_FORBIDDEN")
    if principal.trace_id != envelope.trace_id: raise HTTPException(403, "TRACE_SCOPE_FORBIDDEN")
    task = TaskRecord(envelope.task_public_id, envelope.user_id, envelope.project_id, envelope.project_version_id, envelope.target.object_id, envelope.target.object_version_id, envelope.target_snapshot_hash, envelope.command_id, envelope.trace_id)
    if _repository is None: raise HTTPException(503, "AI_DATABASE_NOT_CONFIGURED")
    existing = _repository.get_task(task.task_public_id)
    try: saved = _repository.create_task(task)
    except IdempotencyConflict as exc: raise HTTPException(409, "TASK_IDEMPOTENCY_CONFLICT") from exc
    if _queue is None:
        raise HTTPException(503, "AI_QUEUE_NOT_CONFIGURED")
    if existing is None:
        try:
            _queue.ensure_available()
            _queue.enqueue(saved.task_public_id, saved.trace_id)
        except Exception as exc:
            try:
                if hasattr(_repository, "mark_status_with_event"):
                    _repository.mark_status_with_event(saved.task_public_id, "failed", failure_code="dispatch_failed_after_durable_create")
                else:
                    _repository.update_status(saved.task_public_id, "failed", failure_code="dispatch_failed_after_durable_create")
            except Exception: pass
            raise HTTPException(503, "AI_QUEUE_UNAVAILABLE") from exc
    return {"task_public_id": saved.task_public_id, "status": saved.status, "trace_id": saved.trace_id}

@router.get("/{task_public_id}", response_model=InternalTaskResponse)
def get_task(task_public_id: str, principal: ServicePrincipal = Depends(read_principal)) -> dict[str, Any]:
    if _repository is None: raise HTTPException(503, "AI_DATABASE_NOT_CONFIGURED")
    task = _repository.get_task(task_public_id)
    if task is None: raise HTTPException(404, "AI_TASK_NOT_FOUND")
    if principal.task_id != task_public_id: raise HTTPException(403, "SERVICE_TASK_SCOPE_FORBIDDEN")
    if principal.trace_id != task.trace_id: raise HTTPException(403, "TRACE_SCOPE_FORBIDDEN")
    return {"task_public_id": task.task_public_id, "status": task.status, "trace_id": task.trace_id, "failure_code": task.failure_code, "result_refs": _repository.list_result_refs(task_public_id)}
