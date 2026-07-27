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

## Stage boundary

The current stage is Product Design Consolidation. Do not start interaction design, technical design, development, database changes, or business-code changes without explicit user authorization.
