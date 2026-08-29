"""rounds artifact enrichment (tool_trace / verification_log / meta)

Revision ID: b2c0a3d9e1f7
Revises: a54f17587afb
Create Date: 2026-08-29

Additive, nullable-only. Existing 25 round rows are unaffected.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c0a3d9e1f7"
down_revision: Union[str, Sequence[str], None] = "a54f17587afb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable enrichment columns to rounds."""
    op.add_column(
        "rounds",
        sa.Column(
            "tool_trace",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "rounds",
        sa.Column("verification_log", sa.Text(), nullable=True),
    )
    op.add_column(
        "rounds",
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop enrichment columns."""
    op.drop_column("rounds", "meta")
    op.drop_column("rounds", "verification_log")
    op.drop_column("rounds", "tool_trace")
