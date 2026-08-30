"""authoritative battle results and battle finalized_at (Change Set C)

Revision ID: c3e1a8b9f0d2
Revises: b2c0a3d9e1f7
Create Date: 2026-08-30

Additive, non-destructive schema migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3e1a8b9f0d2"
down_revision: Union[str, Sequence[str], None] = "b2c0a3d9e1f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add finalized_at to battles and create battle_results table."""
    # 1. Add finalized_at column to battles table
    op.add_column(
        "battles",
        sa.Column(
            "finalized_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 2. Create canonical battle_results table
    op.create_table(
        "battle_results",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("battle_id", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=False, server_default="main"),
        sa.Column("role", sa.String(length=64), nullable=False, server_default="fighter"),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="unverified"),
        sa.Column("termination_reason", sa.String(length=64), nullable=True),
        sa.Column("artifact_refs", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("result_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["battle_id"], ["battles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("battle_id", "phase", "role", "model_id", name="uq_battle_results_identity"),
    )
    op.create_index("ix_battle_results_battle_id", "battle_results", ["battle_id"], unique=False)
    op.create_index("ix_battle_results_model_id", "battle_results", ["model_id"], unique=False)

    # Change Set B provenance on Postgres memories (must not weaken Appwrite policy)
    op.add_column("memories", sa.Column("target_id", sa.String(length=64), nullable=True))
    op.add_column("memories", sa.Column("role", sa.String(length=64), nullable=True))
    op.add_column("memories", sa.Column("visibility_class", sa.String(length=64), nullable=True))
    op.add_column("memories", sa.Column("authoritative_status", sa.String(length=64), nullable=True))
    op.add_column("memories", sa.Column("context_mode", sa.String(length=32), nullable=True))
    op.add_column("memories", sa.Column("source_result_id", sa.String(length=64), nullable=True))
    op.create_index("ix_memories_model_id", "memories", ["model_id"], unique=False)
    op.create_index("ix_memories_target_id", "memories", ["target_id"], unique=False)


def downgrade() -> None:
    """Drop battle_results table and finalized_at column."""
    op.drop_index("ix_memories_target_id", table_name="memories")
    op.drop_index("ix_memories_model_id", table_name="memories")
    op.drop_column("memories", "source_result_id")
    op.drop_column("memories", "context_mode")
    op.drop_column("memories", "authoritative_status")
    op.drop_column("memories", "visibility_class")
    op.drop_column("memories", "role")
    op.drop_column("memories", "target_id")
    op.drop_index("ix_battle_results_model_id", table_name="battle_results")
    op.drop_index("ix_battle_results_battle_id", table_name="battle_results")
    op.drop_table("battle_results")
    op.drop_column("battles", "finalized_at")
