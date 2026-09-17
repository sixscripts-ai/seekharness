"""create users table for native authentication

Revision ID: f1a2b3c4d5e6
Revises: e7f9a4c2d1b0
Create Date: 2026-09-16

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e7f9a4c2d1b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "users" in tables:
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
