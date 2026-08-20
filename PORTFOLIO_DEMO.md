# Portfolio P1 delivery

## REAL Production Accepted Release

- Accepted Runtime Commit: `1be1aec9410211e33f84b99c6166c6768fb487cf`
- Release Tag: `portfolio-p1-v1-accepted-main`
- R3 Contract SHA256: `a892a6a43d87f7baed2ea4d182d73da25fd470036895c8e22712064b7487aaaf`
- Public Acceptance: PASS
- UUID/HTTP compatibility: PASS
- Alembic: `20260729_0004`
- P1 Scope: CLOSED
- RC-02: NOT ENTERED
- `P1-MAIN-PROMOTION-07=PASS`; `P1-RELEASE-TAG-08=PASS`

The accepted production P1 chain is `Login -> Foundation -> Project -> Requirement -> Baseline -> Edit -> Confirm -> Persistence -> Reload`. REAL Production Accepted Release is the current P1 runtime fact.

The following capabilities are not part of the current P1 Accepted Release and must not be described by this Portfolio Demo as production-accepted: File Upload, Version Derivation, Set Working Version, AI Runtime, AI Worker, Redis, MinIO / S3, Qdrant, P2, P3, P4, and AI MVP.

## Live MVP fallback

The repeatable local presentation entry is the frozen Frontend mock adapter.
It is intentionally labelled `FORMAL_MOCK` and is a local fallback only; it does not replace or describe the current production runtime.

```powershell
cd F:\workflow平台\平台开发\.worktrees\frontend
pnpm.cmd dev
```

Open <http://localhost:3000>. The mock flow covers:

`Requirement -> AI clarification/baseline -> Adopt -> Confirm -> Current Baseline`

Historical note: the fallback was retained because the local Docker Engine was unavailable during its delivery validation. That historical local limitation does not describe the current REAL Production Accepted Release.

## Interactive Prototype

The reusable high-fidelity prototype is the accepted Penpot source:

<https://design.penpot.app/#/workspace?team-id=bd31e32d-d69f-81e2-8008-63fe4b53bfae&file-id=bd31e32d-d69f-81e2-8008-6403c41c6a83&page-id=0b6cce22-0755-8065-8008-64eb314e889c>

Local backup: `Wireframe与UI设计/原型备份7.29.penpot`.

- P1 Requirement workspace and mock flow: `Implemented / Validated`
- PRD, Review, Implementation, Test/Feedback, Knowledge/RAG pages: `Interactive Prototype / Designed`

The prototype uses design/static data only and does not add or imply new
backend APIs, workers, databases, or production capability.
