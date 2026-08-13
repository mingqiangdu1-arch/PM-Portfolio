# OPS-001 precise AI service Compose change request

This is a request for the backend/OPS owner. Do not apply it from the AI/data worktree.

## Service commands

- `ai-api`: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `ai-worker`: `celery -A app.workers.celery_app:celery_app worker --loglevel=INFO --queues=interactive,file_parse,export,maintenance`

Both services use build context `./services/ai` and `services/ai/Dockerfile`. Only `ai-api` needs an internal HTTP port. Redis must not expose a public host port.

## Required configuration

- `AI_BROKER_URL=redis://:<secret-reference>@redis:6379/<ops-selected-db>`
- `AI_TASK_DEFAULT_QUEUE=interactive`
- `AI_ENVIRONMENT=<environment>`
- `AI_PROVIDER_MODE=stub` and `AI_CONTEXT_MODE=stub` in CI only
- `AI_LIVE_PROVIDER_AUTHORIZED=false` unless the user separately authorizes a controlled live call
- `FLOW_ENABLED=false`
- `PRODUCT_RELEASE=<immutable-release-id>`

Use secret references rather than literal Redis/provider credentials. The worker has no Celery result backend. Redis health and API/worker startup ordering are operational aids, not authoritative task-state storage.

## Review blockers

- Backend must replace the current placeholder `python -m app.api` / `python -m app.worker` commands.
- Backend/OPS must confirm the Redis database, credential secret name, internal healthcheck, restart policy, and queue-to-worker allocation.
- Readiness must reject new tasks when durable creation or Redis dispatch is unavailable; it must not fabricate progress or mark existing durable tasks lost.
