# API service

Sprint 0 establishes a modular FastAPI monolith. The service exposes health and
contract surfaces only; Sprint 1 identity, project and version behavior is not
implemented here.

Boundary rule: routers call application services, application services coordinate
domain objects and repository ports, and only infrastructure adapters access storage.
Cross-module writes must go through an application command or an outbox event.

Run locally after installing declared dependencies:

```powershell
python -m uvicorn app.main:app --app-dir services/api --reload
```
