# AI-101 / DATA-101 backend freeze review

Status: Sprint 1 contract/schema/event/runtime integration is `review_approved`; the MySQL 8.4.8 and MinIO runtime gates passed. Persistence remains disabled until an explicit enablement decision.

## 2026-08-05 runtime integration result

- The protected Business API health runtime accepts `iss/sub=ai-api`, audience `business-api`, scope `health` with HTTP 200. The obsolete `ai-service + health:read` identity is rejected with 401, and `ai-api + health:read` is rejected with 403.
- OpenAPI remains 29 paths / 28 Sprint 1 business operations with SHA256 `765085b584de8bf22b1a2724b0e4745fa3c8b2db7c16a7ead77c38d736917f1e`.
- Its transaction extension separates `always=[business_fact, operation_audit_log, completed_idempotency_record]` from conditional `business_event_outbox`; audit or a required Outbox failure rolls back. Operation-level canonical-event markers exist only for the seven frozen successful BF operations. Standalone relation, upload abort, file archive and member-role writes have no marker.
- The migration chain is `0001 → 0002 → 0003 → 0004`. The overlay declares head `20260729_0004` and SHA256 `ab603c7d3288492d2ef27493ed9958ae3ad7944861fb6a5a7ace622cf9d6e1da`; migration 0001 SHA256 is `d304df59e8073b1e2bf19ff4cb3ff2929aa8e5b4384d67ac5d7929be9e31e4b5`, and migration 0004 SHA256 is `fc843e5ab0bdd2c3e4e5f5d6365ec522930ca2e397113c92899dd2c65a3c9c0a`.
- Review accepts nullable rollout of `file_version.storage_version_id`, mandatory population for new available versions, its index and populated-data downgrade guard. Real MinIO integration verified signed native checksum, stale conditional copy rejection, server-only final key isolation and storage version/ETag.
- Real MySQL 8.4.8 and MinIO target suites each report 1 passed / 0 skipped. The backend full suite reports 65 passed / 0 skipped; `head → base → head → head`, existing-database upgrade, 77 tables, 234 foreign keys and the 0003/0004 downgrade guards passed.
- Standalone `create_relation` is Review-frozen as business fact + `operation_audit_log` + completed `idempotency_record` in one transaction, with no BF/Outbox. `complete_upload`, including its initialization relation, continues to emit canonical `file.upload.completed`. No generic relation event is invented.
- Sprint 2 `requirement.clarify` candidates are deliberately absent from the AI/data implementation and contracts until the root formal baseline and a later Review freeze package authorize them.

Reviewed backend state: branch `codex/backend`, base `eaa1f992ff37875ce8fdbfa97cf99ee68c5ff94b`, overlay head `20260729_0004`, OpenAPI `3.1.0`, application version `0.1.0-dev`. Review froze 28 Sprint 1 business operations for wave 2; `/internal/v1/health` produces the observed 29-path candidate. Commit authorization remains a separate Review decision for each worktree.

## Six-field migration comparison

| Source contract | Producer | Consumer | Actual Alembic type/null | Enum/check | Index | Degradation | Compatibility conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ai_task.target_snapshot_hash` | AI API precheck | AI repository, freshness checks | `CHAR(64)` ASCII `ascii_bin`, NULL | none | none | no fabricated backfill; reject/quality-block without trustworthy hash | Static migration matches 0.1.3. |
| `ai_task.command_id` | Business API Task Envelope | AI repository, audit/event trace | `VARCHAR(64)`, NULL | none | `idx_ai_task_command_id(command_id)` | resolve through command/idempotency trace before migration | Review accepts inherited collation consistent with trace/command fields; compare normalized original values without case conversion. |
| `ai_call.capability_fingerprint` | AI runtime | trace/quality consumers | `CHAR(64)` ASCII `ascii_bin`, NULL | none | none | recompute only when every version FK exists | Static migration matches. |
| `ai_call.cost_source` | Provider adapter | cost/quality consumers | `VARCHAR(32)`, NULL | allowed values or NULL | none | do not silently discard classification | Static migration/check match. |
| `ai_call.pricing_version` | Provider profile calculator | cost consumers | `VARCHAR(32)`, NULL | required when cost is profile-calculated | none | calculated cost without version becomes unavailable | Static migration/check match. |
| `ai_call.provider_error_class` | Provider adapter | diagnostics/alerts | `VARCHAR(64)` ASCII `ascii_bin`, NULL | none | `(provider_error_class,started_at,id)` | lossy failure-code mapping rejected | Static migration/index match. |

Downgrade queries both AI tables and refuses removal when any accepted field contains data. No historical values are fabricated. `ai_call.trace_id` remains relational through `ai_call.ai_task_id → ai_task.trace_id`, not a seventh column.

Runtime evidence recorded before any persistence-adapter enablement decision:

1. Real MySQL 8.4.8 empty/existing/repeated-upgrade and downgrade evidence passed, including `head → base → head → head`, 77 tables and 234 foreign keys.
2. Real MinIO/S3 checksum and conditional-copy evidence passed, including stale ETag rejection and proof that tampered or anonymous clients cannot overwrite the server-only final key.

Passing these gates does not automatically enable persistence. `persistence_adapter_enabled=false` remains the reviewed rollout state until a separate enablement decision.

The effective database contract is the 77-table `schema_catalog.json` base plus versioned `20260729_0002`, `20260729_0003`, `20260729_0004` and `sprint1_schema_delta.json`. Review accepts this traceable static overlay; the base catalog must not be rewritten.

## Sprint 1 tables and event consumers

| Source | Producer | Consumer | Type/null/index observation | Degradation and conclusion |
| --- | --- | --- | --- | --- |
| `user_account` | Business API identity | auth, audit, event relation checker | Formal fields and `uk_user_email` present | Never emit email/password hash. Static mapping accepted. |
| `user_session` | Business API identity | refresh/replay/audit | `0003`: nullable `revoked_at`; non-null ASCII `token_family_id`; nullable `rotated_at`; unique nullable successor self-FK; family-state index | Review accepted. Existing rows backfill family from `session_public_id` without fabricating rotation; unsafe downgrade is refused. |
| `project/project_member` | Business API project transaction | API, audit, event consumer | owner/status and unique role membership present | Every critical write includes fact/audit/idempotency; Outbox is additionally required only when the frozen catalog has a canonical BF. |
| `project_version` | Business API version commands | API, audit, event consumer | lineage, unique version number, generated unique working key present | History view/set-working/derive remain independent. Real MySQL 8.4.8 verification passed. |
| `stored_file/file_version/file_relation` | Business API + storage coordinator | API, audit, event consumer | 0004 adds nullable `storage_version_id`, required for new available writes; relation constraints remain | Standalone relation is AU-only. Storage failure cannot delete business facts or block non-file CRUD. Real object-store finalization verification passed. |
| `operation_audit_log` | Business API critical commands | security/audit queries | `object_type` NN; object IDs/metadata nullable; trace/command NN; expected indexes present | Audit failure rolls back critical command; never store Token, signed URL, or response body. Static mapping matches 0.1.3. |

## OpenAPI and AI-101 integration

- Review-frozen business contract contains 28 Sprint 1 business operations. The observed second-wave OpenAPI has 29 paths including `/internal/v1/health`; its business operations are marked `implemented-candidate`.
- The protected health path advertises issuers `ai-api/monitoring`, requires subject `ai-api` for the AI caller, audience `business-api` and scope `health`, matching the Review-frozen AI identity.
- AI API readiness requires a valid Service JWT with audience `ai-api` and scope `health`; missing, invalid, expired and insufficient-scope tokens are rejected.
- Outbound AI health probe calls `/internal/v1/health`, issues `iss/sub=ai-api`, audience `business-api`, scope `health`, transmits `X-Trace-ID`, uses a bounded timeout and records only status/error class. `ai-worker` remains reserved for task-scoped Context/File/Freshness calls.
- AI readiness reports only `ai_tasks`; it does not claim Project CRUD unavailable. Mock and in-process cross-service tests exercise the protected Business API health contract without making Project CRUD depend on AI availability.

## Freeze decision

The protected health contract and 0004 overlay match the Review-approved wave 2 candidate. Schema 0.1.3 contract/schema/event/runtime integration is `review_approved`; real MySQL 8.4.8 migration and real MinIO/S3 checksum, conditional-copy and final-key isolation tests passed. Persistence remains off pending an explicit enablement decision. AI-side Mock and actual backend in-process authentication tests pass. The expected source hashes, including the repaired 0001 migration, are recorded in `contracts/backend-sprint1-freeze.json`.
