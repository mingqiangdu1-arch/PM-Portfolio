# Compose environments

- Base: `infra/compose/compose.yaml`
- Local: add `compose.local.yaml`; data ports bind to loopback only.
- CI: add `compose.ci.yaml`; data volumes are ephemeral.
- Staging/Production: configuration skeletons only. Data services expose no host ports.
- `web`, `ai-api` and `ai-worker` use the `full-stack` profile and immutable image tags.
  Their commands and images require consumer review by the Frontend and AI/Data owners.

All credentials are file-backed Compose Secrets. Create ignored local secret files under
`infra/compose/secrets/` (the paths are resolved relative to the base Compose file) or
override them with paths supplied by your secret manager. Never copy values into
`.env.example`.
