from __future__ import annotations
from datetime import UTC, datetime
from typing import Any
from app.context.runtime import validate_freshness_response, validate_runtime_context
from app.requirement_clarification.formal_mock import FormalMockRequirementClarifier
from app.providers.base import ProviderError
from app.requirement_clarification.models import RequirementClarifyTask, ClarificationSource
from app.requirement_clarification.result import validate_context_snapshot, validate_result_content


def _validate_context_source_binding(source: dict[str, Any], raw_ref: dict[str, Any]) -> None:
    expected = {
        "source_type": raw_ref["source_type"],
        "source_id": raw_ref["source_id"],
        "source_version_id": raw_ref["source_version_id"],
        "content_fingerprint": raw_ref["content_hash"],
    }
    if any(source.get(field) != value for field, value in expected.items()):
        raise ValueError("actual context trace source does not match canonical raw_input_ref")


def _iter_result_source_refs(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "source_refs":
                yield from item
            else:
                yield from _iter_result_source_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_result_source_refs(item)


def _validate_result_source_binding(result: dict[str, Any], raw_ref: dict[str, Any]) -> None:
    expected = {
        "source_type": raw_ref["source_type"],
        "source_id": raw_ref["source_id"],
        "source_version_id": raw_ref["source_version_id"],
        "content_hash": raw_ref["content_hash"],
        "label": raw_ref["label"],
    }
    refs = list(_iter_result_source_refs(result))
    if not refs:
        raise ValueError("ready result must contain the canonical raw_input_ref")
    if any(ref != expected for ref in refs):
        raise ValueError("result source_ref does not match canonical raw_input_ref")


class TaskRuntime:
    """Runtime requires a repository atomic persistence port; no partial success is allowed."""
    def __init__(self, *, repository: Any, context_client: Any, provider: Any, token_budget: int, object_store: Any):
        self.repository, self.context_client, self.provider, self.token_budget, self.object_store = repository, context_client, provider, token_budget, object_store
    def execute(self, *, task_public_id: str, trace_id: str) -> None:
        task = self.repository.get_task(task_public_id)
        if task is None or task.trace_id != trace_id: raise RuntimeError("AI task fact missing or trace mismatch")
        self.repository.update_status(task_public_id, "preparing")
        call_id = None
        provider_returned = False
        try:
            freshness = validate_freshness_response(
                self.context_client.target_freshness(task_public_id, trace_id=trace_id, target_snapshot_hash=task.target_snapshot_hash),
                target_snapshot_hash=task.target_snapshot_hash,
                target_object_version_id=task.target_object_version_id,
            )
            if not freshness.fresh:
                if hasattr(self.repository, "mark_status_with_event"):
                    self.repository.mark_status_with_event(task_public_id, "stale_target", failure_code="TARGET_NOT_FRESH")
                else:
                    self.repository.update_status(task_public_id, "stale_target", failure_code="TARGET_NOT_FRESH")
                    if hasattr(self.repository, "record_task_event"):
                        self.repository.record_task_event(task, event_name="ai.task.stale_target", status="stale_target", failure_code="TARGET_NOT_FRESH")
                    elif hasattr(self.repository, "record_outbox"):
                        self.repository.record_outbox({"event_name": "ai.task.stale_target", "task_public_id": task_public_id, "failure_code": "TARGET_NOT_FRESH"})
                return
            payload = self.context_client.context_snapshot(task_public_id, trace_id=trace_id, token_budget=self.token_budget)
            context = validate_runtime_context(payload, task_public_id=task_public_id, target_snapshot_hash=task.target_snapshot_hash, target_object_type=task.target_object_type, target_object_id=task.target_object_id, target_object_version_id=task.target_object_version_id)
            raw_ref = context.requirement_content["raw_input_ref"]
            source = ClarificationSource(
                source_type=raw_ref["source_type"],
                source_id=raw_ref["source_id"],
                source_version_id=raw_ref["source_version_id"],
                content_fingerprint=raw_ref["content_hash"],
                label=raw_ref["label"],
                token_count=0,
            )
            sources = (source,)
            envelope = RequirementClarifyTask(schema_version="0.2.0", task_public_id=task.task_public_id, user_id=task.user_id, project_id=task.project_id, project_version_id=task.project_version_id, module=task.module, task_type=task.task_type, target={"object_type":"requirement","object_id":task.target_object_id,"object_version_id":task.target_object_version_id}, target_snapshot_hash=task.target_snapshot_hash, source_ref_ids=context.source_ref_ids, capability_selection=None, risk_acceptances=tuple(item.model_dump() for item in context.risk_acceptances), command_id=task.command_id, trace_id=trace_id, requested_at=datetime.now(UTC), input=context.input.model_dump(), status="generating")
            self.repository.update_status(task_public_id, "generating")
            selector = getattr(self.provider, "bundle_selector", None)
            bundle = self.repository.resolve_bundle(**selector) if selector else self.repository.resolve_bundle()
            call_id = self.repository.create_call(task, bundle, capability_fingerprint=bundle["fingerprint"])
            if getattr(self.provider, "accepts_requirement_content", False):
                execution = self.provider.run(
                    envelope, sources, requirement_content=context.requirement_content
                )
            else:
                execution = self.provider.run(envelope, sources)
            provider_returned = True
            self.repository.update_status(task_public_id, "checking")
            validate_context_snapshot(execution.context_snapshot)
            actual_sources = execution.context_snapshot["sources"]
            if len(actual_sources) != 1:
                raise ValueError("actual context trace does not match validated runtime context")
            _validate_context_source_binding(actual_sources[0], raw_ref)
            if execution.recovery:
                failure_code = execution.recovery.failure_code
                failure_status = "failed" if failure_code == "DEPENDENCY_UNAVAILABLE" else "quality_blocked"
                self.repository.persist_failure(task, call_id, execution.result, status=failure_status, failure_code=failure_code, call_succeeded=True)
                return
            if execution.result.get("result_kind") not in {"assessment", "questions", "baseline"}:
                self.repository.persist_failure(task, call_id, execution.result, status="quality_blocked", failure_code="RESULT_QUALITY_BLOCKED", call_succeeded=True)
                return
            validate_result_content(execution.result)
            _validate_result_source_binding(execution.result, raw_ref)
            key, fingerprint = self.object_store.put_result(project_id=task.project_id, task_public_id=task_public_id, ai_call_id=str(call_id), result_no=1, content=execution.result)
            self.object_store.verify_result(key=key, content_fingerprint=fingerprint)
            self.repository.persist_success(task, call_id, context, execution, key, fingerprint)
        except ProviderError as exc:
            failure_code = f"PROVIDER_{exc.error_class.upper()}"
            if call_id is not None:
                self.repository.persist_failure(
                    task,
                    call_id,
                    None,
                    status="failed",
                    failure_code=failure_code,
                    call_succeeded=False,
                )
            else:
                self.repository.mark_status_with_event(
                    task_public_id, "failed", failure_code=failure_code
                )
            return
        except Exception:
            if call_id is not None:
                self.repository.persist_failure(task, call_id, None, status="failed", failure_code="AI_RUNTIME_FAILED", call_succeeded=provider_returned)
            else:
                if hasattr(self.repository, "mark_status_with_event"):
                    self.repository.mark_status_with_event(task_public_id, "failed", failure_code="AI_RUNTIME_FAILED")
                else:
                    self.repository.update_status(task_public_id, "failed", failure_code="AI_RUNTIME_FAILED")
                    if hasattr(self.repository, "record_task_event"):
                        self.repository.record_task_event(task, event_name="ai.task.failed", status="failed", failure_code="AI_RUNTIME_FAILED")
                    elif hasattr(self.repository, "record_outbox"):
                        self.repository.record_outbox({"event_name": "ai.task.failed", "task_public_id": task_public_id, "failure_code": "AI_RUNTIME_FAILED"})
            raise
