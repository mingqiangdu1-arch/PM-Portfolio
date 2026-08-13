"""Add the six backend-accepted AI traceability fields for Schema 0.1.3.

Revision ID: 20260729_0002
Revises: 20260729_0001
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "20260729_0002"
down_revision: str | None = "20260729_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_TASK_COLUMNS = ("target_snapshot_hash", "command_id")
AI_CALL_COLUMNS = (
    "capability_fingerprint",
    "cost_source",
    "pricing_version",
    "provider_error_class",
)


def upgrade() -> None:
    op.add_column(
        "ai_task",
        sa.Column(
            "target_snapshot_hash",
            mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_task",
        sa.Column(
            "command_id",
            mysql.VARCHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
    )
    op.create_index("idx_ai_task_command_id", "ai_task", ["command_id"], unique=False)

    op.add_column(
        "ai_call",
        sa.Column(
            "capability_fingerprint",
            mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
    )
    op.add_column("ai_call", sa.Column("cost_source", sa.String(32), nullable=True))
    op.add_column("ai_call", sa.Column("pricing_version", sa.String(32), nullable=True))
    op.add_column(
        "ai_call",
        sa.Column(
            "provider_error_class",
            mysql.VARCHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_ai_call_cost_source",
        "ai_call",
        "cost_source IS NULL OR cost_source IN "
        "('provider_reported', 'profile_calculated', 'unavailable')",
    )
    op.create_check_constraint(
        "ck_ai_call_calculated_pricing",
        "ai_call",
        "cost_source <> 'profile_calculated' OR pricing_version IS NOT NULL",
    )
    op.create_index(
        "idx_ai_call_provider_error_class",
        "ai_call",
        ["provider_error_class", "started_at", "id"],
        unique=False,
    )


def _count_populated(bind: sa.engine.Connection, table: str, columns: tuple[str, ...]) -> int:
    predicates = " OR ".join(f"`{column}` IS NOT NULL" for column in columns)
    statement = sa.text(f"SELECT COUNT(*) FROM `{table}` WHERE {predicates}")
    return int(bind.execute(statement).scalar_one())


def downgrade() -> None:
    bind = op.get_bind()
    populated_task_rows = _count_populated(bind, "ai_task", AI_TASK_COLUMNS)
    populated_call_rows = _count_populated(bind, "ai_call", AI_CALL_COLUMNS)
    if populated_task_rows or populated_call_rows:
        raise RuntimeError(
            "Refusing lossy downgrade of 20260729_0002: one or more accepted AI fields contain data"
        )

    op.drop_index("idx_ai_call_provider_error_class", table_name="ai_call")
    op.drop_constraint("ck_ai_call_calculated_pricing", "ai_call", type_="check")
    op.drop_constraint("ck_ai_call_cost_source", "ai_call", type_="check")
    for column in reversed(AI_CALL_COLUMNS):
        op.drop_column("ai_call", column)

    op.drop_index("idx_ai_task_command_id", table_name="ai_task")
    for column in reversed(AI_TASK_COLUMNS):
        op.drop_column("ai_task", column)
