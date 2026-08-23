"""Add the frozen MVP3 implementation-plan confirmation foundation fields.

Revision ID: 20260823_0006
Revises: 20260821_0005

The three foundation tables already exist.  This revision is intentionally
fail-closed: the authenticated session and all three row counts are checked on
the same Alembic bind before the first DDL statement.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "20260823_0006"
down_revision: str | None = "20260821_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOUNDATION_TABLES = (
    "implementation_plan",
    "implementation_plan_version",
    "confirmation_round",
)


def _guard_empty_target() -> None:
    """Verify identity and zero rows before any schema mutation."""
    bind = op.get_bind()
    identity = bind.execute(
        sa.text("SELECT DATABASE(), CURRENT_USER(), VERSION()")
    ).one()
    if any(value is None or not str(value).strip() for value in identity):
        raise RuntimeError("MVP3 0006 guard failed: target identity unavailable")
    counts = tuple(
        int(bind.execute(sa.text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one())
        for table in FOUNDATION_TABLES
    )
    if counts != (0, 0, 0):
        raise RuntimeError(
            "MVP3 0006 guard failed: expected 0/0/0 on the authenticated target; "
            f"got {counts[0]}/{counts[1]}/{counts[2]}"
        )


def upgrade() -> None:
    _guard_empty_target()

    op.add_column(
        "implementation_plan",
        sa.Column("source_prd_version_id", mysql.BIGINT(unsigned=True), nullable=False),
    )
    op.add_column(
        "implementation_plan",
        sa.Column("source_design_review_id", mysql.BIGINT(unsigned=True), nullable=False),
    )
    op.create_index(
        "idx_implementation_plan_source_prd_version",
        "implementation_plan",
        ["source_prd_version_id"],
        unique=False,
    )
    op.create_index(
        "idx_implementation_plan_source_design_review",
        "implementation_plan",
        ["source_design_review_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_implementation_plan_source_prd_version_id",
        "implementation_plan",
        "prd_version",
        ["source_prd_version_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )
    op.create_foreign_key(
        "fk_implementation_plan_source_design_review_id",
        "implementation_plan",
        "design_review",
        ["source_design_review_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )
    op.create_foreign_key(
        "fk_implementation_plan_current_version_id",
        "implementation_plan",
        "implementation_plan_version",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )

    op.create_foreign_key(
        "fk_implementation_plan_version_source_version_id",
        "implementation_plan_version",
        "implementation_plan_version",
        ["source_version_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )

    op.add_column(
        "confirmation_round",
        sa.Column("source_round_id", mysql.BIGINT(unsigned=True), nullable=True),
    )
    op.add_column(
        "confirmation_round",
        sa.Column("implementation_summary", sa.Text(), nullable=False),
    )
    op.add_column(
        "confirmation_round",
        sa.Column("readiness_json", mysql.JSON(), nullable=False),
    )
    op.add_column(
        "confirmation_round",
        sa.Column(
            "draft_plan_key",
            mysql.BIGINT(unsigned=True),
            sa.Computed(
                "CASE WHEN status = 'draft' THEN implementation_plan_id END",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_confirmation_round_source_round",
        "confirmation_round",
        ["source_round_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uk_plan_one_draft_round", "confirmation_round", ["draft_plan_key"]
    )
    op.create_foreign_key(
        "fk_confirmation_round_source_round_id",
        "confirmation_round",
        "confirmation_round",
        ["source_round_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def downgrade() -> None:
    _guard_empty_target()

    op.drop_constraint(
        "fk_confirmation_round_source_round_id", "confirmation_round", type_="foreignkey"
    )
    op.drop_constraint("uk_plan_one_draft_round", "confirmation_round", type_="unique")
    op.drop_index("idx_confirmation_round_source_round", table_name="confirmation_round")
    op.drop_column("confirmation_round", "draft_plan_key")
    op.drop_column("confirmation_round", "readiness_json")
    op.drop_column("confirmation_round", "implementation_summary")
    op.drop_column("confirmation_round", "source_round_id")

    op.drop_constraint(
        "fk_implementation_plan_version_source_version_id",
        "implementation_plan_version",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_implementation_plan_current_version_id",
        "implementation_plan",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_implementation_plan_source_design_review_id",
        "implementation_plan",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_implementation_plan_source_prd_version_id",
        "implementation_plan",
        type_="foreignkey",
    )
    op.drop_index(
        "idx_implementation_plan_source_design_review", table_name="implementation_plan"
    )
    op.drop_index(
        "idx_implementation_plan_source_prd_version", table_name="implementation_plan"
    )
    op.drop_column("implementation_plan", "source_design_review_id")
    op.drop_column("implementation_plan", "source_prd_version_id")
