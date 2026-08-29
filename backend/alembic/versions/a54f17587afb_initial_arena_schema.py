"""initial arena schema

Revision ID: a54f17587afb
Revises:
Create Date: 2026-08-29 09:23:10.047478

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a54f17587afb'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Tables are created parents-first so foreign-key dependents can reference them.
    op.create_table('battles',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('format_id', sa.String(length=64), nullable=False),
    sa.Column('arena_size', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('timeout_seconds', sa.Integer(), nullable=False),
    sa.Column('round_visibility', sa.String(length=32), nullable=False),
    sa.Column('saved', sa.Boolean(), nullable=False),
    sa.Column('sandbox_id', sa.String(length=128), nullable=True),
    sa.Column('judge_provider_id', sa.String(length=64), nullable=True),
    sa.Column('preview_urls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('difficulty', sa.String(length=32), nullable=True),
    sa.Column('draft_id', sa.String(length=64), nullable=True),
    sa.Column('battle_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('spec_hash', sa.String(length=128), nullable=True),
    sa.Column('custom_title', sa.String(length=255), nullable=True),
    sa.Column('ranked', sa.Boolean(), nullable=True),
    sa.Column('target_id', sa.String(length=64), nullable=True),
    sa.Column('target_version', sa.String(length=32), nullable=True),
    sa.Column('target_manifest_hash', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name='ck_battles_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_battles_created_at', 'battles', ['created_at'], unique=False)
    op.create_index('ix_battles_format_id', 'battles', ['format_id'], unique=False)
    op.create_index('ix_battles_status', 'battles', ['status'], unique=False)
    op.create_index('ix_battles_target_id', 'battles', ['target_id'], unique=False)
    op.create_index('ix_battles_user_id', 'battles', ['user_id'], unique=False)
    op.create_index('ix_battles_user_saved', 'battles', ['user_id', 'saved'], unique=False)
    op.create_index('ix_battles_user_status', 'battles', ['user_id', 'status'], unique=False)
    op.create_table('formats',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('engine', sa.String(length=64), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', name='uq_formats_name')
    )
    op.create_table('leaderboard',
    sa.Column('model_id', sa.String(length=255), nullable=False),
    sa.Column('scope', sa.String(length=64), nullable=False),
    sa.Column('elo', sa.Float(), nullable=False),
    sa.Column('games_played', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('model_id', 'scope')
    )
    op.create_table('memories',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('insight', sa.Text(), nullable=False),
    sa.Column('tokens', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('battle_id', sa.String(length=64), nullable=True),
    sa.Column('model_id', sa.String(length=255), nullable=True),
    sa.Column('format', sa.String(length=64), nullable=True),
    sa.Column('chosen_skills', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('theory', sa.Text(), nullable=True),
    sa.Column('outcome', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_memories_battle_id', 'memories', ['battle_id'], unique=False)
    op.create_index('ix_memories_created_at', 'memories', ['created_at'], unique=False)
    op.create_index('ix_memories_user_id', 'memories', ['user_id'], unique=False)
    op.create_table('providers',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('base_url', sa.Text(), nullable=False),
    sa.Column('encrypted_key', sa.Text(), nullable=False),
    sa.Column('masked_key', sa.String(length=64), nullable=False),
    sa.Column('auth_style', sa.String(length=32), nullable=False),
    sa.Column('model_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', name='uq_providers_user_name')
    )
    op.create_index('ix_providers_user_id', 'providers', ['user_id'], unique=False)
    op.create_table('skills',
    sa.Column('skill', sa.String(length=128), nullable=False),
    sa.Column('elo', sa.Float(), nullable=False),
    sa.Column('wins', sa.Integer(), nullable=False),
    sa.Column('losses', sa.Integer(), nullable=False),
    sa.Column('draws', sa.Integer(), nullable=False),
    sa.Column('uses', sa.Integer(), nullable=False),
    sa.Column('success_rate', sa.Float(), nullable=False),
    sa.Column('tier', sa.String(length=32), nullable=True),
    sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('last_used', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('skill')
    )
    op.create_table('battle_drafts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('mode', sa.String(length=32), nullable=False),
    sa.Column('transcript', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('spec', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('launched_battle_id', sa.String(length=64), nullable=True),
    sa.Column('architect_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['launched_battle_id'], ['battles.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_battle_drafts_status', 'battle_drafts', ['status'], unique=False)
    op.create_index('ix_battle_drafts_user_id', 'battle_drafts', ['user_id'], unique=False)
    op.create_table('battle_events',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('battle_id', sa.String(length=64), nullable=False),
    sa.Column('event_id', sa.String(length=128), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', name='uq_battle_events_event_id')
    )
    op.create_index('ix_battle_events_battle_created', 'battle_events', ['battle_id', 'created_at'], unique=False)
    op.create_index('ix_battle_events_battle_type', 'battle_events', ['battle_id', 'event_type'], unique=False)
    op.create_index('ix_battle_events_sequence', 'battle_events', ['sequence'], unique=False)
    op.create_table('battle_participants',
    sa.Column('battle_id', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('model_id', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('battle_id', 'position')
    )
    op.create_index('ix_battle_participants_model_id', 'battle_participants', ['model_id'], unique=False)
    op.create_table('rounds',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('battle_id', sa.String(length=64), nullable=False),
    sa.Column('phase', sa.String(length=64), nullable=False),
    sa.Column('model_id', sa.String(length=255), nullable=False),
    sa.Column('artifact', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rounds_battle_id', 'rounds', ['battle_id'], unique=False)
    op.create_index('ix_rounds_battle_phase_model', 'rounds', ['battle_id', 'phase', 'model_id'], unique=False)
    op.create_table('scores',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('battle_id', sa.String(length=64), nullable=False),
    sa.Column('model_id', sa.String(length=255), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('judge_model', sa.String(length=255), nullable=True),
    sa.Column('justification', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('battle_id', 'model_id', name='uq_scores_battle_model')
    )
    op.create_index('ix_scores_battle_id', 'scores', ['battle_id'], unique=False)
    op.create_index('ix_scores_model_id', 'scores', ['model_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop dependents before their parents.
    op.drop_index('ix_scores_model_id', table_name='scores')
    op.drop_index('ix_scores_battle_id', table_name='scores')
    op.drop_table('scores')
    op.drop_index('ix_rounds_battle_phase_model', table_name='rounds')
    op.drop_index('ix_rounds_battle_id', table_name='rounds')
    op.drop_table('rounds')
    op.drop_index('ix_battle_participants_model_id', table_name='battle_participants')
    op.drop_table('battle_participants')
    op.drop_index('ix_battle_events_sequence', table_name='battle_events')
    op.drop_index('ix_battle_events_battle_type', table_name='battle_events')
    op.drop_index('ix_battle_events_battle_created', table_name='battle_events')
    op.drop_table('battle_events')
    op.drop_index('ix_battle_drafts_user_id', table_name='battle_drafts')
    op.drop_index('ix_battle_drafts_status', table_name='battle_drafts')
    op.drop_table('battle_drafts')
    op.drop_table('skills')
    op.drop_index('ix_providers_user_id', table_name='providers')
    op.drop_table('providers')
    op.drop_index('ix_memories_user_id', table_name='memories')
    op.drop_index('ix_memories_created_at', table_name='memories')
    op.drop_index('ix_memories_battle_id', table_name='memories')
    op.drop_table('memories')
    op.drop_table('leaderboard')
    op.drop_table('formats')
    op.drop_index('ix_battles_user_status', table_name='battles')
    op.drop_index('ix_battles_user_saved', table_name='battles')
    op.drop_index('ix_battles_user_id', table_name='battles')
    op.drop_index('ix_battles_target_id', table_name='battles')
    op.drop_index('ix_battles_status', table_name='battles')
    op.drop_index('ix_battles_format_id', table_name='battles')
    op.drop_index('ix_battles_created_at', table_name='battles')
    op.drop_table('battles')
