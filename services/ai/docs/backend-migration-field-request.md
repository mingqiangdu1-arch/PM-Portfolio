# Backend-accepted field contract for Schema 0.1.3

Status: backend `20260729_0001` through `20260729_0004` plus `sprint1_schema_delta.json` passed Sprint 1 Review and real MySQL 8.4.8 / MinIO integration gates. Persistence remains disabled until an explicit enablement decision. The AI/data window does not create migrations.

The following accepted AI semantics overlay the formal 77-table base catalog through the versioned migration/delta chain. Existing rows use nullable rollout columns; new-write requirements remain enforced by the AI contract where noted.

| Table | Proposed column | Candidate MySQL type | Null/backfill | Candidate index | New-write rule | Explicit degradation before migration |
| --- | --- | --- | --- | --- | --- | --- |
| `ai_task` | `target_snapshot_hash` | `CHAR(64)` ASCII | `NULL`; no historical hash fabrication | none initially | required for a task that targets a mutable artifact | Reject or `quality_blocked` when a trustworthy snapshot hash cannot be supplied; never compare against an invented hash. |
| `ai_task` | `command_id` | `VARCHAR(64)` | `NULL` for existing rows | non-unique `idx_ai_task_command_id(command_id)` | required for new task commands | Resolve through the authoritative `idempotency_record` plus event `command_id`; do not copy an idempotency key into `ai_task`. |
| `ai_call` | `capability_fingerprint` | `CHAR(64)` ASCII | `NULL`; reconstructable for old rows when all versions exist | none initially | recommended for every new Call | Recompute from Provider/Model/Skill/Prompt/Template/Context Strategy/runtime version FKs. If any input version is absent, report traceability failure instead of persisting a partial fingerprint. |
| `ai_call` | `cost_source` | `VARCHAR(32)` | `NULL` for historical calls | none | required enum `provider_reported/profile_calculated/unavailable` for new Calls | Keep provider token/cost facts in the Call contract, but do not silently discard this classification. Durable provider integration remains disabled until backend supplies an accepted column or explicit canonical metadata mapping. |
| `ai_call` | `pricing_version` | `VARCHAR(32)` | `NULL` when cost is provider-reported or unavailable | none | required when `cost_source=profile_calculated` | A calculated cost without a durable pricing version is treated as unavailable, not authoritative. |
| `ai_call` | `provider_error_class` | `VARCHAR(64)` ASCII, `ascii_bin` | `NULL` for successful or historical calls | `idx_ai_call_provider_error_class(provider_error_class, started_at, id)` | required for classified provider failures | It may map into `failure_code=provider.<class>` only when that does not overwrite another failure code; otherwise downgrade must be rejected. Never persist provider response bodies. |

## Backend-accepted constraints and trace mapping

- `cost_source` is null or one of `provider_reported/profile_calculated/unavailable`.
- `pricing_version` is required when `cost_source=profile_calculated`.
- Downgrade must reject removal when any of the six columns contains data that cannot be mapped without loss.
- `ai_call.trace_id` does not add a seventh column in this candidate. API and event output resolves it through `ai_call.ai_task_id → ai_task.trace_id`; Call writes must verify the supplied trace matches the owning Task trace.
- Provider-error indexing includes `started_at,id` to support time-bounded diagnostics and stable pagination rather than a low-selectivity single-column scan.

## Confirmed fields not requested here

Provider Profile, Model Catalog, Skill Version, Prompt Version, Template Version, Context Strategy, runtime config, token counts, estimated cost, currency, provider request ID, Call status, trace ID, and timestamps remain mapped to their confirmed fields. Runtime `source_role` and `content_ref` are not proposed as `ai_context_usage` columns in Schema 0.1.3.

## Runtime integration evidence and rollout state

The single-head overlay contains the six AI rollout columns plus the 0003 session rotation and 0004 file finalization deltas, accepted indexes/checks, no fabricated AI history, and downgrade protection. Review accepts the base catalog materialized by `0001`, plus `0002/0003/0004` and `sprint1_schema_delta.json`, as the effective versioned fact source, and accepts inherited `command_id` collation with no case conversion. Real MySQL 8.4.8 empty/existing/repeated-upgrade and downgrade tests passed, including `head → base → head → head`, 77 tables and 234 foreign keys. Real MinIO/S3 checksum, conditional-copy, storage-version and final-key isolation tests also passed. The persistence Adapter remains disabled pending a separate enablement decision; passing the runtime gates does not enable it automatically.
