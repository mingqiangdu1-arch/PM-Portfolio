"""Human-in-the-loop Requirement clarification backed by a real JSON provider."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from app.domain.task_state import TaskStatus
from app.providers.base import (
    MalformedResponseSubtype,
    Provider,
    ProviderMalformedResponse,
    ProviderRequest,
)
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
            raise ProviderMalformedResponse(
                "canonical source reference is unavailable",
                subtype=MalformedResponseSubtype.CANONICAL_SOURCE_UNAVAILABLE,
            )
        prompt = self._prompt(task, requirement_content)
        prompt_fingerprint = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        response = self.provider.generate(
            ProviderRequest(
                trace_id=task.trace_id,
                task_public_id=task.task_public_id,
                model=self.model,
                prompt_fingerprint=prompt_fingerprint,
                input_text=prompt,
                response_schema_name="requirement_clarification_candidate",
                response_schema=self._response_schema(task),
            )
        )
        try:
            candidate = json.loads(response.content)
        except (TypeError, ValueError) as exc:
            raise ProviderMalformedResponse(
                "provider returned invalid JSON",
                subtype=MalformedResponseSubtype.INVALID_JSON,
            ) from exc
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
                key: {"status": "complete | partial | missing | not_applicable", "reasons": ["..."], "missing_items": ["..."]}
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
                    "The platform language is Simplified Chinese. Write every human-visible generated string "
                    "in Simplified Chinese, including reasons, missing_items, question_text, question reason, "
                    "baseline facts, assumptions, and unresolved_items. Preserve identifiers, acronyms, product "
                    "names, and channel names such as SKU, SPU, API, JD, and MinIO when needed, but never return "
                    "an English-only question or reason. "
                    f"The only permitted result_kind is {target_kind}; do not choose another stage. "
                    "Copy the exact output_schema shape and replace placeholder strings with concrete content. "
                    "Use all eight dimensions exactly once. "
                    "Return exactly one JSON object without Markdown fences, prose, or an extra wrapper. "
                    "For questions output, return 1 to 3 questions; each question must contain only "
                    "question_id, dimension, question_text, and reason. Use unique question IDs matching "
                    "q-[1-9][0-9]* and use only one of the eight declared dimension keys. "
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
    def _response_schema(task: RequirementClarifyTask) -> dict[str, Any]:
        target_kind = (
            "assessment"
            if task.input.mode == "auto"
            else "baseline"
            if task.input.mode == "skip"
            or (task.input.mode == "standard" and task.input.round_no == 3)
            or (task.input.mode == "deep" and task.input.round_no == 5)
            else "questions"
        )

        def string_array(*, minimum: int = 0, maximum_length: int | None = None) -> dict[str, Any]:
            item: dict[str, Any] = {"type": "string", "minLength": 1}
            if maximum_length is not None:
                item["maxLength"] = maximum_length
            return {"type": "array", "minItems": minimum, "items": item}

        dimension = {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "reasons", "missing_items"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["complete", "partial", "missing", "not_applicable"],
                },
                "reasons": string_array(minimum=1),
                "missing_items": string_array(),
            },
        }
        dimensions = {
            "type": "object",
            "additionalProperties": False,
            "required": list(DIMENSIONS),
            "properties": {key: deepcopy(dimension) for key in DIMENSIONS},
        }
        assessment = {
            "type": "object",
            "additionalProperties": False,
            "required": ["complexity_band", "reasons", "recommended_mode", "missing_items"],
            "properties": {
                "complexity_band": {"type": "string", "enum": ["low", "medium", "high"]},
                "reasons": string_array(minimum=1),
                "recommended_mode": {"type": "string", "enum": ["standard", "deep", "skip"]},
                "missing_items": string_array(),
            },
        }
        question = {
            "type": "object",
            "additionalProperties": False,
            "required": ["question_id", "dimension", "question_text", "reason"],
            "properties": {
                "question_id": {"type": "string", "pattern": r"^q-[1-9][0-9]*$"},
                "dimension": {"type": "string", "enum": list(DIMENSIONS)},
                "question_text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1000,
                    "description": "A human-facing clarification question written in Simplified Chinese.",
                },
                "reason": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                    "description": "A human-facing explanation written in Simplified Chinese.",
                },
            },
        }
        baseline_dimension = {
            "type": "object",
            "additionalProperties": False,
            "required": ["confirmed_facts", "deferred_items", "not_applicable_items"],
            "properties": {
                "confirmed_facts": string_array(minimum=1),
                "deferred_items": string_array(),
                "not_applicable_items": string_array(),
            },
        }
        baseline = {
            "type": "object",
            "additionalProperties": False,
            "required": ["dimensions", "assumptions", "unresolved_items"],
            "properties": {
                "dimensions": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(DIMENSIONS),
                    "properties": {
                        key: deepcopy(baseline_dimension) for key in DIMENSIONS
                    },
                },
                "assumptions": string_array(),
                "unresolved_items": string_array(),
            },
        }
        finish_reason = (
            "mode_skipped" if task.input.mode == "skip" else "round_limit"
        ) if target_kind == "baseline" else None
        next_round_no = (
            None
            if target_kind == "baseline"
            else 1
            if target_kind == "assessment"
            else task.input.round_no + 1
        )
        return {
            "type": "object",
            "description": (
                "All human-visible generated strings must use Simplified Chinese; technical identifiers and "
                "acronyms may remain in their canonical form."
            ),
            "additionalProperties": False,
            "required": [
                "result_kind",
                "dimensions",
                "assessment",
                "questions",
                "baseline",
                "convergence",
            ],
            "properties": {
                "result_kind": {"const": target_kind},
                "dimensions": dimensions,
                "assessment": assessment if target_kind == "assessment" else {"type": "null"},
                "questions": (
                    {"type": "array", "minItems": 1, "maxItems": 3, "items": question}
                    if target_kind == "questions"
                    else {"type": "array", "maxItems": 0}
                ),
                "baseline": baseline if target_kind == "baseline" else {"type": "null"},
                "convergence": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["should_finish", "finish_reason", "next_round_no"],
                    "properties": {
                        "should_finish": {"const": target_kind == "baseline"},
                        "finish_reason": {"const": finish_reason},
                        "next_round_no": {"const": next_round_no},
                    },
                },
            },
        }

    @staticmethod
    def _strings(
        value: Any,
        field: str,
        *,
        minimum: int = 0,
        maximum_length: int | None = None,
    ) -> list[str]:
        if (
            not isinstance(value, list)
            or len(value) < minimum
            or any(
                not isinstance(item, str)
                or not item.strip()
                or (maximum_length is not None and len(item.strip()) > maximum_length)
                for item in value
            )
        ):
            raise ProviderMalformedResponse(
                f"{field} must be a valid non-blank string array",
                subtype=MalformedResponseSubtype.INVALID_FIELD_TYPE,
                field=field,
            )
        return [item.strip() for item in value]

    def _materialize(
        self,
        task: RequirementClarifyTask,
        candidate: Any,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise ProviderMalformedResponse(
                "structured output must be an object",
                subtype=MalformedResponseSubtype.NON_OBJECT_ROOT,
            )
        expected_root_fields = {
            "result_kind", "dimensions", "assessment", "questions", "baseline", "convergence"
        }
        if candidate.get("result_kind") == "questions" and "questions" not in candidate:
            raise ProviderMalformedResponse(
                "questions are required",
                subtype=MalformedResponseSubtype.MISSING_QUESTIONS,
                field="questions",
            )
        if set(candidate) != expected_root_fields:
            raise ProviderMalformedResponse(
                "structured output root fields do not match the requested schema",
                subtype=MalformedResponseSubtype.UNEXPECTED_ROOT_FIELDS,
                rule="exact_root_fields",
            )
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
            raise ProviderMalformedResponse(
                "result_kind does not match the requested clarification stage",
                subtype=MalformedResponseSubtype.WRONG_RESULT_KIND,
                field="result_kind",
            )
        raw_dimensions = candidate.get("dimensions")
        if not isinstance(raw_dimensions, dict) or set(raw_dimensions) != set(DIMENSIONS):
            raise ProviderMalformedResponse(
                "dimensions must contain exactly the frozen eight keys",
                subtype=MalformedResponseSubtype.INVALID_DIMENSIONS,
                field="dimensions",
            )
        dimensions: dict[str, Any] = {}
        for key in DIMENSIONS:
            raw = raw_dimensions[key]
            if (
                not isinstance(raw, dict)
                or set(raw) != {"status", "reasons", "missing_items"}
                or raw.get("status") not in {"complete", "partial", "missing", "not_applicable"}
            ):
                raise ProviderMalformedResponse(
                    f"dimension {key} is invalid",
                    subtype=MalformedResponseSubtype.INVALID_DIMENSION_SHAPE,
                    field=f"dimensions.{key}",
                )
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
            if raw_questions is None:
                raise ProviderMalformedResponse(
                    "questions are required",
                    subtype=MalformedResponseSubtype.MISSING_QUESTIONS,
                    field="questions",
                )
            if not isinstance(raw_questions, list):
                raise ProviderMalformedResponse(
                    "questions must be an array",
                    subtype=MalformedResponseSubtype.INVALID_FIELD_TYPE,
                    field="questions",
                )
            if not 1 <= len(raw_questions) <= 3:
                raise ProviderMalformedResponse(
                    "questions must contain 1 to 3 items",
                    subtype=MalformedResponseSubtype.INVALID_QUESTION_COUNT,
                    field="questions",
                    rule="min_1_max_3",
                )
            seen: set[str] = set()
            for raw in raw_questions:
                if not isinstance(raw, dict):
                    raise ProviderMalformedResponse(
                        "question shape is invalid",
                        subtype=MalformedResponseSubtype.INVALID_QUESTION_SHAPE,
                        field="questions[]",
                    )
                if "question_id" not in raw:
                    raise ProviderMalformedResponse(
                        "question_id is required",
                        subtype=MalformedResponseSubtype.MISSING_QUESTION_ID,
                        field="questions[].question_id",
                    )
                if set(raw) != {
                    "question_id", "dimension", "question_text", "reason"
                }:
                    raise ProviderMalformedResponse(
                        "question shape is invalid",
                        subtype=MalformedResponseSubtype.INVALID_QUESTION_SHAPE,
                        field="questions[]",
                    )
                if raw.get("dimension") not in DIMENSIONS:
                    raise ProviderMalformedResponse(
                        "question dimension is invalid",
                        subtype=MalformedResponseSubtype.INVALID_DIMENSION,
                        field="questions[].dimension",
                    )
                if not isinstance(raw["question_id"], str):
                    raise ProviderMalformedResponse(
                        "question_id must be a string",
                        subtype=MalformedResponseSubtype.INVALID_FIELD_TYPE,
                        field="questions[].question_id",
                    )
                if not raw["question_id"].strip():
                    raise ProviderMalformedResponse(
                        "question_id is required",
                        subtype=MalformedResponseSubtype.MISSING_QUESTION_ID,
                        field="questions[].question_id",
                    )
                question_id = raw["question_id"].strip()
                if re.fullmatch(r"q-[1-9][0-9]*", question_id) is None:
                    raise ProviderMalformedResponse(
                        "question_id does not match the frozen pattern",
                        subtype=MalformedResponseSubtype.INVALID_QUESTION_ID,
                        field="questions[].question_id",
                        rule="q-[1-9][0-9]*",
                    )
                if question_id in seen:
                    raise ProviderMalformedResponse(
                        "question_id must be unique",
                        subtype=MalformedResponseSubtype.DUPLICATE_QUESTION_ID,
                        field="questions[].question_id",
                    )
                seen.add(question_id)
                if not isinstance(raw.get("question_text"), str):
                    raise ProviderMalformedResponse(
                        "question_text must be a string",
                        subtype=MalformedResponseSubtype.INVALID_FIELD_TYPE,
                        field="questions[].question_text",
                    )
                if not raw["question_text"].strip():
                    raise ProviderMalformedResponse(
                        "question_text is required",
                        subtype=MalformedResponseSubtype.MISSING_QUESTION_TEXT,
                        field="questions[].question_text",
                    )
                if not isinstance(raw.get("reason"), str):
                    raise ProviderMalformedResponse(
                        "reason must be a string",
                        subtype=MalformedResponseSubtype.INVALID_FIELD_TYPE,
                        field="questions[].reason",
                    )
                if not raw["reason"].strip():
                    raise ProviderMalformedResponse(
                        "reason is required",
                        subtype=MalformedResponseSubtype.MISSING_REASON,
                        field="questions[].reason",
                    )
                for field in ("question_text", "reason"):
                    if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", raw[field]) is None:
                        raise ProviderMalformedResponse(
                            "human-visible clarification text must use Simplified Chinese",
                            subtype=MalformedResponseSubtype.INVALID_OUTPUT_LANGUAGE,
                            field=f"questions[].{field}",
                            rule="contains_cjk_text",
                        )
                result["questions"].append(
                    {
                        "question_id": question_id,
                        "dimension": raw["dimension"],
                        "question_text": self._strings(
                            [raw["question_text"]], "questions[].question_text", minimum=1, maximum_length=1000
                        )[0],
                        "reason": self._strings(
                            [raw["reason"]], "questions[].reason", minimum=1, maximum_length=2000
                        )[0],
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
            raise ProviderMalformedResponse(
                "convergence is invalid",
                subtype=MalformedResponseSubtype.INVALID_CONVERGENCE,
                field="convergence",
            )
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
