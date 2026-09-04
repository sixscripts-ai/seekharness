"""memories_pgvector_embedding

Revision ID: 014ec2a0cab0
Revises: c3e1a8b9f0d2
Create Date: 2026-09-04 01:30:49.211576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014ec2a0cab0'
down_revision: Union[str, Sequence[str], None] = 'c3e1a8b9f0d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pgvector extension and embedding column with HNSW index."""
    conn = op.get_bind()
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

    insp = sa.inspect(conn)
    mem_cols = [c["name"] for c in insp.get_columns("memories")]
    if "embedding" not in mem_cols:
        conn.execute(
            sa.text(
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(1536);"
            )
        )

    indexes = [idx["name"] for idx in insp.get_indexes("memories")]
    if "ix_memories_embedding" not in indexes:
        conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);"
            )
        )


def downgrade() -> None:
    """Drop embedding column and HNSW index."""
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding;")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding;")
