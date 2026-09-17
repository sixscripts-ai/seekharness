"""store the non-secret Neon branch handle for Battle cleanup

Revision ID: e7f9a4c2d1b0
Revises: 014ec2a0cab0
Create Date: 2026-09-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f9a4c2d1b0"
down_revision: Union[str, Sequence[str], None] = "014ec2a0cab0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add only the cleanup handle; connection strings stay out of storage."""
    conn = op.get_bind()
    columns = {column["name"] for column in sa.inspect(conn).get_columns("battles")}
    if "battle_db_branch_id" not in columns:
        op.add_column(
            "battles",
            sa.Column("battle_db_branch_id", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    """Remove the Battle cleanup handle."""
    conn = op.get_bind()
    columns = {column["name"] for column in sa.inspect(conn).get_columns("battles")}
    if "battle_db_branch_id" in columns:
        op.drop_column("battles", "battle_db_branch_id")

