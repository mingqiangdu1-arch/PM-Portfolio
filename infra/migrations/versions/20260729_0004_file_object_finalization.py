"""Persist the immutable object-store version/finalization identifier.

Revision ID: 20260729_0004
Revises: 20260729_0003
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260729_0004"
down_revision: str | None = "20260729_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "file_version",
        sa.Column("storage_version_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "idx_file_storage_version",
        "file_version",
        ["storage_version_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = int(
        bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM `file_version` WHERE `storage_version_id` IS NOT NULL"
            )
        ).scalar_one()
    )
    if populated:
        raise RuntimeError(
            "Refusing lossy downgrade of 20260729_0004: immutable storage version IDs exist"
        )
    op.drop_index("idx_file_storage_version", table_name="file_version")
    op.drop_column("file_version", "storage_version_id")
