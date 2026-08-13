# Migration baseline

The single Alembic head is `20260729_0001`. Its pinned schema catalog is generated from
the confirmed 77-table data dictionary by `infra/scripts/generate_schema_catalog.py`.
The catalog and revision are a candidate until AI/Data reviews AI, event and metric tables
and Review freezes the migration contract. Once frozen, the catalog used by this revision
must never be regenerated in place; changes require a new revision.

Run from the repository root:

```powershell
$env:DATABASE_URL = "mysql+pymysql://..."
python -m alembic -c infra/migrations/alembic.ini upgrade head
```
