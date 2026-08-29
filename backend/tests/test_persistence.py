"""PostgreSQL persistence tests.

Runs against the Neon dev branch using an isolated throwaway schema per test
session (schema_translate_map), so the dev schema stays clean and no Appwrite
is required. Skips entirely when DATABASE_URL is not configured.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from agent_arena.persistence import repositories
from agent_arena.persistence.engine import database_url, sqlalchemy_url
from agent_arena.persistence.models import (
    Base,
    Battle,
    BattleEvent,
    BattleParticipant,
    Round,
    Score,
)
from agent_arena.persistence.session import session_scope


def _have_db() -> bool:
    try:
        database_url()
        return True
    except RuntimeError:
        return False


pytestmark = pytest.mark.skipif(not _have_db(), reason="DATABASE_URL not configured")


@pytest.fixture(scope="session")
def pg_engine():
    schema = f"ptest_{uuid.uuid4().hex[:12]}"
    eng = create_engine(
        sqlalchemy_url(),
        execution_options={"schema_translate_map": {None: schema}},
        poolclass=None,
    )
    with eng.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.commit()
    Base.metadata.create_all(eng)
    yield eng
    with eng.connect() as conn:
        conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        conn.commit()
    eng.dispose()


@pytest.fixture()
def pg_session(pg_engine):
    factory = sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)
    session = factory()
    yield session
    session.close()


def _create_battle(session, **overrides):
    defaults = dict(
        user_id="user-1",
        format_id="debugging-race",
        arena_size=2,
        timeout_seconds=600,
        round_visibility="isolated",
        model_ids=["host:modal-kimi", "host:openrouter-free"],
        roles=["builder", "breaker"],
    )
    defaults.update(overrides)
    return repositories.battles.battle_create(session, **defaults)


def test_schema_creation(pg_engine):
    """All expected tables exist in the isolated schema; no targets/users tables."""
    tables = set(Base.metadata.tables.keys())
    assert tables == {
        "providers",
        "formats",
        "battles",
        "battle_participants",
        "battle_drafts",
        "battle_events",
        "rounds",
        "scores",
        "leaderboard",
        "skills",
        "memories",
    }
    assert "targets" not in tables
    assert "users" not in tables


def test_jsonb_round_trips(pg_session):
    cfg = {
        "roles": ["a", "b"],
        "nested": {"deep": [1, 2, {"x": True}]},
        "difficulty": "expert",
    }
    fmt = repositories.formats.format_create(
        pg_session, name="round-trip-format", engine="agent_tool_race", config=cfg
    )
    pg_session.commit()
    loaded = repositories.formats.format_list(pg_session)[0]
    assert loaded.config == cfg
    assert loaded.config["nested"]["deep"][2]["x"] is True

    battle = _create_battle(
        pg_session,
        battle_config={"plan": {"phases": [{"actor": "builder"}]}, "target_id": "t1"},
        preview_urls={"fighter": {"url": "https://example.test/p"}},
    )
    pg_session.commit()
    reloaded = repositories.battles.battle_get(pg_session, battle.id)
    assert reloaded.battle_config["plan"]["phases"][0]["actor"] == "builder"
    assert reloaded.preview_urls["fighter"]["url"] == "https://example.test/p"


def test_round_artifact_enrichment_columns(pg_session):
    battle = _create_battle(pg_session, battle_config={"roles": ["builder", "breaker"]})
    pg_session.commit()
    pg_session.add(
        Round(
            battle_id=battle.id,
            phase="build",
            model_id="host:opencode-go",
            artifact="applied patch to starter/app.py",
            tool_trace={
                "steps": [
                    {"tool": "read", "path": "starter/app.py"},
                    {"tool": "edit", "path": "starter/app.py"},
                ]
            },
            verification_log="3 passed, 1 failed in 2.31s",
            meta={"runner": "sandbox", "is_mock": False, "duration_ms": 4120},
        )
    )
    pg_session.commit()
    pg_session.expire_all()
    row = pg_session.scalar(
        select(Round).where(
            Round.battle_id == battle.id, Round.model_id == "host:opencode-go"
        )
    )
    assert row.tool_trace["steps"][1]["tool"] == "edit"
    assert row.tool_trace["steps"][1]["path"] == "starter/app.py"
    assert "3 passed, 1 failed" in row.verification_log
    assert row.meta["is_mock"] is False
    assert row.meta["runner"] == "sandbox"


def test_provider_uniqueness_per_user_name(pg_session):
    repositories.providers.provider_create(
        pg_session,
        user_id="u1",
        name="Anthropic",
        base_url="https://x",
        encrypted_key="cipher-a",
        masked_key="sk-...abcd",
    )
    pg_session.commit()
    # same name, different user -> allowed
    repositories.providers.provider_create(
        pg_session,
        user_id="u2",
        name="Anthropic",
        base_url="https://x",
        encrypted_key="cipher-b",
    )
    pg_session.commit()
    # same user, same name -> unique violation
    with pytest.raises(Exception) as excinfo:
        repositories.providers.provider_create(
            pg_session,
            user_id="u1",
            name="Anthropic",
            base_url="https://y",
            encrypted_key="cipher-c",
        )
        pg_session.commit()
    pg_session.rollback()
    assert "uq_providers_user_name" in str(excinfo.value)


def test_participant_ordering_and_model_ids(pg_session):
    battle = _create_battle(
        pg_session,
        model_ids=["host:a", "host:b", "host:c"],
        roles=["builder", "breaker", None],
    )
    pg_session.commit()
    assert repositories.battles.battle_model_ids(pg_session, battle.id) == [
        "host:a",
        "host:b",
        "host:c",
    ]


def test_host_model_ids_need_no_provider_rows(pg_session):
    battle = _create_battle(pg_session, model_ids=["host:virtual-1", "host:virtual-2"])
    pg_session.commit()
    rows = pg_session.scalars(
        select(BattleParticipant).where(BattleParticipant.battle_id == battle.id)
    ).all()
    assert {r.model_id for r in rows} == {"host:virtual-1", "host:virtual-2"}


def test_cascade_delete_battle_children(pg_session):
    battle = _create_battle(pg_session)
    repositories.events.event_append(
        pg_session,
        battle.id,
        "phase_start",
        {"phase": "build"},
        event_id="evt-1",
        sequence=1,
    )
    pg_session.add(
        Round(battle_id=battle.id, phase="build", model_id="host:a", artifact="log")
    )
    repositories.scores.score_insert(
        pg_session, battle_id=battle.id, model_id="host:a", score=1.0
    )
    pg_session.commit()

    pg_session.delete(pg_session.get(Battle, battle.id))
    pg_session.commit()

    assert (
        pg_session.scalars(
            select(BattleParticipant).where(BattleParticipant.battle_id == battle.id)
        ).all()
        == []
    )
    assert (
        pg_session.scalars(
            select(BattleEvent).where(BattleEvent.battle_id == battle.id)
        ).all()
        == []
    )
    assert (
        pg_session.scalars(select(Round).where(Round.battle_id == battle.id)).all()
        == []
    )
    assert (
        pg_session.scalars(select(Score).where(Score.battle_id == battle.id)).all()
        == []
    )


def test_score_uniqueness_idempotent(pg_session):
    battle = _create_battle(pg_session)
    pg_session.commit()
    repositories.scores.score_insert(
        pg_session, battle_id=battle.id, model_id="host:a", score=10.0
    )
    pg_session.commit()
    repositories.scores.score_insert(
        pg_session, battle_id=battle.id, model_id="host:a", score=99.0
    )
    pg_session.commit()
    rows = repositories.scores.score_list(pg_session, battle.id)
    assert len(rows) == 1
    assert rows[0].score == 10.0  # first write wins


def test_leaderboard_composite_key_upsert(pg_session):
    repositories.leaderboard.leaderboard_upsert(
        pg_session, "host:a", "overall", elo=1200.0, games_played=1
    )
    pg_session.commit()
    repositories.leaderboard.leaderboard_upsert(
        pg_session, "host:a", "overall", elo=1250.0, games_played=2
    )
    pg_session.commit()
    # same model in a different scope is a separate row
    repositories.leaderboard.leaderboard_upsert(
        pg_session, "host:a", "debugging-race", elo=1100.0, games_played=1
    )
    pg_session.commit()
    entry = repositories.leaderboard.leaderboard_get(pg_session, "host:a", "overall")
    assert entry.elo == 1250.0 and entry.games_played == 2
    overall = repositories.leaderboard.leaderboard_list(pg_session, "overall")
    assert len(overall) == 1


def test_event_id_uniqueness(pg_session):
    battle = _create_battle(pg_session)
    pg_session.commit()
    first = repositories.events.event_append(
        pg_session, battle.id, "battle_status", {"status": "queued"}, event_id="dup-1"
    )
    pg_session.commit()
    second = repositories.events.event_append(
        pg_session, battle.id, "battle_status", {"status": "running"}, event_id="dup-1"
    )
    pg_session.commit()
    rows = repositories.events.event_list(pg_session, battle.id)
    assert len(rows) == 1
    assert rows[0].payload == {"status": "queued"}
    assert second.id == first.id


def test_battle_target_fields_persist(pg_session):
    battle = _create_battle(
        pg_session,
        target_id="authentication-gate",
        target_version="1.0.0",
        target_manifest_hash="ab" * 32,
        spec_hash="cd" * 32,
    )
    pg_session.commit()
    loaded = repositories.battles.battle_get(pg_session, battle.id)
    assert loaded.target_id == "authentication-gate"
    assert loaded.target_version == "1.0.0"
    assert loaded.target_manifest_hash == "ab" * 32
    assert loaded.spec_hash == "cd" * 32  # legacy semantics preserved


def test_battle_status_check_constraint(pg_session):
    battle = _create_battle(pg_session, status="queued")
    pg_session.commit()
    repositories.battles.battle_update(pg_session, battle.id, status="running")
    pg_session.commit()
    # The invalid status is rejected by the CHECK constraint at flush time.
    with pytest.raises(Exception) as excinfo:
        repositories.battles.battle_update(pg_session, battle.id, status="exploding")
    pg_session.rollback()
    message = str(excinfo.value) + " " + str(getattr(excinfo.value, "orig", ""))
    assert "ck_battles_status" in message


def test_timestamps_are_timezone_aware(pg_session):
    battle = _create_battle(pg_session)
    pg_session.commit()
    loaded = repositories.battles.battle_get(pg_session, battle.id)
    assert loaded.created_at.tzinfo is not None
    assert loaded.updated_at.tzinfo is not None


def test_draft_optimistic_revision(pg_session):
    draft = repositories.drafts.draft_create(pg_session, user_id="u1", mode="quick")
    pg_session.commit()
    _, applied = repositories.drafts.draft_update(
        pg_session, draft.id, expected_revision=0, spec={"title": "v1"}
    )
    assert applied is True
    pg_session.commit()
    # stale revision is rejected without applying
    _, applied2 = repositories.drafts.draft_update(
        pg_session, draft.id, expected_revision=0, spec={"title": "stale"}
    )
    assert applied2 is False
    pg_session.commit()
    loaded = repositories.drafts.draft_get(pg_session, draft.id)
    assert loaded.revision == 1
    assert loaded.spec == {"title": "v1"}


def test_skills_and_memories_arrays(pg_session):
    repositories.skills.skill_upsert(
        pg_session, "web-audit", elo=1150.0, tags=["security", "web"], uses=3
    )
    pg_session.commit()
    repositories.skills.skill_upsert(pg_session, "web-audit", uses=4)
    pg_session.commit()
    skill = repositories.skills.skill_get(pg_session, "web-audit")
    assert skill.uses == 4
    assert skill.tags == ["security", "web"]

    repositories.memories.memory_create(
        pg_session,
        user_id="u1",
        insight="fighter repeats f-string quoting mistakes",
        tokens=["f-string", "quoting"],
        chosen_skills=["code-review"],
    )
    pg_session.commit()
    mems = repositories.memories.memory_list(pg_session, "u1")
    assert len(mems) == 1
    assert mems[0].tokens == ["f-string", "quoting"]
    assert mems[0].chosen_skills == ["code-review"]


def test_session_scope_does_not_leak_connections(pg_engine):
    from agent_arena.persistence.engine import engine as app_engine

    with session_scope() as session:
        session.execute(text("SELECT 1"))
    assert app_engine().pool.checkedout() == 0
