"""Make active sessions and refresh-token family rotation representable.

Revision ID: 20260729_0003
Revises: 20260729_0002
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "20260729_0003"
down_revision: str | None = "20260729_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "user_session",
        "revoked_at",
        existing_type=mysql.DATETIME(fsp=6),
        nullable=True,
    )
    op.add_column(
        "user_session",
        sa.Column(
            "token_family_id",
            mysql.CHAR(36, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
    )
    # session_public_id is an existing stable UUID and is the only lossless family
    # identity for pre-rotation rows. No rotation history is fabricated.
    op.execute(
        sa.text(
            "UPDATE `user_session` SET `token_family_id` = `session_public_id` "
            "WHERE `token_family_id` IS NULL"
        )
    )
    op.alter_column(
        "user_session",
        "token_family_id",
        existing_type=mysql.CHAR(36, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )
    op.add_column(
        "user_session",
        sa.Column("rotated_at", mysql.DATETIME(fsp=6), nullable=True),
    )
    op.add_column(
        "user_session",
        sa.Column("replaced_by_session_id", mysql.BIGINT(unsigned=True), nullable=True),
    )
    op.create_unique_constraint(
        "uk_user_session_replaced_by",
        "user_session",
        ["replaced_by_session_id"],
    )
    op.create_index(
        "idx_session_family_state",
        "user_session",
        ["token_family_id", "revoked_at", "expires_at", "id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_user_session_replaced_by_session_id",
        "user_session",
        "user_session",
        ["replaced_by_session_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def _unsafe_downgrade_rows(bind: sa.engine.Connection) -> int:
    return int(
        bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM `user_session` "
                "WHERE `revoked_at` IS NULL "
                "OR `rotated_at` IS NOT NULL "
                "OR `replaced_by_session_id` IS NOT NULL "
                "OR BINARY `token_family_id` <> BINARY `session_public_id`"
            )
        ).scalar_one()
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _unsafe_downgrade_rows(bind):
        raise RuntimeError(
            "Refusing lossy downgrade of 20260729_0003: active or rotated session data exists"
        )

    op.drop_constraint(
        "fk_user_session_replaced_by_session_id", "user_session", type_="foreignkey"
    )
    op.drop_index("idx_session_family_state", table_name="user_session")
    op.drop_constraint("uk_user_session_replaced_by", "user_session", type_="unique")
    op.drop_column("user_session", "replaced_by_session_id")
    op.drop_column("user_session", "rotated_at")
    op.drop_column("user_session", "token_family_id")
    op.alter_column(
        "user_session",
        "revoked_at",
        existing_type=mysql.DATETIME(fsp=6),
        nullable=False,
    )
