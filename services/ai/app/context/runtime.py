from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
class RuntimeTarget(_Strict):
    object_type: Literal["requirement"]
    object_id: str = Field(pattern=r"^[1-9][0-9]*$")
    object_version_id: str = Field(pattern=r"^[1-9][0-9]*$")
class RuntimeInput(_Strict):
    mode: Literal["auto", "standard", "deep", "skip"]
    round_no: int = Field(ge=0, le=5)
    continue_deep_confirmed: bool
class RuntimeRiskAcceptance(_Strict):
    risk_id: str = Field(min_length=1, max_length=128)
    impact: Literal["low", "medium"]
    accepted: Literal[True]
class P1RuntimeContextResponse(_Strict):
    contract_version: Literal["p1-runtime-context.v1"]
    task_public_id: str = Field(min_length=1, max_length=64)
    target: RuntimeTarget
    target_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input: RuntimeInput
    source_ref_ids: tuple[str, ...] = Field(min_length=1, max_length=1)
    risk_acceptances: tuple[RuntimeRiskAcceptance, ...]
    requirement_content: dict[str, Any]
    @model_validator(mode="after")
    def validate_source_and_input(self) -> "P1RuntimeContextResponse":
        raw_ref, raw_input = self.requirement_content.get("raw_input_ref"), self.requirement_content.get("raw_input")
        if not isinstance(raw_ref, dict) or not isinstance(raw_input, str): raise ValueError("requirement_content must contain raw_input and raw_input_ref")
        if raw_ref.get("source_id") != self.source_ref_ids[0]: raise ValueError("source_ref_ids must match raw_input_ref.source_id")
        if raw_ref.get("content_hash") != sha256(raw_input.encode("utf-8")).hexdigest(): raise ValueError("raw_input_ref.content_hash does not match raw_input")
        clarification = self.requirement_content.get("clarification")
        if not isinstance(clarification, dict) or clarification.get("mode") != self.input.mode: raise ValueError("input.mode is not derived from requirement clarification")
        saved = clarification.get("continue_deep_confirmed", False)
        if not isinstance(saved, bool) or saved != self.input.continue_deep_confirmed: raise ValueError("continue_deep_confirmed must be a saved boolean")
        if self.input.mode in {"auto", "skip"} and (self.input.round_no != 0 or self.input.continue_deep_confirmed): raise ValueError("auto/skip combination invalid")
        if self.input.mode == "standard" and (not 1 <= self.input.round_no <= 3 or self.input.continue_deep_confirmed): raise ValueError("standard combination invalid")
        if self.input.mode == "deep" and (self.input.round_no < 1 or self.input.round_no > 5 or (self.input.round_no >= 4 and not self.input.continue_deep_confirmed)): raise ValueError("deep combination invalid")
        return self

class P1TargetFreshnessResponse(_Strict):
    fresh: bool
    current_snapshot_hash: str = Field(max_length=64)
    current_version_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")

def validate_runtime_context(payload: dict[str, Any], *, task_public_id: str, target_snapshot_hash: str, target_object_type: str | None = None, target_object_id: str | None = None, target_object_version_id: str | None = None) -> P1RuntimeContextResponse:
    response = P1RuntimeContextResponse.model_validate(payload)
    if response.task_public_id != task_public_id: raise ValueError("context task does not match worker task")
    if response.target_snapshot_hash != target_snapshot_hash: raise ValueError("context target hash does not match task")
    if target_object_type is not None and response.target.object_type != target_object_type: raise ValueError("context target type does not match task")
    if target_object_id is not None and response.target.object_id != target_object_id: raise ValueError("context target id does not match task")
    if target_object_version_id is not None and response.target.object_version_id != target_object_version_id: raise ValueError("context target version does not match task")
    schema_path = Path(__file__).parents[2] / "schemas" / "v0.2" / "requirement-content.schema.json"
    from jsonschema import Draft202012Validator, FormatChecker
    try: schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc: raise ValueError("frozen RequirementContent schema unavailable") from exc
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(response.requirement_content)
    return response

def validate_freshness_response(payload: dict[str, Any], *, target_snapshot_hash: str, target_object_version_id: str) -> P1TargetFreshnessResponse:
    response = P1TargetFreshnessResponse.model_validate(payload)
    if response.current_snapshot_hash and not __import__("re").fullmatch(r"[a-f0-9]{64}", response.current_snapshot_hash):
        raise ValueError("current target hash is invalid")
    if response.fresh and response.current_snapshot_hash != target_snapshot_hash:
        raise ValueError("fresh target hash does not match task")
    if response.fresh and response.current_version_id != target_object_version_id:
        raise ValueError("fresh target version does not match task")
    return response

class BusinessContextClient:
    def __init__(self, *, base_url: str, token: str | Any, transport: httpx.BaseTransport | None = None, timeout: float = 5.0): self.base_url, self.token, self.transport, self.timeout = base_url.rstrip("/"), token, transport, timeout
    def context_snapshot(self, task_public_id: str, *, trace_id: str, token_budget: int) -> dict[str, Any]:
        if not 1 <= token_budget <= 200000: raise ValueError("token_budget must be between 1 and 200000")
        return self._post(f"/internal/v1/ai/tasks/{task_public_id}/context-snapshot", task_public_id, trace_id, {"token_budget": token_budget})
    def target_freshness(self, task_public_id: str, *, trace_id: str, target_snapshot_hash: str) -> dict[str, Any]: return self._post(f"/internal/v1/ai/tasks/{task_public_id}/target-freshness", task_public_id, trace_id, {"target_snapshot_hash": target_snapshot_hash})
    def _post(self, path: str, task_public_id: str, trace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        token = self.token(task_public_id, trace_id) if callable(self.token) else self.token
        with httpx.Client(base_url=self.base_url, timeout=self.timeout, transport=self.transport) as client: response = client.post(path, json=body, headers={"Authorization": f"Bearer {token}", "X-Trace-ID": trace_id, "X-Task-Public-ID": task_public_id})
        if response.status_code >= 400: raise RuntimeError(f"business_context_http_{response.status_code}")
        value = response.json()
        if not isinstance(value, dict): raise ValueError("business context response must be an object")
        return value
