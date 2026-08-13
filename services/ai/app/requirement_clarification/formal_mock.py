from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Literal

from app.domain.task_state import TaskStatus
from app.requirement_clarification.models import (
    ClarificationExecution,
    ClarificationSource,
    ManualRecovery,
    RequirementClarifyTask,
)


TRUTH_LABEL = "FORMAL_MOCK"
DIMENSIONS = (
    "goal", "users_and_roles", "usage_scenarios", "functional_scope",
    "business_rules", "exception_cases", "permission_requirements", "acceptance_criteria",
)
QUESTION_TEXT = {
    "users_and_roles": "哪些角色参与需求确认，各自承担什么责任？",
    "usage_scenarios": "最重要的使用场景和触发条件是什么？",
    "business_rules": "哪些业务规则会决定需求是否可以继续推进？",
    "exception_cases": "出现异常或依赖不可用时，业务应如何继续？",
    "permission_requirements": "谁可以编辑、确认或只读查看该需求？",
    "acceptance_criteria": "哪些可观察条件表示该需求已经满足？",
}
BASELINE_FACT = {
    "goal": "形成可由有权用户审核的需求基线。",
    "users_and_roles": "需求负责人负责澄清、风险接受和最终确认。",
    "usage_scenarios": "用户可从手工输入或文件导入开始需求澄清。",
    "functional_scope": "需求基线覆盖八个固定业务维度。",
    "business_rules": "澄清达到轮次上限时必须收敛并保留未决项。",
    "exception_cases": "AI不可用时保留人工澄清、编辑和确认路径。",
    "permission_requirements": "只有具备确认权限的项目成员可以正式采用候选。",
    "acceptance_criteria": "八维内容、来源、假设和未决项均可追溯。",
}


FailureMode = Literal["none", "rate_limited", "timeout", "unavailable"]


class FormalMockRequirementClarifier:
    """Offline, deterministic Requirement clarifier explicitly labeled FORMAL_MOCK."""

    truth_label = TRUTH_LABEL
    provider_id = "requirement-clarify-formal-mock"

    def __init__(self, *, failure_mode: FailureMode = "none") -> None:
        if failure_mode not in {"none", "rate_limited", "timeout", "unavailable"}:
            raise ValueError("unsupported FORMAL_MOCK failure mode")
        self.failure_mode = failure_mode

    def run(self, task: RequirementClarifyTask, sources: tuple[ClarificationSource, ...]) -> ClarificationExecution:
        context = self._context_snapshot(task, sources)
        source_refs = self._source_refs(context, sources)
        if self.failure_mode != "none":
            return self._manual_recovery(task, context, source_refs, "DEPENDENCY_UNAVAILABLE")
        if not source_refs:
            return self._manual_recovery(task, context, source_refs, "TRACEABILITY_INCOMPLETE")

        if task.input.mode == "auto":
            result = self._assessment(task, source_refs)
        elif task.input.mode == "skip":
            result = self._baseline(task, source_refs, finish_reason="mode_skipped")
        elif task.input.mode == "standard" and task.input.round_no == 3:
            result = self._baseline(task, source_refs, finish_reason="round_limit")
        elif task.input.mode == "deep" and task.input.round_no == 5:
            result = self._baseline(task, source_refs, finish_reason="round_limit")
        else:
            result = self._questions(task, source_refs)
        return ClarificationExecution(
            truth_label=TRUTH_LABEL,
            provider_id=self.provider_id,
            trace_id=task.trace_id,
            command_id=task.command_id,
            task_statuses=(TaskStatus.PREPARING, TaskStatus.GENERATING, TaskStatus.CHECKING, TaskStatus.READY),
            result=result,
            context_snapshot=context,
            recovery=None,
        )

    def _context_snapshot(self, task: RequirementClarifyTask, sources: tuple[ClarificationSource, ...]) -> dict[str, Any]:
        by_id = {source.source_id: source for source in sources}
        source_rows: list[dict[str, Any]] = []
        injections: list[dict[str, Any]] = []
        exclusions: list[dict[str, str]] = []
        for source_id in task.source_ref_ids:
            source = by_id.get(source_id)
            if source is None:
                exclusions.append({"source_id": source_id, "reason": "source_unavailable"})
                continue
            source_rows.append({
                "source_id": source.source_id,
                "source_version_id": source.source_version_id,
                "source_type": source.source_type,
                "content_fingerprint": source.content_fingerprint,
                "was_injected": source.was_injected,
                "exclusion_reason": source.exclusion_reason,
                "token_count": source.token_count,
            })
            if source.was_injected:
                injections.append({
                    "source_id": source.source_id,
                    "injection_order": len(injections) + 1,
                    "token_count": source.token_count,
                    "content_fingerprint": source.content_fingerprint,
                })
            else:
                exclusions.append({"source_id": source.source_id, "reason": source.exclusion_reason or "excluded"})
        fingerprint_input = json.dumps(
            {"sources": source_rows, "injections": injections, "exclusions": exclusions},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        context_fingerprint = sha256(fingerprint_input).hexdigest()
        return {
            "schema_version": "0.2.0",
            "snapshot_id": f"ctx-{context_fingerprint[:24]}",
            "task_public_id": task.task_public_id,
            "target_snapshot_hash": task.target_snapshot_hash,
            "sources": source_rows,
            "injections": injections,
            "exclusions": exclusions,
            "context_fingerprint": context_fingerprint,
            "token_count": sum(item["token_count"] for item in injections),
        }

    @staticmethod
    def _source_refs(
        context: dict[str, Any],
        sources: tuple[ClarificationSource, ...],
    ) -> list[dict[str, Any]]:
        injected_ids = {item["source_id"] for item in context["injections"]}
        labels = {source.source_id: source.label for source in sources}
        return [{
            "source_type": item["source_type"],
            "source_id": item["source_id"],
            "source_version_id": item["source_version_id"],
            "content_hash": item["content_fingerprint"],
            "label": labels[item["source_id"]],
        } for item in context["sources"] if item["source_id"] in injected_ids]

    @staticmethod
    def _dimensions(source_refs: list[dict[str, Any]], *, failed: bool = False) -> dict[str, Any]:
        complete = {"goal", "usage_scenarios", "functional_scope"}
        missing = {"exception_cases", "acceptance_criteria"}
        dimensions: dict[str, Any] = {}
        for key in DIMENSIONS:
            status = "missing" if failed or key in missing else "complete" if key in complete else "partial"
            dimensions[key] = {
                "status": status,
                "reasons": ["AI执行失败，需人工完成。"] if failed else ["FORMAL_MOCK确定性预检结果。"],
                "missing_items": ["需要人工补充或确认。"] if status != "complete" else [],
                "source_refs": deepcopy(source_refs),
            }
        return dimensions

    def _common(self, task: RequirementClarifyTask, source_refs: list[dict[str, Any]], *, status: str = "ready", failed: bool = False) -> dict[str, Any]:
        return {
            "schema_version": "0.2.0",
            "task_public_id": task.task_public_id,
            "task_type": "requirement.clarify",
            "target_snapshot_hash": task.target_snapshot_hash,
            "mode": task.input.mode,
            "round_no": task.input.round_no,
            "status": status,
            "dimensions": self._dimensions(source_refs, failed=failed),
        }

    def _assessment(self, task: RequirementClarifyTask, source_refs: list[dict[str, Any]]) -> dict[str, Any]:
        result = self._common(task, source_refs)
        result.update({
            "result_kind": "assessment",
            "assessment": {
                "dimension_completeness": deepcopy(result["dimensions"]),
                "complexity_band": "medium",
                "reasons": ["存在需要继续澄清的业务信息。"],
                "recommended_mode": "standard",
                "missing_items": ["异常处理", "验收标准"],
                "source_refs": deepcopy(source_refs),
            },
            "questions": [],
            "baseline": None,
            "convergence": {"should_finish": False, "finish_reason": None, "next_round_no": 1},
            "quality": self._quality(result["dimensions"], traceable=True),
        })
        return result

    def _questions(self, task: RequirementClarifyTask, source_refs: list[dict[str, Any]]) -> dict[str, Any]:
        result = self._common(task, source_refs)
        count = 1 + int(sha256(task.task_public_id.encode("utf-8")).hexdigest()[0], 16) % 3
        keys = tuple(QUESTION_TEXT)[:count]
        result.update({
            "result_kind": "questions",
            "assessment": None,
            "questions": [{
                "question_id": f"q-{index}",
                "dimension": key,
                "question_text": QUESTION_TEXT[key],
                "reason": "该业务维度仍存在高价值缺口。",
                "source_refs": deepcopy(source_refs),
            } for index, key in enumerate(keys, start=1)],
            "baseline": None,
            "convergence": {"should_finish": False, "finish_reason": None, "next_round_no": task.input.round_no + 1},
            "quality": self._quality(result["dimensions"], traceable=True),
        })
        return result

    def _baseline(self, task: RequirementClarifyTask, source_refs: list[dict[str, Any]], *, finish_reason: Literal["round_limit", "mode_skipped"]) -> dict[str, Any]:
        result = self._common(task, source_refs)
        baseline_dimensions = {
            key: {
                "confirmed_facts": [BASELINE_FACT[key]],
                "source_refs": deepcopy(source_refs),
                "deferred_items": ["由有权用户复核后决定是否纳入后续范围。"] if key in {"business_rules", "acceptance_criteria"} else [],
                "not_applicable_items": [],
            }
            for key in DIMENSIONS
        }
        baseline_quality = self._quality(result["dimensions"], traceable=True)
        baseline_quality["required_items_total"] = len(DIMENSIONS)
        baseline_quality["required_items_met"] = len(baseline_dimensions)
        result.update({
            "result_kind": "baseline",
            "assessment": None,
            "questions": [],
            "baseline": {
                "dimensions": baseline_dimensions,
                "assumptions": ["当前结论仅基于已注入并可追溯的来源。"],
                "unresolved_items": ["候选仍需有权用户审核、编辑或拒绝。"],
            },
            "convergence": {"should_finish": True, "finish_reason": finish_reason, "next_round_no": None},
            "quality": baseline_quality,
        })
        return result

    def _manual_recovery(self, task: RequirementClarifyTask, context: dict[str, Any], source_refs: list[dict[str, Any]], failure_code: Literal["DEPENDENCY_UNAVAILABLE", "TRACEABILITY_INCOMPLETE"]) -> ClarificationExecution:
        result = self._common(
            task,
            source_refs,
            status="failed" if failure_code == "DEPENDENCY_UNAVAILABLE" else "quality_blocked",
            failed=True,
        )
        result.update({
            "result_kind": "assessment",
            "assessment": {
                "dimension_completeness": deepcopy(result["dimensions"]),
                "complexity_band": "high",
                "reasons": ["AI结果不可用，必须保留并使用人工路径。"],
                "recommended_mode": "skip",
                "missing_items": ["人工澄清与人工Baseline"],
                "source_refs": deepcopy(source_refs),
            },
            "questions": [],
            "baseline": None,
            "convergence": {"should_finish": True, "finish_reason": "ai_unavailable_manual", "next_round_no": None},
            "quality": {
                "format_status": "passed",
                "traceability_status": "passed" if source_refs else "failed",
                "safety_status": "passed",
                "major_error": False,
                "blocker_codes": [failure_code],
                "required_items_total": 8,
                "required_items_met": 0,
            },
        })
        recovery = ManualRecovery(
            failure_code=failure_code,
            finish_reason="ai_unavailable_manual",
            actions=("manual_input", "manual_clarification", "manual_baseline", "confirm_after_gate", "retry_ai_task"),
            retryable=True,
        )
        return ClarificationExecution(
            truth_label=TRUTH_LABEL,
            provider_id=self.provider_id,
            trace_id=task.trace_id,
            command_id=task.command_id,
            task_statuses=(
                (TaskStatus.PREPARING, TaskStatus.GENERATING, TaskStatus.FAILED)
                if failure_code == "DEPENDENCY_UNAVAILABLE"
                else (TaskStatus.PREPARING, TaskStatus.GENERATING, TaskStatus.CHECKING, TaskStatus.QUALITY_BLOCKED)
            ),
            result=result,
            context_snapshot=context,
            recovery=recovery,
        )

    @staticmethod
    def _quality(dimensions: dict[str, Any], *, traceable: bool) -> dict[str, Any]:
        return {
            "format_status": "passed",
            "traceability_status": "passed" if traceable else "failed",
            "safety_status": "passed",
            "major_error": False,
            "blocker_codes": [],
            "required_items_total": len(DIMENSIONS),
            "required_items_met": sum(item["status"] == "complete" for item in dimensions.values()),
        }
