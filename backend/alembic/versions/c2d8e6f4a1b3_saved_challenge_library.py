"""persist account-owned saved challenge membership

Revision ID: c2d8e6f4a1b3
Revises: f1a2b3c4d5e6
Create Date: 2026-09-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2d8e6f4a1b3"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    columns = {column["name"] for column in sa.inspect(conn).get_columns("battle_drafts")}
    if "saved" not in columns:
        op.add_column(
            "battle_drafts",
            sa.Column("saved", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    indexes = {index["name"] for index in sa.inspect(conn).get_indexes("battle_drafts")}
    if "ix_battle_drafts_user_saved" not in indexes:
        op.create_index(
            "ix_battle_drafts_user_saved", "battle_drafts", ["user_id", "saved"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(conn).get_indexes("battle_drafts")}
    if "ix_battle_drafts_user_saved" in indexes:
        op.drop_index("ix_battle_drafts_user_saved", table_name="battle_drafts")
    columns = {column["name"] for column in sa.inspect(conn).get_columns("battle_drafts")}
    if "saved" in columns:
        op.drop_column("battle_drafts", "saved")
