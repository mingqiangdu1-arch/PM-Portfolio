# Project Agent Rules

## Authoritative context

Read `PROJECT_STATUS.md` and `PROJECT_MEMORY.md` before project work. If `CURRENT_TASK.md` exists, read it next. Current formal product design lives in `产品设计体系整理/` and takes precedence over summaries, task notes, project rules, and external Skills.

## External Product-design Skills

The following user-level External Skills are available through `C:\Users\10238\.codex\skills\external` and registered in `F:\AI-Agent-System\skills\INDEX.md`:

- `jobs-to-be-done`: user, situation, job, pain, alternative, and desired-outcome analysis.
- `opportunity-solution-tree`: desired outcome, opportunity, solution, and experiment mapping.
- `epic-hypothesis`: falsifiable feature/module hypotheses and validation design.

Do not scan or load all external Skill files by default.

1. Match the task against the Skill names and descriptions above.
2. Read only the selected primary Skill's `SKILL.md`.
3. Use one Skill by default.
4. Use at most one secondary Skill when the task genuinely needs both methods.
5. Never load all three product-design Skills in one task.
6. Treat Skill output as analysis or a candidate. Do not use it to overwrite current formal product design.
7. Do not install additional Skills or run referenced scripts without explicit user approval.

Skill precedence:

`正式产品设计 > PROJECT_MEMORY.md > CURRENT_TASK.md（如存在） > AGENTS.md > External Skill`

The previous product-design Skills are non-default in Interaction Design:

- `jobs-to-be-done`: candidate; load only when a page goal lacks confirmed user evidence.
- `opportunity-solution-tree`: disabled.
- `epic-hypothesis`: disabled.

## External Interaction-design Skills

The following user-level External Skills were used for the completed Interaction Design stage and are now disabled by default. They remain installed through `C:\Users\10238\.codex\skills\external` and registered in `F:\AI-Agent-System\skills\INDEX.md`:

- `user-flow-mapping`: user task flows, page entry/exit, page transitions, user-visible branches, cancellation, return and failure recovery.
- `wireframing`: page goals, information hierarchy, content regions, component placeholders, operation entry points and low-fidelity page structures.

Do not load either Skill for subsequent stages by default. If the user requests a revision to the confirmed Interaction Design baseline, temporarily use `user-flow-mapping` first for cross-page task paths, then `wireframing` for the pages required by those paths. Load one Skill by default and both only sequentially for a complete feature.

For this project, `user-flow-mapping` must not model backend services, APIs, databases, Agent execution chains, architecture or delivery schedules. It must not invent conversion or drop-off data. `wireframing` is limited to low-fidelity structure and must not define branding, colors, typography, high-fidelity UI, motion, frontend code, component-library implementation or responsive engineering details.

## Stage output locations

- Save Interaction Design deliverables only under `交互设计与页面状态机/交互设计/`.
- Save Page State Machine deliverables only under `交互设计与页面状态机/页面状态机/`.
- Save Wireframe, visual-specification, UI-design and high-fidelity-prototype deliverables only under `Wireframe与UI设计/`, using its stage subdirectories defined in that directory's `README.md`.
- Do not place either stage's formal deliverables in the project root, `产品设计体系整理/`, or the other stage's subdirectory.
- Shared navigation or index material for these two stages may live at `交互设计与页面状态机/README.md`, but each formal artifact must have one owning stage directory.

## Figma design Skills

The official Figma Plugin provides the following stage Skills without a project-local or user-level copy:

- `figma-use`: mandatory foundation before every `use_figma` call.
- `figma-generate-library`: design tokens, styles, components and variants; use together with `figma-use`.
- `figma-generate-design`: composed screens and views; use together with `figma-use`.

For low-fidelity completion, `wireframing` is candidate-only and may be loaded temporarily. Do not enable design-to-code, Code Connect, motion, frontend implementation or code-generation Skills for the Wireframe/UI stage. Figma Skills execute confirmed product, interaction and page-state decisions; they must not overwrite them. Do not create or modify a Figma file until the Page State Machine baseline is complete and the user explicitly authorizes visual design work.

## Personal Page State Machine Skill

`page-state-machine-design` is available through `C:\Users\10238\.codex\skills\personal` and registered in `F:\AI-Agent-System\skills\INDEX.md`. Use it only for user-observable page or page-family states, events, guards, transitions, entry/exit actions, asynchronous feedback, permissions and recovery. Do not use it to redefine business entity lifecycles, backend orchestration, APIs, databases, visual styling or implementation code. Formal product design and confirmed Interaction Design remain authoritative.

## Current Governance Closeout

- `RC-02-FREEZE-11-20260821-MVP2-PRD-REVIEW-V1` is unchanged: `mvp2.prd-review.rc02.v1`, `packages/contracts/openapi/openapi.json`, SHA256 `80c5060dad07e02c3092303fa479ca73428ce44f1d9d8e0dc640c6249b15b01e`, 50 paths / 56 operations, migration head `20260821_0005`; AI is OUT.
- Accepted source baseline: Backend Package 1 `2499d7a`, Backend Package 2 `28e904e`, Frontend Package `00511ae`, and source-binding fix `201a53e` (the effective requirement version ID is serialized for confirmed/effective lists; draft/non-effective remains null).
- `MVP2_INTEGRATION_REVIEW=ACCEPT` and `INTEGRATION_VERIFICATION=PASS`: the authorized PRD happy path passed. The later `GET design-reviews` 405 is `VERIFICATION_PROCEDURE_OUT_OF_SCOPE_NOT_IMPLEMENTATION_FAILURE`.
- `MVP2-POST-PUSH-CLOSEOUT=PASS` for `origin/codex/backend-mvp2-package1-local` at `201a53e`; its canonical real-content diff is clean and it has no true untracked files.
- `MVP2_STATUS=COMPLETED_IN_MAIN`.
- `MVP2_MAIN_PROMOTION=PASS`.
- `BACKEND_PACKAGE_1=ACCEPTED`; `BACKEND_PACKAGE_2=ACCEPTED`; `FRONTEND_PACKAGE=ACCEPTED`; `SOURCE_BINDING_FIX=ACCEPTED`; `MVP2_INTEGRATION_REVIEW=ACCEPT`; `PRD_HAPPY_PATH=PASS`.
- Accepted reconciliation merge: `32e8d7e1395ddb90395f146d06ac29a99ebbd011`, with parents `14bc14ea8af1cdd85d82556271dfe0a0957cc5af` and `201a53ec40d3eb7c6e62025355c0a7806ff524de`; this merge is in Main ancestry. The final governance closeout is a later child and this record does not claim `32e8d7e` remains the future remote tip.
- `MVP2_CURRENT_GATE=MVP2-COMPLETE`; `MVP2_NEXT_GATE=AWAITING_NEW_USER_AUTHORITY`. No further MVP2 action is authorized by this closeout.
- `RELEASE_AUTHORITY=NOT_GRANTED`; `TAG_AUTHORITY=NOT_GRANTED`; `DEPLOYMENT_AUTHORITY=NOT_GRANTED`; `PRODUCTION_CHANGED=NO`.

P1 is historical only: its accepted runtime commit `1be1aec`, tag `portfolio-p1-v1-accepted-main`, and `20260729_0004` migration record do not describe current MVP2 state or authorize new production work.

## Stage boundary

Interaction Design is complete and user-approved. Formal product design in `产品设计体系整理/` remains authoritative; the current effective Interaction Design baseline lives in `交互设计与页面状态机/交互设计/`. `page-state-machine-design` remains bounded to user-observable page behavior, and the design-stage rules above remain authoritative for their respective documents. Historical stage rules that say development had not started describe their original design-stage context; they do not override the current MVP2 Main closeout or authorize any new scope.
