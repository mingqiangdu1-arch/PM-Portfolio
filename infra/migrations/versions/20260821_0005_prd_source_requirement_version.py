"""Bind each PRD to its confirmed source Requirement Version.

Revision ID: 20260821_0005
Revises: 20260729_0004
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "20260821_0005"
down_revision: str | None = "20260729_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prd",
        sa.Column(
            "source_requirement_version_id",
            mysql.BIGINT(unsigned=True),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_prd_source_requirement_version",
        "prd",
        ["source_requirement_version_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_prd_source_requirement_version_id",
        "prd",
        "requirement_version",
        ["source_requirement_version_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def downgrade() -> None:
    bind = op.get_bind()
    prd_rows = int(bind.execute(sa.text("SELECT COUNT(*) FROM `prd`")).scalar_one())
    if prd_rows:
        raise RuntimeError(
            "Refusing lossy downgrade of 20260821_0005: PRD data exists"
        )
    op.drop_constraint(
        "fk_prd_source_requirement_version_id", "prd", type_="foreignkey"
    )
    op.drop_index("idx_prd_source_requirement_version", table_name="prd")
    op.drop_column("prd", "source_requirement_version_id")
