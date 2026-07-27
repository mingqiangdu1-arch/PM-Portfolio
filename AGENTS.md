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
- Do not place either stage's formal deliverables in the project root, `产品设计体系整理/`, or the other stage's subdirectory.
- Shared navigation or index material for these two stages may live at `交互设计与页面状态机/README.md`, but each formal artifact must have one owning stage directory.

## Stage boundary

Interaction Design is complete and user-approved. Formal product design in `产品设计体系整理/` remains authoritative; the current effective Interaction Design baseline lives in `交互设计与页面状态机/交互设计/`. Do not start the Page State Machine stage until its required Skill has been separately discovered, audited, confirmed by the user, and installed, and the user has explicitly authorized that stage. Do not start visual UI design, technical design, development, database changes, API changes, system-architecture changes, or business-code changes without explicit user authorization.
