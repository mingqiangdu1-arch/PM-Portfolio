from __future__ import annotations

from copy import deepcopy
from typing import Any


def _string(*, nullable: bool = False, **constraints: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": ["string", "null"] if nullable else "string"}
    schema.update(constraints)
    return schema


def _object(
    properties: dict[str, Any],
    required: list[str] | None = None,
    *,
    additional_properties: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": additional_properties,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _envelope(data_ref: str) -> dict[str, Any]:
    return _object(
        {
            "code": {"type": "string", "const": "OK"},
            "message": {"type": "string"},
            "data": {"$ref": f"#/components/schemas/{data_ref}"},
            "trace_id": _string(),
        },
        ["code", "message", "data", "trace_id"],
    )


def _parameter(name: str, *, location: str = "path", required: bool = True) -> dict[str, Any]:
    return {"name": name, "in": location, "required": required, "schema": _string()}


def _operation(
    operation_id: str,
    tag: str,
    response_schema: str,
    *,
    request_schema: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    idempotent: bool = False,
    description: str | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "tags": [tag],
        "security": [{"bearerAuth": []}],
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{response_schema}"}
                    }
                },
            }
        },
        "x-contract-phase": "sprint-2-p1-runtime-r4-candidate",
        "x-implementation-status": "implemented-p1-runtime-r4-candidate",
    }
    operation_parameters = deepcopy(parameters or [])
    if idempotent:
        operation_parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
        operation["x-idempotency-scope"] = "actor+endpoint+request-hash"
    if operation_parameters:
        operation["parameters"] = operation_parameters
    if request_schema:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{request_schema}"}
                }
            },
        }
    if description:
        operation["description"] = description
    if blockers:
        # These are settled R4 contract decisions, not unresolved Review blockers.
        operation["x-r4-decisions"] = blockers
    return operation


VERSION_ID = _parameter("version_id")
REQUIREMENT_ID = _parameter("requirement_id")
TASK_ID = _parameter("task_id")
RESULT_ID = _parameter("result_id")

REQUIREMENT_DIMENSIONS = [
    "goal",
    "users_and_roles",
    "usage_scenarios",
    "functional_scope",
    "business_rules",
    "exception_cases",
    "permission_requirements",
    "acceptance_criteria",
]

TASK_STATUSES = [
    "prechecking",
    "blocked",
    "queued",
    "preparing",
    "generating",
    "checking",
    "ready",
    "partial_result",
    "quality_blocked",
    "cancel_requested",
    "cancelled",
    "failed",
    "expired",
    "stale_target",
]

RESULT_STATUSES = ["ready", "partial_result", "quality_blocked", "failed", "expired", "stale_target"]
RESULT_KINDS = ["assessment", "questions", "baseline"]
REQUIREMENT_SOURCE_TYPES = ["manual", "file_import"]
REQUIREMENT_PRIORITIES = ["low", "normal", "high", "critical"]
REQUIREMENT_STATUSES = ["draft", "effective", "archived"]
VERSION_CONFIRMATION_STATUSES = ["draft", "confirmed"]
CONFIRMATION_GATE_RESULTS = ["passed", "passed_with_risk"]
COMPLETENESS_STATUSES = ["complete", "partial", "missing", "not_applicable"]
COMPLEXITY_BANDS = ["low", "medium", "high"]
FINISH_REASONS = [
    "round_limit",
    "user_finished",
    "no_new_high_value_question",
    "mode_skipped",
    "ai_unavailable_manual",
]
RISK_IMPACTS = ["low", "medium"]
MODIFICATION_INTENSITIES = ["none", "minor", "major"]
ADOPTION_STATUSES = ["adopted", "adopted_after_edit", "rejected"]
ERROR_HTTP_MAPPING = {
    "AUTH_REQUIRED": 401,
    "FORBIDDEN": 403,
    "PERMISSION_CHANGED": 403,
    "RESOURCE_NOT_FOUND": 404,
    "VERSION_CONFLICT": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "CLARIFICATION_ROUND_LIMIT_REACHED": 409,
    "DEEP_CONFIRMATION_REQUIRED": 409,
    "AI_TASK_NOT_CANCELLABLE": 409,
    "AI_TASK_NOT_RETRYABLE": 409,
    "RESULT_NOT_READY": 409,
    "RESULT_QUALITY_BLOCKED": 409,
    "STALE_TARGET": 409,
    "TRACEABILITY_INCOMPLETE": 409,
    "VALIDATION_ERROR": 422,
    "CLARIFICATION_MODE_REASON_REQUIRED": 422,
    "CLARIFICATION_ROUND_INVALID": 409,
    "RISK_ACCEPTANCE_INVALID": 422,
    "AI_QUOTA_EXCEEDED": 429,
    "QUEUE_UNAVAILABLE": 503,
    "DEPENDENCY_UNAVAILABLE": 503,
}

PHASE_A_BLOCKERS = [
    # R4 remains a candidate pending Review and the shared real-runtime Gate.
]

# Raw requirement input is the immutable user-provided source fact. Keep this
# policy in generated OpenAPI metadata so reviewers and clients can resolve
# its persisted location and hashing rule without implementation details.
RAW_INPUT_POLICY = {
    "persisted_path": "requirement_version.content_json.raw_input",
    "immutable_across_versions": True,
    "ref_content_hash": "sha256(utf8(raw_input))",
}


SPRINT2_SCHEMAS: dict[str, dict[str, Any]] = {
    "ClarificationMode": {
        "type": "string",
        "enum": ["auto", "standard", "deep", "skip"],
    },
    "RequirementDimension": {"type": "string", "enum": REQUIREMENT_DIMENSIONS},
    "AiTaskStatus": {"type": "string", "enum": TASK_STATUSES},
    "AiResultStatus": {"type": "string", "enum": RESULT_STATUSES},
    "AiResultKind": {"type": "string", "enum": RESULT_KINDS},
    "RequirementSourceType": {"type": "string", "enum": REQUIREMENT_SOURCE_TYPES},
    "RequirementPriority": {"type": "string", "enum": REQUIREMENT_PRIORITIES},
    "RequirementStatus": {"type": "string", "enum": REQUIREMENT_STATUSES},
    "VersionConfirmationStatus": {"type": "string", "enum": VERSION_CONFIRMATION_STATUSES},
    "ConfirmationGateResult": {"type": "string", "enum": CONFIRMATION_GATE_RESULTS},
    "CompletenessStatus": {"type": "string", "enum": COMPLETENESS_STATUSES},
    "ComplexityBand": {"type": "string", "enum": COMPLEXITY_BANDS},
    "FinishReason": {"type": "string", "enum": FINISH_REASONS},
    "RiskImpact": {"type": "string", "enum": RISK_IMPACTS},
    "ModificationIntensity": {"type": "string", "enum": MODIFICATION_INTENSITIES},
    "AdoptionStatus": {"type": "string", "enum": ADOPTION_STATUSES},
    "SourceRef": _object(
        {
            "source_type": _string(minLength=1, maxLength=64),
            "source_id": _string(minLength=1, maxLength=128),
            "source_version_id": _string(nullable=True, minLength=1, maxLength=128),
            "content_hash": _string(pattern="^[0-9a-f]{64}$"),
            "label": _string(minLength=1, maxLength=256),
        },
        ["source_type", "source_id", "source_version_id", "content_hash", "label"],
    ),
    "ObjectRef": _object(
        {
            "object_type": _string(),
            "object_id": _string(),
            "object_version_id": _string(nullable=True),
        },
        ["object_type", "object_id", "object_version_id"],
    ),
    "VersionRef": _object(
        {
            "id": _string(),
            "version_no": _string(),
            "status": _string(),
            "content_hash": _string(pattern="^[0-9a-f]{64}$"),
            "created_at": _string(format="date-time"),
        },
        ["id", "version_no", "status", "content_hash", "created_at"],
    ),
    "RiskAcceptance": _object(
        {
            "missing_item_code": _string(),
            "impact": {"$ref": "#/components/schemas/RiskImpact"},
            "reason": _string(minLength=1),
        },
        ["missing_item_code", "impact", "reason"],
    ),
    "RequirementBaselineDimension": _object(
        {
            "confirmed_facts": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
            "source_refs": {
                "type": "array",
                "uniqueItems": True,
                "items": {"$ref": "#/components/schemas/SourceRef"},
            },
            "deferred_items": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
            "not_applicable_items": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
        },
        ["confirmed_facts", "source_refs", "deferred_items", "not_applicable_items"],
    ),
    "RequirementBaseline": _object(
        {
            "dimensions": _object(
                {
                    dimension: {"$ref": "#/components/schemas/RequirementBaselineDimension"}
                    for dimension in REQUIREMENT_DIMENSIONS
                },
                REQUIREMENT_DIMENSIONS,
            ),
            "assumptions": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
            "unresolved_items": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
        },
        ["dimensions", "assumptions", "unresolved_items"],
    ),
    "ClarificationDimensions": _object(
        {
            dimension: {
                "$ref": "#/components/schemas/ClarificationDimensionStatus"
            }
            for dimension in REQUIREMENT_DIMENSIONS
        },
        REQUIREMENT_DIMENSIONS,
    ),
    "ClarificationDimensionStatus": _object(
        {
            "status": {"$ref": "#/components/schemas/CompletenessStatus"},
            "missing_items": {"type": "array", "items": _string()},
            "source_refs": {"type": "array", "items": {"$ref": "#/components/schemas/SourceRef"}},
        },
        ["status", "missing_items", "source_refs"],
    ),
    "ClarificationAssessment": _object(
        {
            "assessment_version": _string(),
            "dimensions": {"$ref": "#/components/schemas/ClarificationDimensions"},
            "complexity_band": {"$ref": "#/components/schemas/ComplexityBand"},
            "complexity_reason": _string(),
            "recommended_mode": {"$ref": "#/components/schemas/ClarificationMode"},
            "missing_dimensions": {
                "type": "array",
                "uniqueItems": True,
                "items": {"$ref": "#/components/schemas/RequirementDimension"},
            },
            "source_refs": {"type": "array", "items": {"$ref": "#/components/schemas/SourceRef"}},
            "ai_result_id": _string(),
        },
        [
            "assessment_version",
            "dimensions",
            "complexity_band",
            "complexity_reason",
            "recommended_mode",
            "missing_dimensions",
            "source_refs",
            "ai_result_id",
        ],
    ),
    "ClarificationQuestion": _object(
        {
            "question_id": _string(),
            "dimension": {"$ref": "#/components/schemas/RequirementDimension"},
            "question_text": _string(minLength=1),
            "reason": _string(minLength=1),
            "source_refs": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/SourceRef"},
            },
        },
        ["question_id", "dimension", "question_text", "reason", "source_refs"],
    ),
    "ClarificationAnswer": _object(
        {"question_id": _string(), "answer": _string()},
        ["question_id", "answer"],
    ),
    "ClarificationRound": _object(
        {
            "round_no": {"type": "integer", "minimum": 1, "maximum": 5},
            "ai_task_id": _string(),
            "ai_result_id": _string(),
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"$ref": "#/components/schemas/ClarificationQuestion"},
            },
            "answers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"$ref": "#/components/schemas/ClarificationAnswer"},
            },
        },
        ["round_no", "ai_task_id", "ai_result_id", "questions", "answers"],
    ),
    "RequirementContent": _object(
        {
            "raw_input": _string(minLength=1, readOnly=True),
            "raw_input_ref": {"$ref": "#/components/schemas/SourceRef", "readOnly": True},
            "clarification": _object(
                {
                    "mode": {"$ref": "#/components/schemas/ClarificationMode"},
                    "assessment": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/ClarificationAssessment"},
                            {"type": "null"},
                        ]
                    },
                    "assessment_ref": {
                        "oneOf": [{"$ref": "#/components/schemas/ObjectRef"}, {"type": "null"}],
                        "readOnly": True,
                    },
                    "assessment_summary": _string(nullable=True),
                    "rounds": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {"$ref": "#/components/schemas/ClarificationRound"},
                    },
                    "finish_reason": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/FinishReason"},
                            {"type": "null"},
                        ],
                    },
                    "continue_deep_confirmed": {
                        "type": "boolean",
                        "description": "Explicit owner confirmation persisted before deep round four; absent legacy values normalize to false.",
                    },
                },
                ["mode", "assessment", "assessment_ref", "assessment_summary", "rounds", "finish_reason"],
            ),
            "baseline": {"$ref": "#/components/schemas/RequirementBaseline"},
        },
        ["raw_input", "raw_input_ref", "clarification", "baseline"],
    ),
    "RequirementVersion": _object(
        {
            "id": _string(),
            "requirement_id": _string(),
            "source_version_id": _string(nullable=True),
            "version_no": _string(),
            "content_format": _string(),
            "content_json": {"$ref": "#/components/schemas/RequirementContent"},
            "content_hash": _string(pattern="^[0-9a-f]{64}$"),
            "confirmation_status": {"$ref": "#/components/schemas/VersionConfirmationStatus"},
            "unresolved_count": {"type": "integer", "minimum": 0},
            "risk_acceptances": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/RiskAcceptance"},
            },
            "created_from_ai_result_id": _string(nullable=True),
            "is_effective": {"type": "boolean"},
            "created_at": _string(format="date-time"),
        },
        [
            "id",
            "requirement_id",
            "source_version_id",
            "version_no",
            "content_format",
            "content_json",
            "content_hash",
            "confirmation_status",
            "unresolved_count",
            "risk_acceptances",
            "created_from_ai_result_id",
            "is_effective",
            "created_at",
        ],
        additional_properties=False,
    ),
    "RequirementSummary": _object(
        {
            "id": _string(),
            "project_version_id": _string(),
            "title": _string(),
            "source_type": {"$ref": "#/components/schemas/RequirementSourceType"},
            "priority": {"$ref": "#/components/schemas/RequirementPriority"},
            "status": {"$ref": "#/components/schemas/RequirementStatus"},
            "current_version_id": _string(nullable=True),
            "effective_version_id": _string(nullable=True),
            "updated_at": _string(format="date-time"),
            "version": {"type": "integer", "minimum": 1},
        },
        [
            "id",
            "project_version_id",
            "title",
            "source_type",
            "priority",
            "status",
            "current_version_id",
            "effective_version_id",
            "updated_at",
            "version",
        ],
    ),
    "RequirementData": _object(
        {
            "requirement": {"$ref": "#/components/schemas/RequirementSummary"},
            "current_version": {
                "oneOf": [
                    {"$ref": "#/components/schemas/RequirementVersion"},
                    {"type": "null"},
                ]
            },
            "effective_version": {
                "oneOf": [
                    {"$ref": "#/components/schemas/RequirementVersion"},
                    {"type": "null"},
                ]
            },
            "permissions": {"$ref": "#/components/schemas/PermissionSummary"},
        },
        ["requirement", "current_version", "effective_version", "permissions"],
    ),
    "RequirementResponse": _envelope("RequirementData"),
    "RequirementVersionResponse": _envelope("RequirementVersion"),
    "RequirementListData": _object(
        {
            "items": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/RequirementSummary"},
            },
            "next_cursor": _string(nullable=True),
            "has_more": {"type": "boolean"},
        },
        ["items", "next_cursor", "has_more"],
    ),
    "RequirementListResponse": _envelope("RequirementListData"),
    "CreateRequirementRequest": _object(
        {
            "title": _string(minLength=1, maxLength=200),
            "raw_input": _string(minLength=1),
            "source_refs": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/SourceRef"},
            },
        },
        ["title", "raw_input", "source_refs"],
    ),
    "ReviseRequirementVersionRequest": _object(
        {
            "title": _string(minLength=1, maxLength=200),
            "content_json": {"$ref": "#/components/schemas/RequirementContent"},
            "risk_acceptances": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/RiskAcceptance"},
            },
            "expected_version": {"type": "integer", "minimum": 1},
        },
        ["expected_version"],
    ),
    "CreateRequirementVersionRequest": _object(
        {
            "source_version_id": _string(nullable=True),
            "content_json": {"$ref": "#/components/schemas/RequirementContent"},
            "source_refs": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/SourceRef"},
            },
            "change_note": _string(minLength=1),
        },
        ["content_json", "source_refs", "change_note"],
    ),
    "SetClarificationModeRequest": _object(
        {
            "mode": {"$ref": "#/components/schemas/ClarificationMode"},
            "reason": _string(nullable=True),
            "expected_version": {"type": "integer", "minimum": 1},
        },
        ["mode", "expected_version"],
    ),
    "SubmitClarificationAnswersRequest": _object(
        {
            "round_no": {"type": "integer", "minimum": 1, "maximum": 5},
            "answers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"$ref": "#/components/schemas/ClarificationAnswer"},
            },
            "finish_now": {"type": "boolean"},
            "continue_deep_confirmed": {"type": "boolean"},
            "expected_version": {"type": "integer", "minimum": 1},
        },
        ["round_no", "answers", "finish_now", "continue_deep_confirmed", "expected_version"],
    ),
    "ClarificationAnswerData": _object(
        {
            "requirement_version": {"$ref": "#/components/schemas/RequirementVersion"},
            "task_creation": {
                "type": "object",
                "additionalProperties": False,
                "required": ["decoupled", "create_operation"],
                "properties": {
                    "decoupled": {"type": "boolean", "const": True},
                    "create_operation": {"type": "string", "const": "POST /api/v1/ai/tasks"},
                },
            },
            "baseline_candidate_ref": {
                "oneOf": [{"$ref": "#/components/schemas/ObjectRef"}, {"type": "null"}]
            },
        },
        ["requirement_version", "task_creation", "baseline_candidate_ref"],
    ),
    "ClarificationAnswerResponse": _envelope("ClarificationAnswerData"),
    "ConfirmRequirementVersionRequest": _object(
        {
            "expected_version": {"type": "integer", "minimum": 1},
            "risk_acceptances": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/RiskAcceptance"},
            },
        },
        ["expected_version", "risk_acceptances"],
    ),
    "ConfirmRequirementData": _object(
        {
            "effective_version": {"$ref": "#/components/schemas/RequirementVersion"},
            "gate_result": {"$ref": "#/components/schemas/ConfirmationGateResult"},
        },
        ["effective_version", "gate_result"],
    ),
    "ConfirmRequirementResponse": _envelope("ConfirmRequirementData"),
    "TaskTarget": _object(
        {
            "object_type": {"type": "string", "const": "requirement"},
            "object_id": _string(),
            "object_version_id": _string(),
        },
        ["object_type", "object_id", "object_version_id"],
    ),
    "ClarificationTaskInput": _object(
        {
            "mode": {"$ref": "#/components/schemas/ClarificationMode"},
            "round_no": {"type": "integer", "minimum": 0, "maximum": 5},
            "continue_deep_confirmed": {"type": "boolean"},
        },
        ["mode", "round_no", "continue_deep_confirmed"],
    ),
    "RequirementClarifyTaskEnvelope": _object(
        {
            "schema_version": {"type": "string", "const": "0.2.0"},
            "task_public_id": _string(),
            "user_id": _string(),
            "project_id": _string(),
            "project_version_id": _string(),
            "module": {"type": "string", "const": "product_design"},
            "task_type": {"type": "string", "const": "requirement.clarify"},
            "target": {"$ref": "#/components/schemas/TaskTarget"},
            "target_snapshot_hash": _string(pattern="^[0-9a-f]{64}$"),
            "source_ref_ids": {"type": "array", "minItems": 1, "uniqueItems": True, "items": _string()},
            "capability_selection": {"type": ["object", "null"], "additionalProperties": True},
            "risk_acceptances": {"type": "array", "items": {"$ref": "#/components/schemas/RiskAcceptance"}},
            "command_id": _string(),
            "trace_id": _string(),
            "requested_at": _string(format="date-time"),
            "input": {"$ref": "#/components/schemas/ClarificationTaskInput"},
        },
        [
            "schema_version", "task_public_id", "user_id", "project_id", "project_version_id",
            "module", "task_type", "target", "target_snapshot_hash", "source_ref_ids",
            "capability_selection", "risk_acceptances", "command_id", "trace_id", "requested_at", "input",
        ],
    ),
    "AiTaskEnvelope": {"$ref": "#/components/schemas/RequirementClarifyTaskEnvelope"},
    "CreateAiTaskRequest": _object(
        {
            "task_type": {"type": "string", "const": "requirement.clarify"},
            "target": {"$ref": "#/components/schemas/TaskTarget"},
            "source_ref_ids": {"type": "array", "minItems": 1, "uniqueItems": True, "items": _string()},
            "user_instruction": _string(nullable=True),
            "capability_selection": {"type": ["object", "null"], "additionalProperties": True},
            "risk_acceptances": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/RiskAcceptance"},
            },
        },
        ["task_type", "target", "source_ref_ids"],
    ),
    "AiTaskResultRef": _object(
        {
            "result_id": _string(),
            "status": {"$ref": "#/components/schemas/AiResultStatus"},
            "target_snapshot_hash": _string(pattern="^[0-9a-f]{64}$"),
        },
        ["result_id", "status", "target_snapshot_hash"],
    ),
    "AiTaskSummary": _object(
        {
            "task_id": _string(),
            "task_public_id": _string(format="uuid"),
            "status": {"$ref": "#/components/schemas/AiTaskStatus"},
            "task_type": {"type": "string", "const": "requirement.clarify"},
            "created_by_user_id": _string(),
            "queued_at": _string(format="date-time"),
            "target_snapshot_hash": _string(pattern="^[0-9a-f]{64}$"),
            "capability_summary": {"type": "object", "additionalProperties": True},
            "missing_items": {"type": "array", "items": _string()},
            "result_refs": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/AiTaskResultRef"},
            },
            "events_url": _string(format="uri-reference"),
            "poll_url": _string(format="uri-reference"),
        },
        [
            "task_id",
            "task_public_id",
            "status",
            "task_type",
            "created_by_user_id",
            "queued_at",
            "target_snapshot_hash",
            "capability_summary",
            "missing_items",
            "result_refs",
            "events_url",
            "poll_url",
        ],
    ),
    "AiTaskResponse": _envelope("AiTaskSummary"),
    "AiTaskListData": _object(
        {
            "items": {"type": "array", "items": {"$ref": "#/components/schemas/AiTaskSummary"}},
            "next_cursor": _string(nullable=True),
            "has_more": {"type": "boolean"},
        },
        ["items", "next_cursor", "has_more"],
    ),
    "AiTaskListResponse": _envelope("AiTaskListData"),
    "AiTaskCommandRequest": _object({"reason": _string(minLength=1)}, ["reason"]),
    "RetryAiTaskRequest": _object(
        {
            "reason": _string(minLength=1),
            "use_latest_target": {"type": "boolean"},
            "capability_selection": {"type": ["object", "null"], "additionalProperties": True},
        },
        ["reason", "use_latest_target"],
    ),
    "AiResultDimension": _object(
        {
            "status": {"$ref": "#/components/schemas/CompletenessStatus"},
            "reasons": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
            "missing_items": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
            "source_refs": {
                "type": "array",
                "uniqueItems": True,
                "items": {"$ref": "#/components/schemas/SourceRef"},
            },
        },
        ["status", "reasons", "missing_items", "source_refs"],
    ),
    "AiResultDimensions": _object(
        {
            dimension: {"$ref": "#/components/schemas/AiResultDimension"}
            for dimension in REQUIREMENT_DIMENSIONS
        },
        REQUIREMENT_DIMENSIONS,
    ),
    "AiResultConvergence": _object(
        {
            "should_finish": {"type": "boolean"},
            "finish_reason": {"type": ["string", "null"], "enum": [*FINISH_REASONS, None]},
            "next_round_no": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
        },
        ["should_finish", "finish_reason", "next_round_no"],
    ),
    "AiResultQuality": _object(
        {
            "format_status": {"type": "string", "enum": ["passed", "failed"]},
            "traceability_status": {"type": "string", "enum": ["passed", "failed", "not_applicable"]},
            "safety_status": {"type": "string", "enum": ["passed", "failed"]},
            "major_error": {"type": "boolean"},
            "blocker_codes": {
                "type": "array",
                "uniqueItems": True,
                "items": _string(minLength=1, maxLength=64),
            },
            "required_items_total": {"type": "integer", "minimum": 0},
            "required_items_met": {"type": "integer", "minimum": 0},
        },
        [
            "format_status", "traceability_status", "safety_status", "major_error",
            "blocker_codes", "required_items_total", "required_items_met",
        ],
    ),
    "AiResultAssessment": _object(
        {
            "dimension_completeness": {"$ref": "#/components/schemas/AiResultDimensions"},
            "complexity_band": {"$ref": "#/components/schemas/ComplexityBand"},
            "reasons": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
            "recommended_mode": {"$ref": "#/components/schemas/ClarificationMode"},
            "missing_items": {"type": "array", "items": _string(minLength=1, maxLength=2000)},
            "source_refs": {
                "type": "array",
                "uniqueItems": True,
                "items": {"$ref": "#/components/schemas/SourceRef"},
            },
        },
        ["dimension_completeness", "complexity_band", "reasons", "recommended_mode", "missing_items", "source_refs"],
    ),
    "AiResultBaseline": {"$ref": "#/components/schemas/RequirementBaseline"},
    "AiResultContent": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "const": "0.2.0"},
            "task_public_id": _string(minLength=1, maxLength=64),
            "task_type": {"type": "string", "const": "requirement.clarify"},
            "target_snapshot_hash": _string(pattern="^[0-9a-f]{64}$"),
            "mode": {"$ref": "#/components/schemas/ClarificationMode"},
            "round_no": {"type": "integer", "minimum": 0, "maximum": 5},
            "result_kind": {"$ref": "#/components/schemas/AiResultKind"},
            "status": {"$ref": "#/components/schemas/AiResultStatus"},
            "dimensions": {"$ref": "#/components/schemas/AiResultDimensions"},
            "assessment": {"oneOf": [{"$ref": "#/components/schemas/AiResultAssessment"}, {"type": "null"}]},
            "questions": {
                "type": "array", "maxItems": 3,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["question_id", "dimension", "question_text", "reason", "source_refs"],
                    "properties": {
                        "question_id": _string(pattern="^q-[1-9][0-9]*$"),
                        "dimension": {"$ref": "#/components/schemas/RequirementDimension"},
                        "question_text": _string(minLength=1, maxLength=1000),
                        "reason": _string(minLength=1, maxLength=2000),
                        "source_refs": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"$ref": "#/components/schemas/SourceRef"},
                        },
                    },
                },
            },
            "baseline": {"oneOf": [{"$ref": "#/components/schemas/AiResultBaseline"}, {"type": "null"}]},
            "convergence": {"$ref": "#/components/schemas/AiResultConvergence"},
            "quality": {"$ref": "#/components/schemas/AiResultQuality"},
        },
        "required": [
            "schema_version", "task_public_id", "task_type", "target_snapshot_hash", "mode", "round_no",
            "result_kind", "status", "dimensions", "assessment", "questions", "baseline", "convergence", "quality",
        ],
    },
    "AiResult": _object(
        {
            "id": _string(),
            "schema_version": {"type": "string", "const": "0.2.0"},
            "task_public_id": _string(),
            "task_type": {"type": "string", "const": "requirement.clarify"},
            "status": {"$ref": "#/components/schemas/AiResultStatus"},
            "result_kind": {"$ref": "#/components/schemas/AiResultKind"},
            "mode": {"$ref": "#/components/schemas/ClarificationMode"},
            "round_no": {"type": "integer", "minimum": 0, "maximum": 5},
            "target_snapshot_hash": _string(pattern="^[0-9a-f]{64}$"),
            "content_json": {"oneOf": [{"$ref": "#/components/schemas/AiResultContent"}, {"type": "null"}]},
            "content_summary": _string(nullable=True),
            "source_refs": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/SourceRef"},
            },
            "quality_summary": {"$ref": "#/components/schemas/AiResultQuality"},
            "convergence": {"$ref": "#/components/schemas/AiResultConvergence"},
            "capability_summary": {"type": "object", "additionalProperties": True},
        },
        [
            "id",
            "schema_version",
            "task_public_id",
            "task_type",
            "status",
            "result_kind",
            "mode",
            "round_no",
            "target_snapshot_hash",
            "content_json",
            "content_summary",
            "source_refs",
            "quality_summary",
            "convergence",
            "capability_summary",
        ],
    ),
    "AiResultResponse": _envelope("AiResult"),
    "FormalizeAiResultRequest": {
        **_object(
            {
                "adoption": {"type": "string", "enum": ["adopt", "modified_adopt", "reject"]},
                "target_object_type": {"type": "string", "const": "requirement"},
                "target_object_id": _string(),
                "target_snapshot_hash": _string(pattern="^[0-9a-f]{64}$"),
                "expected_version": {"type": "integer", "minimum": 1},
                "modified_content_json": {"type": ["object", "null"], "additionalProperties": True},
                "modification_intensity": {"$ref": "#/components/schemas/ModificationIntensity"},
                "reason": _string(nullable=True),
            },
            ["adoption", "target_object_type", "target_object_id", "target_snapshot_hash", "expected_version", "modification_intensity"],
        ),
        "oneOf": [
            {"properties": {"adoption": {"const": "adopt"}, "modified_content_json": {"type": "null"}, "modification_intensity": {"const": "none"}}, "required": ["modified_content_json"]},
            {"properties": {"adoption": {"const": "modified_adopt"}, "modified_content_json": {"type": "object", "minProperties": 1}, "modification_intensity": {"const": "minor"}}, "required": ["modified_content_json"]},
            {"properties": {"adoption": {"const": "modified_adopt"}, "modified_content_json": {"type": "object", "minProperties": 1}, "modification_intensity": {"const": "major"}, "reason": {"type": "string", "minLength": 1}}, "required": ["modified_content_json", "reason"]},
            {"properties": {"adoption": {"const": "reject"}, "modification_intensity": {"const": "none"}, "reason": {"type": "string", "minLength": 1}}, "required": ["reason"]},
        ],
    },
    "FormalizeAiResultData": _object(
        {
            "adoption_id": _string(),
            "adoption_status": {
                "type": "string",
                "enum": ADOPTION_STATUSES,
            },
            "artifact_version_ref": {
                "oneOf": [{"$ref": "#/components/schemas/VersionRef"}, {"type": "null"}]
            },
        },
        ["adoption_id", "adoption_status", "artifact_version_ref"],
    ),
    "FormalizeAiResultResponse": _envelope("FormalizeAiResultData"),
}

# Result-kind invariants are kept in the OpenAPI candidate so consumers can
# validate the same one-to-one mapping as the AI Result Content schema.
SPRINT2_SCHEMAS["AiResultContent"]["allOf"] = [
    {
        "if": {"properties": {"result_kind": {"const": "assessment"}}, "required": ["result_kind"]},
        "then": {
            "properties": {
                "assessment": {"type": "object"},
                "questions": {"maxItems": 0},
                "baseline": {"type": "null"},
            }
        },
    },
    {
        "if": {"properties": {"result_kind": {"const": "questions"}}, "required": ["result_kind"]},
        "then": {
            "properties": {
                "assessment": {"type": "null"},
                "questions": {"minItems": 1, "maxItems": 3},
                "baseline": {"type": "null"},
            }
        },
    },
    {
        "if": {"properties": {"result_kind": {"const": "baseline"}}, "required": ["result_kind"]},
        "then": {
            "properties": {
                "assessment": {"type": "null"},
                "questions": {"maxItems": 0},
                "baseline": {"type": "object"},
            }
        },
    },
    {
        "if": {
            "properties": {
                "convergence": {
                    "properties": {"should_finish": {"const": True}},
                    "required": ["should_finish"],
                }
            },
            "required": ["convergence"],
        },
        "then": {
            "properties": {
                "convergence": {
                    "properties": {
                        "finish_reason": {"type": "string"},
                        "next_round_no": {"type": "null"},
                    }
                }
            }
        },
    },
    {
        "if": {
            "properties": {
                "convergence": {
                    "properties": {"should_finish": {"const": False}},
                    "required": ["should_finish"],
                }
            },
            "required": ["convergence"],
        },
        "then": {
            "properties": {
                "convergence": {
                    "properties": {
                        "finish_reason": {"type": "null"},
                        "next_round_no": {"type": "integer", "minimum": 1, "maximum": 5},
                    }
                }
            }
        },
    },
]


SPRINT2_PATHS: dict[str, dict[str, Any]] = {
    "/api/v1/project-versions/{version_id}/requirements": {
        "get": _operation(
            "listRequirements",
            "requirements",
            "RequirementListResponse",
            parameters=[
                VERSION_ID,
                {"$ref": "#/components/parameters/Cursor"},
                _parameter("status", location="query", required=False),
            ],
        ),
        "post": _operation(
            "createRequirement",
            "requirements",
            "RequirementResponse",
            request_schema="CreateRequirementRequest",
            parameters=[VERSION_ID],
            idempotent=True,
            description=(
                "Persists raw_input unchanged at "
                "requirement_version.content_json.raw_input. Subsequent Requirement "
                "Versions inherit raw_input and cannot modify it."
            ),
            blockers=["permission", "transaction", "event"],
        ),
    },
    "/api/v1/requirements/{requirement_id}": {
        "get": _operation(
            "getRequirement",
            "requirements",
            "RequirementResponse",
            parameters=[REQUIREMENT_ID],
        )
    },
    "/api/v1/requirement-versions/{version_id}": {
        "patch": _operation(
            "reviseRequirementVersion",
            "requirements",
            "RequirementVersionResponse",
            request_schema="ReviseRequirementVersionRequest",
            parameters=[VERSION_ID],
            description=(
                "Creates a new immutable Requirement Version and never overwrites the addressed "
                "version; raw_input is inherited and cannot be modified."
            ),
            blockers=["permission", "idempotency", "transaction", "event"],
        )
    },
    "/api/v1/requirement-versions/{version_id}:set-clarification-mode": {
        "post": _operation(
            "setRequirementClarificationMode",
            "requirements",
            "RequirementVersionResponse",
            request_schema="SetClarificationModeRequest",
            parameters=[VERSION_ID],
            idempotent=True,
            blockers=["permission", "new_version_semantics", "transaction", "event"],
        )
    },
    "/api/v1/requirement-versions/{version_id}/clarification-answers": {
        "post": _operation(
            "submitRequirementClarificationAnswers",
            "requirements",
            "ClarificationAnswerResponse",
            request_schema="SubmitClarificationAnswersRequest",
            parameters=[VERSION_ID],
            idempotent=True,
            description="Every answer submission creates a new immutable Requirement Version.",
            blockers=["permission", "error_codes", "transaction", "event", "ai_task_acceptance"],
        )
    },
    "/api/v1/requirement-versions/{version_id}/clarification-result": {
        "get": {
            **_operation(
                "getRequirementVersionClarificationResult",
                "requirements",
                "AiResultResponse",
                parameters=[
                    VERSION_ID,
                    {
                        "name": "mode",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "enum": ["standard", "deep"]},
                    },
                    {
                        "name": "round_no",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                ],
                description=(
                    "Returns the one authoritative ready questions result for the addressed immutable "
                    "Requirement Version, clarification mode, and round. This read creates no AI Task, "
                    "performs no Provider call, and mutates no Requirement or AI result."
                ),
                blockers=["permission", "exact_target", "authoritative_result_validation"],
            ),
            "x-read-only": True,
            "x-side-effects": {
                "task_creation": False,
                "provider_call": False,
                "requirement_mutation": False,
                "result_mutation": False,
            },
        }
    },
    "/api/v1/requirements/{requirement_id}/versions": {
        "post": _operation(
            "createRequirementVersion",
            "requirements",
            "RequirementVersionResponse",
            request_schema="CreateRequirementVersionRequest",
            parameters=[REQUIREMENT_ID],
            idempotent=True,
            description=(
                "Creates a new immutable Requirement Version and preserves every prior fact; "
                "raw_input is inherited and cannot be modified."
            ),
            blockers=["permission", "transaction", "event"],
        )
    },
    "/api/v1/requirement-versions/{version_id}:confirm": {
        "post": _operation(
            "confirmRequirementVersion",
            "requirements",
            "ConfirmRequirementResponse",
            request_schema="ConfirmRequirementVersionRequest",
            parameters=[VERSION_ID],
            idempotent=True,
            blockers=["permission", "gate_result_enum", "transaction", "event"],
        )
    },
    "/api/v1/ai/tasks": {
        "get": _operation(
            "listAiTasks",
            "ai-tasks",
            "AiTaskListResponse",
            parameters=[
                _parameter("project_id", location="query", required=False),
                _parameter("status", location="query", required=False),
                {"$ref": "#/components/parameters/Cursor"},
            ],
            blockers=["permission"],
        ),
        "post": _operation(
            "createAiTask",
            "ai-tasks",
            "AiTaskResponse",
            request_schema="CreateAiTaskRequest",
            idempotent=True,
            description="Creates one traceable requirement.clarify Task; it does not call a Provider synchronously.",
            blockers=["permission", "error_codes", "task_acceptance", "transaction", "event"],
        ),
    },
    "/api/v1/ai/tasks/{task_id}": {
        "get": _operation(
            "getAiTask",
            "ai-tasks",
            "AiTaskResponse",
            parameters=[TASK_ID],
            blockers=["permission"],
        )
    },
    "/api/v1/ai/tasks/{task_id}/events": {
        "get": {
            **_operation(
                "streamAiTaskEvents",
                "ai-tasks",
                "AiTaskResponse",
                parameters=[TASK_ID, {"$ref": "#/components/parameters/LastEventId"}],
                description="SSE disconnect does not cancel the Task; clients may fall back to the Task snapshot.",
                blockers=["sse_authorization", "event_replay_error_codes"],
            ),
            "responses": {
                "200": {
                    "description": "AI Task event stream",
                    "content": {
                        "text/event-stream": {
                            "schema": {"type": "string"},
                            "x-event-types": [
                                "task.snapshot",
                                "task.status",
                                "task.warning",
                                "task.result",
                                "task.terminal",
                                "heartbeat",
                            ],
                        }
                    },
                }
            },
        }
    },
    "/api/v1/ai/tasks/{task_id}:cancel": {
        "post": _operation(
            "cancelAiTask",
            "ai-tasks",
            "AiTaskResponse",
            request_schema="AiTaskCommandRequest",
            parameters=[TASK_ID],
            idempotent=True,
            blockers=["permission", "eligible_states", "error_codes", "transaction", "event"],
        )
    },
    "/api/v1/ai/tasks/{task_id}:retry": {
        "post": _operation(
            "retryAiTask",
            "ai-tasks",
            "AiTaskResponse",
            request_schema="RetryAiTaskRequest",
            parameters=[TASK_ID],
            idempotent=True,
            description="Creates a new Task and never overwrites a failed, cancelled or expired Task fact.",
            blockers=["permission", "eligible_states", "error_codes", "transaction", "event"],
        )
    },
    "/api/v1/ai/results/{result_id}": {
        "get": _operation(
            "getAiResult",
            "ai-results",
            "AiResultResponse",
            parameters=[RESULT_ID],
            blockers=["permission", "result_status_and_quality_enums"],
        )
    },
    "/api/v1/ai/results/{result_id}:formalize": {
        "post": _operation(
            "formalizeAiResult",
            "ai-results",
            "FormalizeAiResultResponse",
            request_schema="FormalizeAiResultRequest",
            parameters=[RESULT_ID],
            idempotent=True,
            description="Ready is only a candidate. Formalization preserves old facts on failure or stale target.",
            blockers=["permission", "error_codes", "target_object_enum", "transaction", "event"],
        )
    },
}


def install_sprint2_contract(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    components.setdefault("parameters", {})["LastEventId"] = {
        "name": "Last-Event-ID",
        "in": "header",
        "required": False,
        "schema": _string(),
    }
    components.setdefault("schemas", {}).update(deepcopy(SPRINT2_SCHEMAS))
    components["schemas"]["Sprint2ErrorCode"] = {
        "type": "string", "enum": sorted(ERROR_HTTP_MAPPING),
    }
    components["schemas"]["Sprint2ErrorResponse"] = {
        "type": "object", "additionalProperties": False,
        "required": ["code", "message", "details", "trace_id"],
        "properties": {
            "code": {"$ref": "#/components/schemas/Sprint2ErrorCode"},
            "message": {"type": "string"},
            "details": {"type": "array", "items": {"$ref": "#/components/schemas/FieldError"}},
            "trace_id": {"type": "string"},
        },
    }
    event_payloads = {
        "RequirementClarificationAssessedPayload": ["assessment_version", "complexity_band", "recommended_mode", "missing_dimensions"],
        "RequirementClarificationModeSelectedPayload": ["selected_mode", "recommended_mode", "is_override", "reason_code"],
        "RequirementClarificationRoundCompletedPayload": ["round_no", "question_count", "answered_count", "remaining_rounds"],
        "RequirementClarificationFinishedPayload": ["finish_reason", "round_count", "unresolved_count", "baseline_hash"],
        "ArtifactDraftSavedPayload": ["artifact_type", "draft_version_id", "content_hash"],
        "ArtifactVersionFormalizedPayload": ["artifact_type", "formal_version_id", "source_ai_result_id"],
    }
    for name, fields in event_payloads.items():
        components["schemas"][name] = {
            "type": "object", "additionalProperties": False,
            "required": fields,
            "properties": {
                field: ({"type": "array", "items": {"$ref": "#/components/schemas/RequirementDimension"}} if field == "missing_dimensions" else
                         {"type": "integer", "minimum": 0} if field in {"round_no", "question_count", "answered_count", "remaining_rounds", "round_count", "unresolved_count"} else
                         {"type": "boolean"} if field == "is_override" else
                         {"type": "string", "pattern": "^[0-9a-f]{64}$"} if field in {"content_hash", "baseline_hash"} else
                         {"type": "string"})
                for field in fields
            },
        }
    components["schemas"]["ArtifactVersionFormalizedPayload"]["properties"]["formal_version_id"] = {
        "type": "string",
        "description": "Requirement Version identifier for the newly formalized version",
    }
    event_fields = [
        "schema_version", "event_id", "event_name", "occurred_at", "producer", "module",
        "result_status", "source_type", "privacy_class", "user_id", "project_id",
        "project_version_id", "object_type", "object_id", "object_version_id", "trace_id",
        "command_id", "payload_json",
    ]
    components["schemas"]["RequirementEventEnvelope"] = {
        "type": "object", "additionalProperties": False,
        "required": event_fields,
        "properties": {
            "schema_version": {"type": "string", "const": "0.2.0"},
            "event_id": _string(), "event_name": {"type": "string"},
            "occurred_at": _string(format="date-time"), "producer": {"type": "string", "const": "Business API"},
            "module": {"type": "string", "const": "product_design"}, "result_status": {"type": "string"},
            "source_type": {"type": "string"}, "privacy_class": {"type": "string"},
            "user_id": _string(), "project_id": _string(), "project_version_id": _string(),
            "object_type": {"type": "string", "const": "requirement"}, "object_id": _string(),
            "object_version_id": _string(), "trace_id": _string(), "command_id": _string(),
            "payload_json": {"type": "object"},
        },
    }
    components.setdefault("responses", {})
    for status in ("401", "403", "404", "409", "422", "429", "503"):
        components["responses"][f"Sprint2Error{status}"] = {
            "description": f"Sprint 2 error ({status})",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Sprint2ErrorResponse"}}},
            "x-http-status": int(status),
            "x-error-codes": [code for code, code_status in ERROR_HTTP_MAPPING.items() if code_status == int(status)],
        }
    for path, path_item in SPRINT2_PATHS.items():
        if path in schema.setdefault("paths", {}):
            raise RuntimeError(f"Sprint 2 contract path already exists: {path}")
        schema["paths"][path] = deepcopy(path_item)

    schema["x-raw-input-policy"] = deepcopy(RAW_INPUT_POLICY)
    create_requirement_operation = schema["paths"][
        "/api/v1/project-versions/{version_id}/requirements"
    ]["post"]
    create_requirement_operation["x-raw-input-policy"] = deepcopy(RAW_INPUT_POLICY)

    owner_ops = {
        "createRequirement", "reviseRequirementVersion", "setRequirementClarificationMode",
        "submitRequirementClarificationAnswers", "createRequirementVersion", "confirmRequirementVersion",
        "createAiTask", "formalizeAiResult",
    }
    transaction_boundaries = {
        "createRequirement": "identity+initial_version+audit+idempotency+business_outbox",
        "reviseRequirementVersion": "new_version+audit+business_outbox",
        "setRequirementClarificationMode": "new_version+audit+business_outbox",
        "submitRequirementClarificationAnswers": "answer_version+audit+business_outbox; ai_task_creation_decoupled",
        "createRequirementVersion": "new_version+audit+business_outbox",
        "confirmRequirementVersion": "effective_version+pointer+audit+business_outbox",
        "createAiTask": "task+idempotency+audit; queue_acceptance_not_false_success",
        "cancelAiTask": "cancel_command+audit+ai_event",
        "retryAiTask": "new_task+retry_of+audit+ai_event",
        "formalizeAiResult": "new_requirement_version+adoption+audit+idempotency+business_outbox",
    }
    for path in SPRINT2_PATHS:
        for operation in schema["paths"][path].values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operation_id = operation["operationId"]
            if operation_id in owner_ops:
                operation["x-permissions"] = {"allowed_project_roles": ["owner"], "admin_bypass": False}
            elif operation_id in {"cancelAiTask", "retryAiTask"}:
                operation["x-permissions"] = {
                    "allowed_project_roles": ["owner"],
                    "additional_actor_predicate": "task_initiator",
                    "admin_bypass": False,
                }
            else:
                operation["x-permissions"] = {
                    "allowed_project_roles": ["owner", "reviewer", "implementer", "tester"],
                    "admin_bypass": False,
                }
            operation["x-permission"] = operation["x-permissions"]
            operation["x-error-http-mapping"] = ERROR_HTTP_MAPPING
            operation["x-command-semantics"] = {
                "actor": "owner_or_task_initiator" if operation_id in {"cancelAiTask", "retryAiTask"} else (
                    "owner" if operation_id in owner_ops else "project_member_with_target_read_permission"
                ),
                "admin_bypass": False,
                "queue_unavailable_no_false_queued": operation_id == "createAiTask",
            }
            if operation_id in transaction_boundaries:
                operation["x-transaction-boundary"] = transaction_boundaries[operation_id]
                operation["x-transaction"] = {
                    "boundary": transaction_boundaries[operation_id],
                    "atomic": True,
                    "audit_required": True,
                    "outbox_required": True,
                    "task_creation_decoupled": operation_id == "submitRequirementClarificationAnswers",
                }
            if operation_id == "formalizeAiResult":
                operation["x-formalize-branches"] = {
                    "adopt": {"creates_requirement_version": True, "adoption_status": "adopted"},
                    "modified_adopt": {"creates_requirement_version": True, "adoption_status": "adopted_after_edit", "requires_content": True, "major_requires_reason": True},
                    "reject": {"creates_requirement_version": False, "adoption_status": "rejected", "requires_reason": True},
                    "shared_transaction": ["idempotency", "audit", "business_outbox"],
                }
            operation["responses"].update({
                status: {"$ref": f"#/components/responses/Sprint2Error{status}"}
                for status in ("401", "403", "404", "409", "422", "429", "503")
            })
            if operation_id == "streamAiTaskEvents":
                operation["x-sse-authorization"] = {
                    "recheck": ["connect", "before_each_event", "before_heartbeat"],
                    "on_revocation": "close_connection_without_body; subsequent_poll=PERMISSION_CHANGED",
                }
            if operation_id == "createAiTask":
                operation["x-command-envelope"] = {
                    "ref": "#/components/schemas/RequirementClarifyTaskEnvelope",
                    "derived_input": "Business API derives and validates input from target Requirement Version; frontend input is not trusted",
                    "excluded_from_public_request": ["user_id", "command_id", "trace_id", "requested_at", "project_id", "project_version_id", "module", "input"],
                }

    schema["x-error-http-mapping"] = ERROR_HTTP_MAPPING
    schema["x-task-command-policy"] = {
        "create": {"task_type": "requirement.clarify", "allowed_project_roles": ["owner"]},
        "cancel": {
            "from": ["prechecking", "queued", "preparing", "generating", "checking"],
            "to": "cancel_requested",
            "terminal_rejection": "AI_TASK_NOT_CANCELLABLE",
        },
        "retry": {
            "from": ["blocked", "partial_result", "quality_blocked", "cancelled", "failed", "expired", "stale_target"],
            "creates_new_task": True,
            "retry_of_task_id": True,
            "terminal_rejection": "AI_TASK_NOT_RETRYABLE",
        },
        "ready_regeneration": "create",
    }
    schema["x-requirement-events"] = {
        "schema_version": "0.2.0",
        "producer": "Business API",
        "outbox_transactional": True,
        "envelope_excludes": ["ingested_at"],
        "events": {
            "requirement.clarification.assessed": {
                "fact": "assessment_result_reference_written_to_requirement_version",
                "payload": ["assessment_version", "complexity_band", "recommended_mode", "missing_dimensions"],
            },
            "requirement.clarification.mode_selected": {
                "fact": "new_requirement_version_and_mode_committed",
                "payload": ["selected_mode", "recommended_mode", "is_override", "reason_code"],
            },
            "requirement.clarification.round_completed": {
                "fact": "answer_requirement_version_committed",
                "payload": ["round_no", "question_count", "answered_count", "remaining_rounds"],
            },
            "requirement.clarification.finished": {
                "fact": "baseline_candidate_reference_or_content_committed",
                "payload": ["finish_reason", "round_count", "unresolved_count", "baseline_hash"],
            },
            "artifact.draft.saved": {
                "fact": "new_requirement_version_committed",
                "payload": ["artifact_type", "draft_version_id", "content_hash"],
            },
            "artifact.version.formalized": {
                "fact": "effective_version_and_adoption_committed",
                "payload": ["artifact_type", "formal_version_id", "source_ai_result_id"],
            },
        },
        "adoption_events": {
            "ai.result.adopted": "adopted",
            "ai.result.adopted_after_edit": "adopted_after_edit",
            "ai.result.rejected": "rejected",
            "ai.result.left_unreviewed": "emitted_when_review_is_explicitly_closed_without_adoption; analytics_status=not_reviewed",
        },
    }
    payload_schema_by_event = {
        "requirement.clarification.assessed": "RequirementClarificationAssessedPayload",
        "requirement.clarification.mode_selected": "RequirementClarificationModeSelectedPayload",
        "requirement.clarification.round_completed": "RequirementClarificationRoundCompletedPayload",
        "requirement.clarification.finished": "RequirementClarificationFinishedPayload",
        "artifact.draft.saved": "ArtifactDraftSavedPayload",
        "artifact.version.formalized": "ArtifactVersionFormalizedPayload",
    }
    for event_name, schema_name in payload_schema_by_event.items():
        schema["x-requirement-events"]["events"][event_name]["payload_schema"] = f"#/components/schemas/{schema_name}"

    schema["x-sprint-2-phase-a"] = {
        "task_package": "M2-S2-REQ-CLARIFY-20260805-R1",
        "candidate_version": "R4",
        "status": "pending_review",
        "implementation_authorized": True,
        "migration_change": "none",
        "scope": ["BE-201", "BE-203", "BE-204"],
        "x-deferred-scope": [
            "BE-202",
            "project-file-list",
            "file-relation-enums",
            "csrf-delivery",
        ],
        "feature_flags": {
            "persistence_adapter_enabled": False,
            "flow_enabled": False,
        },
        "clarification_round_policy": {
            "standard_max_rounds": 3,
            "deep_max_rounds": 5,
            "deep_reconfirmation_before_round": 4,
            "questions_per_round_min": 1,
            "questions_per_round_max": 3,
            "converge_on": ["round_limit", "user_finished", "no_new_high_value_question"],
        },
        "ai_result_policy": {
            "ready_is_formal": False,
            "request_to_persistence_adoption_mapping": {
                "adopt": "adopted",
                "modified_adopt": "adopted_after_edit",
                "reject": "rejected",
                "no_adoption_record": "not_reviewed",
            },
            "not_reviewed_is_derived_only": True,
        },
    }
