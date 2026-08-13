# M2 AI/data Requirement Clarification R3 re-review request

Candidate version: `0.2.0-proposed`

Proposed Schema identity: `0.2.0`

Status: `ready_for_review`

Requested Review result: `approved` or `changes_required`

This isolated candidate bundle applies the targeted RequirementContent R3
correction. The previous R2 bundle hash is retained as audit evidence only and
is not an implementation input. This request does not authorize further runtime
work.

## Freeze scope requested

- Canonical dimensions use `exception_cases` and the other seven frozen keys.
- Task/Result statuses, Result kinds, modes, adoption mapping, modification
  intensities, completeness, complexity, finish reasons, 3/5 round limits,
  deep round 4-5 confirmation, and 1-3 questions match the Review decision.
- Task Envelope contains the frozen user/project/module/target/hash/source/
  capability/risk/command/trace/time/input identity.
- Result Content contains assessment, questions, Baseline, convergence, and
  quality structures. Result Baseline and RequirementContent Baseline map 1:1.
- RequirementContent retains required non-empty `raw_input` verbatim, marks it
  and `raw_input_ref` read-only, represents `raw_input_ref` as a five-field
  `SourceRef`, constrains nullable assessment to `ClarificationAssessment`, and stores
  clarification history as `rounds[]`. Each round contains `round_no`,
  `ai_task_id`, `ai_result_id`, 1-3 questions, and 1-3 answers; an answer
  contains exactly `question_id` and `answer`.
- Every Result/RequirementContent `source_refs` item uses the backend-compatible
  five-field `SourceRef` object: `source_type`, `source_id`, nullable
  `source_version_id`, SHA-256 `content_hash`, and `label`. Task Envelope
  `source_ref_ids[]` remains a string array as separately adjudicated.
- Context Snapshot records actual source IDs and versions, injection/exclusion,
  fingerprints, and token counts using existing traceability facts only.
- Requirement business event Schema identity is `0.2.0`; its producer is
  `Business API`, transaction facts and payloads match the decision, and
  producer envelopes reject `ingested_at`.
- AI runtime events remain owned by `AI Service`. Existing adoption/rejection
  events and the derived `not_reviewed` mapping are documented without adding a
  persisted `not_reviewed` adoption value.
- Formal Schema `0.1.3` files remain unchanged historical facts; the formal
  v0.2 RequirementContent copy must match this candidate byte-for-byte.

## Review actions requested

1. Verify the AI/data artifact hashes returned with this request against this
   bundle and record the accepted bundle hash.
2. Record the compatible backend OpenAPI candidate hash and the final
   OpenAPI-to-AI/event hash mapping. This AI/data window did not read or alter a
   backend worktree; cross-window hash pairing remains a Review action.
3. If compatible, approve the R3 correction with final hashes. Otherwise return
   one consolidated `changes_required` result.

## Known limits and exclusions

- This package contains contracts, mapping, fixed Stub-style samples, and
  candidate-only tests. It contains no Provider response or credential and
  makes no network call.
- It does not implement Task runtime, Provider, Context loader, worker,
  persistence adapter, database migration, OpenAPI, UI, SSE, or Flow behavior.
- Project-file refresh/recovery, file relation enums, Requirement derivation
  `change_type/inheritance_choices`, and public dual-submit CSRF delivery remain
  outside this R3 correction under the Review decision.
- No Stage, Commit, Push, Merge, or Rebase is authorized.

Only an explicit Review approval authorizes continuation of the paused runtime
implementation; Commit and Push remain separately unauthorized.
