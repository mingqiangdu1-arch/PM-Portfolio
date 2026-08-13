from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT / "infra" / "migrations" / "alembic.ini"
EXPECTED_HEAD = "20260729_0004"


def upgrade() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_CONFIG), "upgrade", "head"],
        cwd=ROOT,
        check=True,
    )


def scalar(connection: sa.Connection, statement: str) -> int | str:
    return connection.execute(sa.text(statement)).scalar_one()


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    upgrade()  # empty-database migration
    upgrade()  # repeat upgrade must be a no-op
    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        table_count = scalar(
            connection,
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name <> 'alembic_version'",
        )
        head = scalar(connection, "SELECT version_num FROM alembic_version")
        generated_unique = scalar(
            connection,
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND index_name IN "
            "('uk_project_one_working','uk_requirement_effective',"
            "'uk_version_one_main_prd','uk_plan_one_effective_round')",
        )
    if table_count != 77:
        raise RuntimeError(f"Expected 77 business tables, found {table_count}")
    if head != EXPECTED_HEAD:
        raise RuntimeError(f"Expected migration head {EXPECTED_HEAD}, found {head}")
    if generated_unique != 4:
        raise RuntimeError("Critical generated unique constraints are missing")
    print(f"Verified {table_count} tables at Alembic head {head}")


if __name__ == "__main__":
    main()
