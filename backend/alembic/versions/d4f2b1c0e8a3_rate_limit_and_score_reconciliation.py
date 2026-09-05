"""battle_rate_limits and score_reconciliations

Revision ID: d4f2b1c0e8a3
Revises: 014ec2a0cab0
Create Date: 2026-09-04

Coordinated cutover: deploy this migration with the atomic limiter and
score-repair CLI in the same release.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4f2b1c0e8a3"
down_revision: Union[str, Sequence[str], None] = "014ec2a0cab0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if "battle_rate_limits" not in tables:
        op.create_table(
            "battle_rate_limits",
            sa.Column("battle_id", sa.String(length=64), nullable=False),
            sa.Column(
                "window_ts",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("battle_id"),
        )

    if "score_reconciliations" not in tables:
        op.create_table(
            "score_reconciliations",
            sa.Column("battle_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("judge_model", sa.String(length=255), nullable=True),
            sa.Column(
                "repaired_scores",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('scores_repaired_elo_pending', 'elo_acknowledged')",
                name="ck_score_reconciliations_status",
            ),
            sa.ForeignKeyConstraint(
                ["battle_id"], ["battles.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("battle_id"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()
    if "score_reconciliations" in tables:
        op.drop_table("score_reconciliations")
    if "battle_rate_limits" in tables:
        op.drop_table("battle_rate_limits")
