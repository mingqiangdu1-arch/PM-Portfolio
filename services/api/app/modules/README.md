# Module boundaries

Each business module owns its application commands, domain model, repository ports and
infrastructure adapters. A module must not import another module's repository adapter or
ORM model. Cross-module work uses an application-facing port and persists an outbox event
in the same transaction as the owning state change.

Sprint 0 contains boundary markers only. No Sprint 1 identity, project or version behavior
is implemented.
