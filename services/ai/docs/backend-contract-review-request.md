# AI/data to backend contract review request

Status: reconciled candidate 0.1.3 after Review. No database migration, OpenAPI root, business API, or Compose file is changed here.

## Review dependencies

- Baseline: `main/eaa1f99`.
- Wave 2 requires Review confirmation that BE-001, OPS-001, and BE-003 candidates are usable.
- Backend remains the owner of business authorization, formalization, durable transaction boundaries, database migrations, and public API contracts.
- AI results remain candidates. The AI service must never promote or overwrite a formal business artifact.

## AI table and field request

Please review storage mapping and ownership for these candidate facts:

| Candidate record | Required fields or constraints | Owner/request |
| --- | --- | --- |
| `ai_task` | public/task ID, user/project/version/module, task type, target type/ID, `target_snapshot_hash`, status, trace ID, `command_id`, timestamps | Backend to confirm the minimal 77-table field change; idempotency remains authoritative in `idempotency_record`. |
| `ai_call` | task ID, sequence, provider profile, model catalog, Skill Version, Prompt Version, Template Version, context strategy version, runtime config version, capability fingerprint, provider request ID, status, token/cost fields, error class, trace, timestamps | AI runtime writes call facts; backend/Review to confirm FK/version references and retention. |
| `ai_context_usage` | call ID, source type/ID/version, role, retrieval mode, injected/excluded flag, exclusion reason, fingerprint, safe summary, token count | Store metadata only; prohibit full sensitive context. Confirm source reference resolution. |
| `ai_result` | task/call ID, target snapshot hash, candidate fingerprint, result format, storage reference, trace metadata, safety/major-error flags, candidate status | Candidate-only semantics and immutable result versions required. Backend owns any later formalization. |
| `operation_audit_log` | actor user/type, operation, object/version, result/failure/reason, trace/command, time, safe metadata | Reuse the existing audit record; do not add a parallel audit table or independent audit UUID. |
| `outbox_event` | envelope below, payload reference or safe payload, delivery state/attempts | Must be durable in the same transaction as the originating fact; Redis is not the unique fact source. |
| `event_compensation` | original/compensation event IDs, correction type, reason, replacement payload, approver | Approved correction of immutable history only; delivery attempts/dead-letter state remain outbox/ingest concerns. |

`target_snapshot_hash` and `command_id` semantics are accepted, but backend must still submit the minimal migration candidate. Routing/catalog versions and capability fingerprint remain a separate minimal persistence proposal. This window creates no migration.

The exact type, nullability, index, rollout, and degradation request for every currently missing Task/Call field is in `backend-migration-field-request.md`. No persistence adapter may silently drop those fields.

## Public event envelope candidate 0.1.3

Every event requires:

- `schema_version`, `event_id`, `event_name`, `occurred_at`, `module`, `result_status`, `source_type`, `privacy_class`, and `payload_json`;
- applicable project, object, AI Task/Call/Result, trace, command, correlation, and causation fields;
- optional `idempotency_key` only as a transport hint mapped to authoritative command/idempotency records.

`event_id` is the unique deduplication key. `ingested_at` is consumer-owned and is rejected by the producer Schema. Producers must not include secrets, raw prompts, full context, or sensitive business documents. See `event-field-mapping.md` for the canonical event names and mappings.

## Task-state alignment request

Please review this exact user-visible status set and its API/event mapping:

`prechecking`, `blocked`, `queued`, `preparing`, `generating`, `checking`, `ready`, `partial_result`, `quality_blocked`, `cancel_requested`, `cancelled`, `failed`, `expired`, `stale_target`.

Unknown duration is represented by stage state only, never a fabricated percentage. Retry creates a new Task/Call lineage. Leaving the page does not cancel. Cancellation is a request until acknowledged by the worker.

## Compose dependency review for OPS-001

The AI service requests configuration, not direct Compose changes:

- internal service names for AI API, AI worker, and Redis;
- `AI_BROKER_URL` supplied by secret/environment reference, with host, port and database selected by OPS;
- separate interactive/default queue name and worker health visibility;
- no Celery result backend as a source of truth;
- no public Redis port and no credentials in files or logs;
- API readiness that rejects new queued work when the durable task write or Redis broker is unavailable;
- graceful worker shutdown and retry/dead-letter monitoring.

The exact service commands and environment request are maintained in `compose-change-request.md`.

## Remaining Review response

Please return accepted/rejected/needs-change for each candidate field group, canonical event names and mappings, DB/FK/enum ownership, outbox transaction boundary, Redis/worker dependency names, and the usable BE-001/OPS-001/BE-003 candidate commit IDs.
