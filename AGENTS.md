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

## Stage boundary

Interaction Design is complete and user-approved. Formal product design in `产品设计体系整理/` remains authoritative; the current effective Interaction Design baseline lives in `交互设计与页面状态机/交互设计/`. `page-state-machine-design` is installed and enabled, so the Page State Machine stage is ready to start only after explicit user authorization. The official Figma Plugin Skills required by the later visual stage are also registered and enabled, but visual design remains blocked until the Page State Machine baseline is completed and accepted. Do not create or modify Figma assets, start visual UI design, technical design, development, database changes, API changes, system-architecture changes, or business-code changes before their respective stage gates are satisfied.
