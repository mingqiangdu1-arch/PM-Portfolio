# DATA-001/DATA-101 event and record mapping candidate 0.1.3

Status: candidate after Review feedback; not frozen.

| Formal field/concept | Candidate JSON field | Producer/consumer rule |
| --- | --- | --- |
| Schema version | `schema_version` | Producer writes `0.1.3`; breaking changes require Review. |
| Unique deduplication key | `event_id` | Producer creates once; consumer deduplicates on this field. |
| Canonical name | `event_name` | Must use the confirmed `ai.task.*`, `ai.call.*`, `ai.context.selected`, or `ai.result.*` name. |
| Fact time | `occurred_at` | Producer time in UTC. |
| Ingestion time | `ingested_at` | Consumer-owned; deliberately rejected by the producer envelope Schema. |
| Ownership | `module`, `source_type` | `module` is at most 32 characters. AI API uses `ai_service`; worker uses `worker`. Component detail belongs in `payload_json.producer_component`. |
| Outcome | `result_status` | Only `success/failed/partial/cancelled/blocked/expired`; AI Task state belongs in `payload_json.task_status`. |
| Privacy | `privacy_class` | Only `internal_id/pseudonymous/confidential/restricted`; no raw secrets or full context. |
| Business relation | `project_id`, `project_version_id`, object fields | Optional only where applicable; validated against authoritative IDs by the consumer. |
| AI relation | `ai_task_id`, `ai_call_id`, `ai_result_id` | Uses durable MySQL facts, never Celery result state. |
| Trace chain | `trace_id`, `command_id`, `correlation_id`, `causation_id` | Propagated when applicable. |
| Transport hint | `idempotency_key` | Optional; maps to `idempotency_record`/command tracking and never replaces `event_id`. |
| Safe body | `payload_json` | Minimal non-sensitive facts only. |

## Sprint 1 event mapping

`sprint1-business-event.schema.json` contains the Review-accepted Identity names and formal Project/Version/File facts. Every behavior event uses one globally unique `event_id`. `operation_audit_log` remains the separate authoritative AU fact, uses its database `id` plus `trace_id/command_id`, and does not gain an invented `audit_id` or a behavior-event projection.

| Domain | Producer | Consumer | Canonical names / status |
| --- | --- | --- | --- |
| Project | Business API transaction + `business_event_outbox` | Event Consumer → `behavior_event` | `project.project.created/create_failed/archived/restored`; formal. |
| Project Version | Business API transaction + Outbox | Event Consumer → `behavior_event` | `project.version.created/derived/derive_failed/working_set/startup_selected`; formal. |
| File | Business API transaction + Outbox | Event Consumer → `behavior_event` | `file.upload.started/completed/failed`; formal. |
| Identity | Business API authentication transaction + Outbox | Event Consumer → `behavior_event`; security audit remains separate | `identity.user.registered`, `identity.session.login_succeeded/login_failed/refreshed/refresh_replay_blocked/logged_out/revoked`; Review accepted. Failed events require `failure_code`; payload forbids email, password, Token, Cookie, IP and complete UA. |
| Audit | Business API critical transaction | Direct `operation_audit_log` quality queries | AU stays separate from `behavior_event`; correlate with BF through `trace_id/command_id`. Do not emit `audit.operation.recorded`. |

`user_id`, `session_id`, `failure_code`, `product_release`, `client_version`, and `ai_capability_versions_json` are now represented as optional formal envelope fields. A failed event requires non-empty `failure_code`. `ingested_at` remains consumer-owned and is intentionally absent from producer JSON.

## Record mappings

- `operation-audit.schema.json` maps to existing `operation_audit_log`; `object_type` is always a stable non-empty type such as `health_check`, while `object_id` and `object_version_id` may be null. It does not propose a new table or an independent audit UUID.
- `event-compensation.schema.json` maps approved correction/supersession/redaction records. It does not model delivery attempts or dead-letter state and never mutates the original event.
- `ai-context-usage.schema.json` persists only confirmed columns including `retrieval_method`, `was_injected`, `content_fingerprint`, and `content_summary`. Runtime `source_role` and `content_ref` remain non-persistent Context assembly fields and are deliberately absent from this Schema.
- `ai-result.schema.json` uses `content_ref` and `format_status`; every result remains a candidate until the business API formalizes it through an authorized action.
