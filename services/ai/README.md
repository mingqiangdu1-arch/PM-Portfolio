# AI service foundation

This directory owns the Sprint 0 AI/data implementation boundary:

- internal FastAPI AI service and Celery worker;
- Task Router, context, provider, result-processing, and trace foundations;
- candidate AI/event JSON Schemas and offline data-quality checks;
- Provider/Context stubs used by CI;
- AI-003 fixed Flow spike inputs, rubric, and gate evidence;
- AI/worker/data-quality monitoring rules.

The service never formalizes a business artifact. Business API remains the only
owner of permissions, Project Version state, formal artifacts, and adoption
transactions. Redis is transport and recoverable progress only; it is not a
fact store.

## Wave status

- Wave 1: runnable scaffold, stubs, candidate schemas, fixtures, and offline
  tests completed.
- Wave 2: conditionally authorized for integration candidates. Redis/Celery
  dispatch boundaries, an OpenAI-compatible DeepSeek profile, Schema 0.1.3,
  data-quality checks, and the fixed JSON Flow sample run are implemented.
- Still blocked: database-backed integration, Compose acceptance, live provider
  calls, event-Schema freeze, and Flow enablement require backend/OPS/Review.

No real provider call is permitted in CI. A live DeepSeek smoke test additionally
requires explicit user network authorization and a secret reference supplied
outside the repository.

## Sprint 1 internal authentication

`GET /internal/v1/ai/health/ready` requires a short-lived Service JWT from `business-api` with audience `ai-api` and scope `health`. Configure inbound verification with `AI_INTERNAL_JWT_SECRET`. When `AI_CONTEXT_MODE=business_api`, configure `AI_BUSINESS_API_URL` and `AI_BUSINESS_API_JWT_SECRET`; the probe calls `/internal/v1/health` with `iss/sub=ai-api`, audience `business-api`, scope `health`, a maximum 300-second TTL, and never retains the response body. `ai-worker` identity is reserved for task-scoped Context/File/Freshness calls.

AI readiness describes the `ai_tasks` capability only. Broker, Provider, Context or Business API failure rejects new AI work but must not be interpreted as Project CRUD unavailability. `FLOW_ENABLED` remains false.

## Local verification

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python tools\validate_schemas.py
.\.venv\Scripts\python tools\check_event_quality.py examples\events\valid-events.json --known-task-id 5
.\.venv\Scripts\python tools\evaluate_flow_fixtures.py
.\.venv\Scripts\python tools\evaluate_flow_gate.py --rubric flow_spike\rubric.json --evidence flow_spike\evidence\gate-result.json
```

Start the internal API or worker only after dependencies are installed:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
.\.venv\Scripts\celery -A app.workers.celery_app:celery_app worker -Q interactive --loglevel INFO
```
