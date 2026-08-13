# AI-003 fixed-sample Flow Spike gate

Status: executed, `failed_closed`. At `2026-07-29T16:06:53+08:00`, fixed samples and JSON logic validation passed, while the full gate scored 25/100. `flow_enabled=false` remains mandatory until every gate passes and Review approves enablement. See `evidence/gate-result.json` for fixture hashes and failed checks.

## Controlled steps

1. Freeze the three JSON fixtures and record their content hashes.
2. Generate a text-only candidate and complete human text Review.
3. Generate a Mermaid candidate only from the accepted text and complete Mermaid Review.
4. Convert the accepted Mermaid candidate into editable draw.io XML using an approved tool.
5. Export attributable PNG and SVG derivatives; never treat them as editable sources.
6. Run reachability, terminal-node, branch-label, orphan-node and recovery-path checks.
7. Verify Task, Call, Skill Version, Prompt, Template, Model and context-source trace fields.
8. Exercise a failed conversion and confirm the last accepted version is preserved.
9. Record every mandatory result in `evidence/gate-result.json` and run the gate evaluator.

The evaluator passes only when all mandatory checks are explicitly `true`. Missing results fail closed. This repository does not include or execute an unapproved Flow conversion script.
