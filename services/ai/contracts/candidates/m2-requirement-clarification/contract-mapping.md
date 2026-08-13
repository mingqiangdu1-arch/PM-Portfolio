# Requirement clarification R3 contract mapping

Bundle marker: `candidate_version=0.2.0-proposed`, `status=ready_for_review`.
The schemas identify the proposed target contract as `schema_version=0.2.0` but
remain non-effective until Review returns `m2_contracts_frozen` with hashes.

## Ownership and data flow

- Business API owns Requirement facts, derives and validates Task `input` from
  the addressed immutable Requirement Version, and creates a new Version for
  each saved answer or adopted Baseline. AI Service never overwrites a Version.
- AI Service owns AI runtime Task/Call/Context/Result facts and its existing AI
  runtime events. Every clarification round is a separate traceable Task/Result.
- AI unavailability does not remove manual input, edit, answer, Baseline, or
  confirmation paths. `ready` is an AI candidate state, not a formal Version.
- The proposed structures project onto existing Requirement Version content and
  AI traceability storage. They add no table, migration, persistence enablement,
  Provider call, or Flow behavior.

## RequirementContent and AI Result Baseline 1:1 mapping

| RequirementContent path | AI Result Content path |
|---|---|
| `baseline.dimensions.goal` | `baseline.dimensions.goal` |
| `baseline.dimensions.users_and_roles` | `baseline.dimensions.users_and_roles` |
| `baseline.dimensions.usage_scenarios` | `baseline.dimensions.usage_scenarios` |
| `baseline.dimensions.functional_scope` | `baseline.dimensions.functional_scope` |
| `baseline.dimensions.business_rules` | `baseline.dimensions.business_rules` |
| `baseline.dimensions.exception_cases` | `baseline.dimensions.exception_cases` |
| `baseline.dimensions.permission_requirements` | `baseline.dimensions.permission_requirements` |
| `baseline.dimensions.acceptance_criteria` | `baseline.dimensions.acceptance_criteria` |
| each dimension `confirmed_facts/source_refs/deferred_items/not_applicable_items` | same four fields |
| `baseline.assumptions` | `baseline.assumptions` |
| `baseline.unresolved_items` | `baseline.unresolved_items` |

`raw_input` retains the producer's original text verbatim and is required;
`raw_input` and `raw_input_ref` are both marked `readOnly=true`.
`raw_input_ref` is the same five-field `SourceRef` shape used for traceability.
`clarification` contains `mode`, nullable `assessment`, nullable `assessment_ref`
(`ObjectRef`), nullable `assessment_summary`, `rounds`, and nullable
`finish_reason`. Each round persists `round_no`, `ai_task_id`, `ai_result_id`,
`questions`, and `answers`; both question and answer arrays contain 1-3 items,
and round data is not flattened onto `clarification`. Non-null `assessment`
uses exactly the Backend `ClarificationAssessment` fields:
`assessment_version`, `dimensions`, `complexity_band`, `complexity_reason`,
`recommended_mode`, `missing_dimensions`, `source_refs`, and `ai_result_id`.
Its `dimensions` has the eight canonical keys; every dimension contains only
`status`, `missing_items`, and structured `source_refs`.
Questions use `question_id`, `dimension`, `question_text`, `reason`, and
`source_refs`; answers contain exactly `question_id` and `answer`.

Every Result/RequirementContent field named `source_refs` is a structured
`SourceRef[]`. Each item contains exactly `source_type`, `source_id`,
`source_version_id` (nullable), `content_hash` (SHA-256), and `label`. This same
shape is used by assessment dimensions, assessment summaries, questions, and
Baseline dimensions. Task Envelope `source_ref_ids[]` deliberately
remains `string[]` as a separate frozen field.

## Status and adoption mapping

- Task status is exactly the frozen 0.1.3 set, including cancellation and stale
  target states. Result status is exactly `ready|partial_result|quality_blocked|
  failed|expired|stale_target`.
- `quality_blocked`, `failed`, `expired`, and `stale_target` Results cannot be
  formalized.
- Request `adopt` persists `adopted`; `modified_adopt` persists
  `adopted_after_edit`; `reject` persists `rejected`.
- `not_reviewed` is derived only when no Adoption row exists. It is not a
  persisted adoption value and is not returned by the formalization command.
- Modification intensity is `none|minor|major`; `modified_adopt` uses
  `minor|major`, and `major` requires a reason at the Business API command gate.

## Round and convergence mapping

- `standard` has at most 3 rounds; `deep` has at most 5 rounds; deep rounds 4
  and 5 require `continue_deep_confirmed=true`; question Results contain 1-3
  questions.
- Finish reasons are `round_limit`, `user_finished`,
  `no_new_high_value_question`, `mode_skipped`, and `ai_unavailable_manual`.
  At a round limit, user finish, or no new high-value question, the candidate
  Baseline retains assumptions and unresolved items.

## Requirement business event mapping

| Event | Producer | Transaction fact | Payload |
|---|---|---|---|
| `requirement.clarification.assessed` | Business API | Assessment Result reference committed in Requirement Version | `assessment_version,complexity_band,recommended_mode,missing_dimensions` |
| `requirement.clarification.mode_selected` | Business API | new Version and mode committed | `selected_mode,recommended_mode,is_override,reason_code` |
| `requirement.clarification.round_completed` | Business API | answer Version committed | `round_no,question_count,answered_count,remaining_rounds` |
| `requirement.clarification.finished` | Business API | Baseline candidate reference/content committed | `finish_reason,round_count,unresolved_count,baseline_hash` |
| `artifact.draft.saved` | Business API | new Requirement Version committed | existing artifact payload plus Requirement Version reference |
| `artifact.version.formalized` | Business API | effective Version and Adoption committed | existing formal payload plus Requirement Version reference |

Adoption and rejection continue to use `ai.result.adopted`,
`ai.result.adopted_after_edit`, and `ai.result.rejected`. Explicitly closing an
unreviewed Result uses `ai.result.left_unreviewed`; analytics derive
`not_reviewed`. The Requirement producer schema excludes consumer-only
`ingested_at`.

## Access and transaction boundary

Requirement mutation, Task creation, risk acceptance, and candidate
formalization require the project `owner`. Reads require target-object read
permission. Task cancel/retry is available to the initiator or owner; for this
task the initiator is an owner. SSE uses the same Task-read permission and is
rechecked before connection, event delivery, and heartbeat. An `admin` role
alone grants no project-content access.

Answer saving commits independently of the next AI Task. Queue or AI failure
does not roll back the answer Version. Adoption and formalization commit the new
Version, Adoption, audit, idempotency fact, and Outbox atomically; rejection
writes no product Version.
