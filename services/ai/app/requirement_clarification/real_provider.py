"""Human-in-the-loop Requirement clarification backed by a real JSON provider."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from app.domain.task_state import TaskStatus
from app.providers.base import Provider, ProviderMalformedResponse, ProviderRequest
from app.requirement_clarification.formal_mock import DIMENSIONS, FormalMockRequirementClarifier
from app.requirement_clarification.models import (
    ClarificationExecution,
    ClarificationSource,
    RequirementClarifyTask,
)
from app.requirement_clarification.result import validate_result_content


class RealRequirementClarifier:
    truth_label = "REAL_PROVIDER"
    provider_id = "deepseek"
    accepts_requirement_content = True

    def __init__(self, provider: Provider, *, model: str = "deepseek-v4-flash") -> None:
        self.provider = provider
        self.model = model
        self.bundle_selector = {
            "provider_code": "deepseek",
            "model_code": model,
            "profile_name": "portfolio-mvp5-deepseek",
            "prompt_name": "requirement.clarify.deepseek",
        }

    def run(
        self,
        task: RequirementClarifyTask,
        sources: tuple[ClarificationSource, ...],
        *,
        requirement_content: dict[str, Any],
    ) -> ClarificationExecution:
        helper = FormalMockRequirementClarifier()
        context = helper._context_snapshot(task, sources)
        source_refs = helper._source_refs(context, sources)
        if not source_refs:
            raise ProviderMalformedResponse("canonical source reference is unavailable")
        prompt = self._prompt(task, requirement_content)
        prompt_fingerprint = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        response = self.provider.generate(
            ProviderRequest(
                trace_id=task.trace_id,
                task_public_id=task.task_public_id,
                model=self.model,
                prompt_fingerprint=prompt_fingerprint,
                input_text=prompt,
            )
        )
        try:
            candidate = json.loads(response.content)
        except (TypeError, ValueError) as exc:
            raise ProviderMalformedResponse("provider returned invalid JSON") from exc
        result = self._materialize(task, candidate, source_refs)
        validate_result_content(result)
        return ClarificationExecution(
            truth_label="REAL_PROVIDER",
            provider_id=response.provider,
            trace_id=task.trace_id,
            command_id=task.command_id,
            task_statuses=(
                TaskStatus.PREPARING,
                TaskStatus.GENERATING,
                TaskStatus.CHECKING,
                TaskStatus.READY,
            ),
            result=result,
            context_snapshot=context,
            recovery=None,
            provider_response=response.model_dump(mode="json"),
        )

    @staticmethod
    def _prompt(task: RequirementClarifyTask, requirement_content: dict[str, Any]) -> str:
        target_kind = (
            "assessment"
            if task.input.mode == "auto"
            else "baseline"
            if task.input.mode == "skip"
            or (task.input.mode == "standard" and task.input.round_no == 3)
            or (task.input.mode == "deep" and task.input.round_no == 5)
            else "questions"
        )
        schema: dict[str, Any] = {
            "result_kind": target_kind,
            "dimensions": {
                key: {"status": "complete | partial | missing", "reasons": ["..."], "missing_items": ["..."]}
                for key in DIMENSIONS
            },
            "assessment": {
                "complexity_band": "low | medium | high",
                "reasons": ["..."],
                "recommended_mode": "standard | deep | skip",
                "missing_items": ["..."],
            },
            "questions": [
                {
                    "question_id": "q-1",
                    "dimension": "one dimension key",
                    "question_text": "...",
                    "reason": "...",
                }
            ],
            "baseline": {
                "dimensions": {
                    key: {
                        "confirmed_facts": ["..."],
                        "deferred_items": ["..."],
                        "not_applicable_items": ["..."],
                    }
                    for key in DIMENSIONS
                },
                "assumptions": ["..."],
                "unresolved_items": ["..."],
            },
            "convergence": {
                "should_finish": False,
                "finish_reason": None,
                "next_round_no": 1,
            },
        }
        if target_kind == "assessment":
            schema["questions"] = []
            schema["baseline"] = None
            schema["convergence"] = {
                "should_finish": False,
                "finish_reason": None,
                "next_round_no": 1,
            }
        elif target_kind == "questions":
            schema["assessment"] = None
            schema["baseline"] = None
            schema["convergence"] = {
                "should_finish": False,
                "finish_reason": None,
                "next_round_no": task.input.round_no + 1,
            }
        else:
            schema["assessment"] = None
            schema["questions"] = []
            schema["convergence"] = {
                "should_finish": True,
                "finish_reason": (
                    "mode_skipped" if task.input.mode == "skip" else "round_limit"
                ),
                "next_round_no": None,
            }
        return json.dumps(
            {
                "instruction": (
                    "Analyze the Chinese or English product requirement. Return only JSON matching output_schema. "
                    f"The only permitted result_kind is {target_kind}; do not choose another stage. "
                    "Copy the exact output_schema shape and replace placeholder strings with concrete content. "
                    "Use all eight dimensions exactly once. "
                    "AI content is a candidate for human review; do not claim confirmation. "
                    "For non-selected assessment/questions/baseline fields, return null or an empty array as appropriate."
                ),
                "task": {
                    "mode": task.input.mode,
                    "round_no": task.input.round_no,
                    "target_snapshot_hash": task.target_snapshot_hash,
                },
                "requirement_content": requirement_content,
                "output_schema": schema,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _strings(value: Any, field: str, *, minimum: int = 0) -> list[str]:
        if (
            not isinstance(value, list)
            or len(value) < minimum
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise ProviderMalformedResponse(f"{field} must be a non-blank string array")
        return [item.strip() for item in value]

    def _materialize(
        self,
        task: RequirementClarifyTask,
        candidate: Any,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise ProviderMalformedResponse("structured output must be an object")
        kind = candidate.get("result_kind")
        expected_kind = (
            "assessment"
            if task.input.mode == "auto"
            else "baseline"
            if task.input.mode == "skip"
            or (task.input.mode == "standard" and task.input.round_no == 3)
            or (task.input.mode == "deep" and task.input.round_no == 5)
            else "questions"
        )
        if kind != expected_kind:
            raise ProviderMalformedResponse("result_kind does not match the requested clarification stage")
        raw_dimensions = candidate.get("dimensions")
        if not isinstance(raw_dimensions, dict) or set(raw_dimensions) != set(DIMENSIONS):
            raise ProviderMalformedResponse("dimensions must contain exactly the frozen eight keys")
        dimensions: dict[str, Any] = {}
        for key in DIMENSIONS:
            raw = raw_dimensions[key]
            if not isinstance(raw, dict) or raw.get("status") not in {"complete", "partial", "missing"}:
                raise ProviderMalformedResponse(f"dimension {key} is invalid")
            dimensions[key] = {
                "status": raw["status"],
                "reasons": self._strings(raw.get("reasons"), f"dimensions.{key}.reasons", minimum=1),
                "missing_items": self._strings(raw.get("missing_items", []), f"dimensions.{key}.missing_items"),
                "source_refs": deepcopy(source_refs),
            }
        result: dict[str, Any] = {
            "schema_version": "0.2.0",
            "task_public_id": task.task_public_id,
            "task_type": "requirement.clarify",
            "target_snapshot_hash": task.target_snapshot_hash,
            "mode": task.input.mode,
            "round_no": task.input.round_no,
            "status": "ready",
            "result_kind": kind,
            "dimensions": dimensions,
            "assessment": None,
            "questions": [],
            "baseline": None,
        }
        if kind == "assessment":
            raw = candidate.get("assessment")
            if not isinstance(raw, dict) or raw.get("complexity_band") not in {"low", "medium", "high"} or raw.get("recommended_mode") not in {"standard", "deep", "skip"}:
                raise ProviderMalformedResponse("assessment is invalid")
            result["assessment"] = {
                "dimension_completeness": deepcopy(dimensions),
                "complexity_band": raw["complexity_band"],
                "reasons": self._strings(raw.get("reasons"), "assessment.reasons", minimum=1),
                "recommended_mode": raw["recommended_mode"],
                "missing_items": self._strings(raw.get("missing_items", []), "assessment.missing_items"),
                "source_refs": deepcopy(source_refs),
            }
        elif kind == "questions":
            raw_questions = candidate.get("questions")
            if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= 3:
                raise ProviderMalformedResponse("questions must contain 1 to 3 items")
            seen: set[str] = set()
            for raw in raw_questions:
                if not isinstance(raw, dict) or raw.get("dimension") not in DIMENSIONS:
                    raise ProviderMalformedResponse("question is invalid")
                question_id = str(raw.get("question_id", "")).strip()
                if not question_id or question_id in seen:
                    raise ProviderMalformedResponse("question_id must be unique and non-blank")
                seen.add(question_id)
                result["questions"].append(
                    {
                        "question_id": question_id,
                        "dimension": raw["dimension"],
                        "question_text": self._strings([raw.get("question_text")], "question_text", minimum=1)[0],
                        "reason": self._strings([raw.get("reason")], "question.reason", minimum=1)[0],
                        "source_refs": deepcopy(source_refs),
                    }
                )
        else:
            raw = candidate.get("baseline")
            if not isinstance(raw, dict) or not isinstance(raw.get("dimensions"), dict) or set(raw["dimensions"]) != set(DIMENSIONS):
                raise ProviderMalformedResponse("baseline dimensions are invalid")
            baseline_dimensions: dict[str, Any] = {}
            for key in DIMENSIONS:
                item = raw["dimensions"][key]
                if not isinstance(item, dict):
                    raise ProviderMalformedResponse(f"baseline dimension {key} is invalid")
                baseline_dimensions[key] = {
                    "confirmed_facts": self._strings(item.get("confirmed_facts"), f"baseline.{key}.confirmed_facts", minimum=1),
                    "source_refs": deepcopy(source_refs),
                    "deferred_items": self._strings(item.get("deferred_items", []), f"baseline.{key}.deferred_items"),
                    "not_applicable_items": self._strings(item.get("not_applicable_items", []), f"baseline.{key}.not_applicable_items"),
                }
            result["baseline"] = {
                "dimensions": baseline_dimensions,
                "assumptions": self._strings(raw.get("assumptions", []), "baseline.assumptions"),
                "unresolved_items": self._strings(raw.get("unresolved_items", []), "baseline.unresolved_items"),
            }
        raw_convergence = candidate.get("convergence")
        if not isinstance(raw_convergence, dict):
            raise ProviderMalformedResponse("convergence is invalid")
        result["convergence"] = {
            "should_finish": kind == "baseline",
            "finish_reason": ("mode_skipped" if task.input.mode == "skip" else "round_limit") if kind == "baseline" else None,
            "next_round_no": None if kind == "baseline" else (1 if kind == "assessment" else task.input.round_no + 1),
        }
        result["quality"] = {
            "format_status": "passed",
            "traceability_status": "passed",
            "safety_status": "passed",
            "major_error": False,
            "blocker_codes": [],
            "required_items_total": len(DIMENSIONS),
            "required_items_met": len(DIMENSIONS) if kind == "baseline" else sum(item["status"] == "complete" for item in dimensions.values()),
        }
        return result
