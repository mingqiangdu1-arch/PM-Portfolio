# Sprint 1 backend contract freeze request

Status: Sprint 1 implementation candidate after Review corrections. Release remains blocked on real MySQL 8.4 and S3-compatible integration Gates.

Candidate revision: `20260729_0004` (head; `0002` AI fields, `0003` session rotation, `0004` object finalization identity)

## First Review corrections

- B1 implemented in `20260729_0003`: nullable active-session revocation, lossless family backfill, rotation timestamp, unique successor self-FK, family lookup index and downgrade refusal for active/rotated/family-linked data.
- B2 implemented in OpenAPI: public version compare, explicit Set-Cookie rotate/clear headers, same-origin Origin/Referer policy, optional deployment CSRF header and stable failure codes.
- Pending File Version lifecycle is now encoded in schemas and operation extensions, with available-only version lists and one-time pending-to-available finalization.

OpenAPI: `3.1.0`, generated only from `services/api/app/main.py`; Sprint 1 routes are marked `x-implementation-status: implemented-candidate` pending integration freeze.

## Consumer review scope

Frontend and Review should confirm these public groups:

- Identity: register, login, refresh rotation, logout and current session.
- Project: list/create/detail/update/archive/restore, member role read/write and Project Context.
- Version: list/detail, set-working and derive. Viewing a historical version is read-only and is not a command. Derive never silently changes the working version.
- File: signed-upload initialization/completion/abort, file/version read, signed download, relation creation and archive.
- Every external path is under `/api/v1`. `/internal/v1/health` uses the Review-frozen service identity `iss/sub=ai-api`, `aud=business-api`, scope `health`; monitoring is separately allowed only with `iss/sub=monitoring`.
- IDs are strings on the wire, timestamps are UTC RFC3339, lists use opaque cursors, and critical commands require `Idempotency-Key` plus an optimistic-lock field.

AI/data should confirm that no API response adds an `ai_call.trace_id` persistence field: it remains derived through `ai_call.ai_task_id -> ai_task.trace_id`.

## Permission candidate

- Project roles are exactly `owner`, `reviewer`, `implementer`, `tester`.
- Undefined actions are denied.
- `admin` is a system role and does not bypass project membership or owner-only content decisions.
- Only owner may update/archive/restore a Project, manage membership, set the working version or derive a version.
- All four project roles may read project history and upload/download/relate files within their allowed evidence scope; object ownership and association are checked in addition to membership.
- Non-member object lookup returns non-enumerating `RESOURCE_NOT_FOUND`; known insufficient role returns `FORBIDDEN`.

## Transaction candidate

Every critical write atomically writes its business fact,
`operation_audit_log`, and completed `idempotency_record` response reference.
Only commands with an already frozen canonical business event additionally
write `business_event_outbox` in that transaction. Audit failure, or Outbox
failure when an Outbox write is required, rolls back the command:

- create Project + V1 + owner membership;
- archive/restore Project;
- change member roles (audit only; no canonical member event in 0.1.3);
- set working Project Version;
- derive Project Version + lineage record;
- complete upload and create immutable File Version/initial Relation
  (`file.upload.completed` Outbox);
- create a standalone File Relation (audit only; no canonical relation event);
- archive File (audit only; no canonical archive event).

Object storage calls must not hold a MySQL transaction. Storage failure blocks new upload completion but does not block non-file Project CRUD. A successful object write followed by metadata failure is an orphan-cleanup candidate and is not returned as business success.

## Migration candidate already accepted by backend

`20260729_0002` adds six nullable rollout columns without fabricating historical data:

| Table | Column | Type / collation | Index / constraint |
|---|---|---|---|
| `ai_task` | `target_snapshot_hash` | `CHAR(64)` ASCII `ascii_bin`, nullable | none |
| `ai_task` | `command_id` | `VARCHAR(64)`, nullable | `idx_ai_task_command_id` |
| `ai_call` | `capability_fingerprint` | `CHAR(64)` ASCII `ascii_bin`, nullable | none |
| `ai_call` | `cost_source` | `VARCHAR(32)`, nullable | enum check |
| `ai_call` | `pricing_version` | `VARCHAR(32)`, nullable | required by check when calculated |
| `ai_call` | `provider_error_class` | `VARCHAR(64)` ASCII `ascii_bin`, nullable | `(provider_error_class,started_at,id)` |

Downgrade queries both tables first and rejects the downgrade if any of the six columns contains data.

## Implemented session schema delta for re-review

The confirmed 77-table dictionary originally could not represent secure Refresh rotation/replay:

1. `user_session.revoked_at` is `NOT NULL`, so an active non-revoked session has no valid representation.
2. There is no token-family or rotation-chain field, so replay cannot revoke the complete family without guesswork.

Review-accepted follow-up revision (created as `20260729_0003`):

| Column/change | Candidate | Existing-row handling |
|---|---|---|
| `user_session.revoked_at` | alter to `DATETIME(6) NULL` | preserve values; active rows may be null after rollout |
| `user_session.token_family_id` | `CHAR(36)` ASCII `NOT NULL` | add nullable, backfill from `session_public_id`, then make non-null |
| `user_session.rotated_at` | `DATETIME(6) NULL` | no fabricated backfill |
| `user_session.replaced_by_session_id` | `BIGINT UNSIGNED NULL` self-FK | no fabricated backfill |
| family lookup index | `(token_family_id, revoked_at, expires_at, id)` | online/index-lock risk to be checked |

`20260729_0003` implements this accepted delta and additionally makes `replaced_by_session_id` unique. Successful refresh will create a successor row while the locked predecessor records `rotated_at`, `revoked_at` and the successor reference; replay revokes the family by `token_family_id`. A sentinel `revoked_at`, overwriting a token hash in place, storing raw Refresh tokens or fabricating historical rotation remains rejected.

## First Review accepted decisions

1. `PATCH /projects/{id}/context` is a project-level mutable singleton. It is not a historical Project Version snapshot.
2. File upload state uses pending `stored_file` + pending `file_version`; no upload table is added. The pending version is internal-only until one-time completion and never appears in normal lists/download/relation/current-version references.
3. Any authenticated user may create a Project and becomes owner; admin is not required.
4. Project description maximum length is 5000. Registration password length is 12–128; login accepts existing credentials up to 128.

No Commit or Push has been made. Wave 2 must not start until Review rechecks the two corrections and explicitly freezes the consumer contract.

## Revision 20260729_0004: immutable object finalization candidate

Status: implementation-review candidate; this revision is not part of the
previously frozen wave-1 head and requires Review before release.

`20260729_0004` adds nullable `file_version.storage_version_id VARCHAR(255)`
and `idx_file_storage_version`. Existing rows are preserved without fabricated
object versions. Every newly completed `available` File Version must persist a
non-empty storage version identifier; downgrade refuses when any identifier is
present.

The completion protocol is now:

1. Browser PUTs only to a temporary key and must send signed
   `x-amz-checksum-sha256`; user-controlled metadata is not trusted.
2. Business API performs checksum-enabled HEAD outside the MySQL transaction.
3. Business API conditionally copies the exact source ETag/version to a
   deterministic server-only final key and verifies final size, MIME and native
   SHA-256 checksum.
4. The completion transaction changes `pending -> available` once and stores
   the final object key plus S3 version ID (or final ETag on a compatible store
   without bucket versioning), then creates current-version/relation/audit,
   canonical `file.upload.completed` Outbox and idempotency result.
5. A storage success followed by transaction failure is an orphan-cleanup
   candidate and is never returned as business success. The browser never
   receives write authority for the final key.

The schema overlay lineage is `0001 -> 0002 -> 0003 -> 0004`; its top-level
`revision` is therefore `20260729_0004`.

Canonical event limitation: the frozen 0.1.3 directory contains file upload
events but no file-relation or project-member event. Those commands write their
business fact, audit and idempotency record atomically, but must not invent a
canonical Outbox name. If Review requires Outbox for them, a separate event
catalog change must first freeze the names and payloads.
