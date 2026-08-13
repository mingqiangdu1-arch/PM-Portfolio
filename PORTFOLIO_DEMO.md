# Portfolio P1 delivery

## Live MVP fallback

The repeatable local presentation entry is the frozen Frontend mock adapter.
It is intentionally labelled `FORMAL_MOCK`; it does not claim a live backend or
AI provider.

```powershell
cd F:\workflow平台\平台开发\.worktrees\frontend
pnpm.cmd dev
```

Open <http://localhost:3000>. The mock flow covers:

`Requirement -> AI clarification/baseline -> Adopt -> Confirm -> Current Baseline`

The real multi-service Compose deployment is not part of this fallback because
the local Docker Engine was unavailable during delivery validation.

## Interactive Prototype

The reusable high-fidelity prototype is the accepted Penpot source:

<https://design.penpot.app/#/workspace?team-id=bd31e32d-d69f-81e2-8008-63fe4b53bfae&file-id=bd31e32d-d69f-81e2-8008-6403c41c6a83&page-id=0b6cce22-0755-8065-8008-64eb314e889c>

Local backup: `Wireframe与UI设计/原型备份7.29.penpot`.

- P1 Requirement workspace and mock flow: `Implemented / Validated`
- PRD, Review, Implementation, Test/Feedback, Knowledge/RAG pages: `Interactive Prototype / Designed`

The prototype uses design/static data only and does not add or imply new
backend APIs, workers, databases, or production capability.
