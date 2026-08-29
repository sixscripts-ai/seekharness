"""SQLAlchemy 2.x models for the PostgreSQL persistence layer.

Designed from current runtime usages (battles.py, battle_drafts.py,
providers.py, memory.py, skills_registry.py, event_bus usage) — NOT from the
checked-in Appwrite schema.py, which is known to lag the live schema.

Conventions:
  - TIMESTAMPTZ columns everywhere (DateTime(timezone=True))
  - structured data is JSONB, never a serialized JSON string
  - status is a CHECK constraint, not a Postgres ENUM
  - Appwrite document ids are plain strings; no users table (Appwrite Auth
    remains the identity provider)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """Declarative base; metadata is consumed by Alembic."""


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_providers_user_name"),
        Index("ix_providers_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    # Fernet ciphertext only. FERNET_KEY stays a backend secret and is never
    # stored in PostgreSQL.
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    masked_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    auth_style: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Format(Base):
    __tablename__ = "formats"
    __table_args__ = (UniqueConstraint("name", name="uq_formats_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Battle(Base):
    __tablename__ = "battles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_battles_status",
        ),
        Index("ix_battles_user_id", "user_id"),
        Index("ix_battles_user_status", "user_id", "status"),
        Index("ix_battles_user_saved", "user_id", "saved"),
        Index("ix_battles_status", "status"),
        Index("ix_battles_format_id", "format_id"),
        Index("ix_battles_target_id", "target_id"),
        Index("ix_battles_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    format_id: Mapped[str] = mapped_column(String(64), nullable=False)
    arena_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    round_visibility: Mapped[str] = mapped_column(String(32), nullable=False)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sandbox_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    judge_provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_urls: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    difficulty: Mapped[str | None] = mapped_column(String(32), nullable=True)
    draft_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    battle_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    spec_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    custom_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ranked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Target manifest hash. The legacy spec_hash field keeps its existing
    # semantics; for target battles this column carries the immutable
    # manifest hash (initialized from spec_hash during migration when absent).
    target_manifest_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BattleParticipant(Base):
    """Ordered model slots for a battle (replaces serialized model_ids)."""

    __tablename__ = "battle_participants"
    __table_args__ = (Index("ix_battle_participants_model_id", "model_id"),)

    battle_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("battles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BattleDraft(Base):
    __tablename__ = "battle_drafts"
    __table_args__ = (
        Index("ix_battle_drafts_user_id", "user_id"),
        Index("ix_battle_drafts_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    transcript: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="drafting")
    launched_battle_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("battles.id", ondelete="SET NULL"),
        nullable=True,
    )
    architect_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BattleEvent(Base):
    __tablename__ = "battle_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_battle_events_event_id"),
        Index("ix_battle_events_battle_created", "battle_id", "created_at"),
        Index("ix_battle_events_battle_type", "battle_id", "event_type"),
        Index("ix_battle_events_sequence", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    battle_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("battles.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Round(Base):
    __tablename__ = "rounds"
    __table_args__ = (
        Index("ix_rounds_battle_id", "battle_id"),
        Index("ix_rounds_battle_phase_model", "battle_id", "phase", "model_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    battle_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("battles.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_trace: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    verification_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # runner, duration_ms, tokens, cost_usd, is_mock
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("battle_id", "model_id", name="uq_scores_battle_model"),
        Index("ix_scores_battle_id", "battle_id"),
        Index("ix_scores_model_id", "model_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    battle_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("battles.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    judge_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LeaderboardEntry(Base):
    """Ranking rows keyed by (model_id, scope).

    The Appwrite format_id column maps to scope during migration; the API
    layer can alias scope back to format_id for frontend compatibility.
    """

    __tablename__ = "leaderboard"

    model_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    elo: Mapped[float] = mapped_column(Float, nullable=False)
    games_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SkillRecord(Base):
    __tablename__ = "skills"

    skill: Mapped[str] = mapped_column(String(128), primary_key=True)
    elo: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draws: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    last_used: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_id", "user_id"),
        Index("ix_memories_battle_id", "battle_id"),
        Index("ix_memories_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    insight: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    battle_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chosen_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    theory: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
