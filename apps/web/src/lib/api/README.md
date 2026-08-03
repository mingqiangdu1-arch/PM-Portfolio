# API client boundary

FE-003 consumes the Review-frozen BE-002 OpenAPI snapshot. `ports.ts` contains frontend-only view models; both adapters implement the same boundary. They are not OpenAPI DTOs.

- Set `OPENAPI_SCHEMA_PATH` to the frozen JSON and run `pnpm --filter @aipdv/web api:generate`. Generation is rejected unless its SHA-256 matches the reviewed snapshot.
- `generated/` is Orval output and must not be edited by hand. `real-adapter.ts` maps generated types into frontend view ports.
- `NEXT_PUBLIC_API_MODE=mock|real` selects the adapter; the default remains deterministic mock mode. `NEXT_PUBLIC_API_BASE_URL` configures the real origin.
- Browser code must not call Business API through ad-hoc request shapes.
- Real version derivation and file relation submission remain intentionally blocked until their allowed semantic values are frozen; no placeholder enum is sent.
