"""Real PostgreSQL concurrency tests for Change Set C finalization.

These are not Python threading.Lock simulations. They open concurrent DB
sessions against an isolated throwaway schema. They never use production Neon.
"""

from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from agent_arena.finalization import finalize_battle
from agent_arena.persistence import repositories
from agent_arena.persistence.models import (
    Base,
    Battle,
    LeaderboardEntry,
    Memory,
    Round,
    Score,
    SkillRecord,
)
from agent_arena.persistence.session import SessionLocal
from agent_arena.results import TRUSTED_VERIFICATION_MARKER
from tests.pg_support import postgres_tests_enabled, sqlalchemy_test_url

pytestmark = pytest.mark.postgres


def _payload(mid: str, role: str, passed: bool, steps: int, skills: list[str] | None = None) -> str:
    body = {
        "model_id": mid,
        "role": role,
        "phase": "race",
        "outcome": "TEST_PASS" if passed else "TEST_FAIL",
        "passed": passed,
        "steps": steps,
        "skill_reads": skills or [],
        "artifact_checks": {"present": ["solution.py"], "missing": []},
        "theory": "keep the ping function correct",
    }
    return "EXECUTOR_RESULT: " + json.dumps(body)


def _trusted_payload(mid: str, role: str, passed: bool, steps: int, skills: list[str] | None = None) -> str:
    body = {
        "source": "trusted_verifier",
        "kind": "solo",
        "model_id": mid,
        "role": role,
        "phase": "race",
        "passed": passed,
        "outcome": "TEST_PASS" if passed else "TEST_FAIL",
        "verification_status": "verified_pass" if passed else "verified_fail",
        "steps": steps,
        "skill_reads": skills or [],
        "artifact_checks": {"present": ["solution.py"], "missing": []},
        "theory": "keep the ping function correct",
    }
    return TRUSTED_VERIFICATION_MARKER + " " + json.dumps(body)


def _trusted_override(
    mid: str, role: str, passed: bool, steps: int, skills: list[str] | None = None
) -> dict:
    return {
        "model_id": mid,
        "role": role,
        "phase": "race",
        "outcome": "TEST_PASS" if passed else "TEST_FAIL",
        "passed": passed,
        "steps": steps,
        "skill_reads": skills or [],
        "artifact_checks": {"present": ["solution.py"], "missing": []},
        "theory": "keep the ping function correct",
        "_trusted": True,
    }


@pytest.fixture(scope="module")
def pg_engine():
    if not postgres_tests_enabled():
        pytest.skip("ARENA_INTEGRATION_TESTS=1 and ARENA_PG_TEST_URL required")
    schema = f"c4test_{uuid.uuid4().hex[:12]}"
    eng = create_engine(
        sqlalchemy_test_url(),
        execution_options={"schema_translate_map": {None: schema}},
        poolclass=QueuePool,
        pool_size=8,
        max_overflow=8,
        pool_pre_ping=True,
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
def pg_bound(pg_engine, monkeypatch):
    SessionLocal._maker = sessionmaker(
        bind=pg_engine, expire_on_commit=False, autoflush=False
    )
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: True)
    monkeypatch.setattr("agent_arena.persistence.service.using_postgres", lambda: True)
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    monkeypatch.setenv("APPWRITE_DUAL_WRITE", "false")
    monkeypatch.setenv("APPWRITE_READ_FALLBACK", "false")
    from agent_arena.config import settings

    settings.cache_clear()
    yield pg_engine
    SessionLocal._maker = None


def _create_running_battle(
    session,
    *,
    model_ids: list[str],
    results: list[tuple[str, str, bool, int, list[str] | None]],
    context_mode: str = "adaptive",
    ranked: bool = True,
    target_id: str | None = None,
    user_id: str = "user-c",
) -> Battle:
    battle = repositories.battles.battle_create(
        session,
        user_id=user_id,
        format_id="fast-code",
        arena_size=len(model_ids),
        timeout_seconds=600,
        round_visibility="isolated",
        model_ids=model_ids,
        status="running",
        ranked=ranked,
        target_id=target_id,
        battle_config={"context_mode": context_mode},
    )
    for mid, role, passed, steps, skills in results:
        session.add(
            Round(
                battle_id=battle.id,
                phase="race",
                model_id=mid,
                artifact=_payload(mid, role, passed, steps, skills),
            )
        )
    session.commit()
    return battle


def _wait_for_blocked_backend(engine, *, timeout: float = 15.0) -> None:
    """Poll until a backend in this database is waiting on another transaction.

    Used only as a test observer. Production correctness remains PostgreSQL
    row locking inside finalize_battle, not this wait.
    """
    sql = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() "
        "AND pid <> pg_backend_pid() "
        "AND cardinality(pg_blocking_pids(pid)) > 0"
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.connect() as conn:
            n = conn.execute(sql).scalar_one()
            if int(n or 0) > 0:
                return
        time.sleep(0.02)
    raise TimeoutError("expected a PostgreSQL lock wait between finalize and round writer")


def _assert_no_authoritative_side_effects(session, bid: str, model_ids: list[str], skill: str) -> None:
    row = session.get(Battle, bid)
    assert row is not None
    assert row.status == "running"
    assert row.finalized_at is None
    assert row.failure_reason is None
    assert repositories.results.results_list_by_battle(session, bid) == []
    assert repositories.scores.score_list(session, bid) == []
    assert (
        session.scalars(
            select(LeaderboardEntry).where(LeaderboardEntry.model_id.in_(model_ids))
        ).first()
        is None
    )
    assert session.get(SkillRecord, skill) is None
    assert list(session.scalars(select(Memory).where(Memory.battle_id == bid))) == []


def _assert_completed_exactly_once(session, bid: str, model_ids: list[str], skill: str) -> None:
    row = session.get(Battle, bid)
    assert row.status == "completed"
    assert row.finalized_at is not None
    assert (row.failure_reason or "") != "INCOMPLETE_EVIDENCE"
    results = repositories.results.results_list_by_battle(session, bid)
    assert len(results) == 2
    identities = {(r.phase, r.role, r.model_id) for r in results}
    assert identities == {("race", "player_a", model_ids[0]), ("race", "player_b", model_ids[1])}
    scores = repositories.scores.score_list(session, bid)
    assert len(scores) == 2
    assert {s.model_id for s in scores} == set(model_ids)
    entries = list(
        session.scalars(select(LeaderboardEntry).where(LeaderboardEntry.model_id == model_ids[0]))
    )
    assert entries
    assert sum(e.games_played for e in entries) == 2
    skill_row = session.get(SkillRecord, skill)
    assert skill_row is not None
    assert skill_row.uses == 2
    assert skill_row.wins == 1
    assert skill_row.losses == 1
    memories = list(session.scalars(select(Memory).where(Memory.battle_id == bid)))
    assert len(memories) == 1


def _add_race_rounds(session, bid: str, mid_a: str, mid_b: str, skill: str) -> None:
    session.add(
        Round(
            battle_id=bid,
            phase="race",
            model_id=mid_a,
            artifact=_payload(mid_a, "player_a", True, 3, [skill]),
        )
    )
    session.add(
        Round(
            battle_id=bid,
            phase="race",
            model_id=mid_b,
            artifact=_payload(mid_b, "player_b", False, 8, [skill]),
        )
    )


def test_c1_duplicate_concurrent_finalize(pg_bound):
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    with factory() as session:
        battle = _create_running_battle(
            session,
            model_ids=["model-a", "model-b"],
            results=[
                ("model-a", "player_a", True, 3, ["shared-skill"]),
                ("model-b", "player_b", False, 9, ["shared-skill"]),
            ],
        )
        bid = battle.id

    start = threading.Barrier(2)

    overrides = [
        _trusted_override("model-a", "player_a", True, 3, ["shared-skill"]),
        _trusted_override("model-b", "player_b", False, 9, ["shared-skill"]),
    ]

    def _run():
        start.wait(timeout=10)
        return finalize_battle(bid, override_results=overrides)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_run)
        f2 = pool.submit(_run)
        r1 = f1.result()
        r2 = f2.result()

    flags = sorted([bool(r1.get("already_finalized")), bool(r2.get("already_finalized"))])
    assert flags == [False, True]
    winners = [r for r in (r1, r2) if not r.get("already_finalized")]
    assert len(winners) == 1
    assert winners[0]["status"] == "completed"
    assert winners[0].get("authoritative") is True

    with factory() as session:
        scores = repositories.scores.score_list(session, bid)
        assert len(scores) == 2
        row = session.get(Battle, bid)
        assert row.status == "completed"
        assert row.finalized_at is not None
        entries = list(
            session.scalars(select(LeaderboardEntry).where(LeaderboardEntry.model_id == "model-a"))
        )
        assert sum(e.games_played for e in entries) == 2  # target+overall or overall only
        skill = session.get(SkillRecord, "shared-skill")
        assert skill is not None
        assert skill.uses == 2  # both fighters loaded it: win + loss
        memories = list(session.scalars(select(Memory).where(Memory.battle_id == bid)))
        assert len(memories) == 1


def test_c2_concurrent_elo_two_battles_same_model(pg_bound):
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    with factory() as session:
        a = _create_running_battle(
            session,
            model_ids=["model-x", "model-y"],
            results=[
                ("model-x", "player_a", True, 2, []),
                ("model-y", "player_b", False, 7, []),
            ],
            target_id=None,
            context_mode="strict",
        )
        b = _create_running_battle(
            session,
            model_ids=["model-x", "model-z"],
            results=[
                ("model-x", "player_a", True, 2, []),
                ("model-z", "player_b", False, 7, []),
            ],
            target_id=None,
            context_mode="strict",
        )
        id_a, id_b = a.id, b.id

    start = threading.Barrier(2)
    import agent_arena.finalization as fin

    real_elo = fin._apply_leaderboard_elo_pg

    def _elo_overlap(session, battle, scores):
        start.wait(timeout=10)
        return real_elo(session, battle, scores)

    fin._apply_leaderboard_elo_pg = _elo_overlap
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(
                finalize_battle,
                id_a,
                override_results=[
                    _trusted_override("model-x", "player_a", True, 2),
                    _trusted_override("model-y", "player_b", False, 7),
                ],
            )
            f2 = pool.submit(
                finalize_battle,
                id_b,
                override_results=[
                    _trusted_override("model-x", "player_a", True, 2),
                    _trusted_override("model-z", "player_b", False, 7),
                ],
            )
            assert f1.result()["status"] == "completed"
            assert f2.result()["status"] == "completed"
    finally:
        fin._apply_leaderboard_elo_pg = real_elo

    with factory() as session:
        overall = session.scalars(
            select(LeaderboardEntry).where(
                LeaderboardEntry.model_id == "model-x",
                LeaderboardEntry.scope == "overall",
            )
        ).one()
        assert overall.games_played == 2
        assert overall.elo > 1230.0


def test_c3_missing_leaderboard_rows_race_safe(pg_bound):
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    m_new = f"mod_new_{uuid.uuid4().hex[:8]}"
    opp1 = f"opp1_{uuid.uuid4().hex[:8]}"
    opp2 = f"opp2_{uuid.uuid4().hex[:8]}"
    with factory() as session:
        existing = session.scalars(
            select(LeaderboardEntry).where(LeaderboardEntry.model_id == m_new)
        ).first()
        assert existing is None
        a = _create_running_battle(
            session,
            model_ids=[m_new, opp1],
            results=[
                (m_new, "player_a", True, 2, []),
                (opp1, "player_b", False, 8, []),
            ],
            context_mode="strict",
        )
        b = _create_running_battle(
            session,
            model_ids=[m_new, opp2],
            results=[
                (m_new, "player_a", True, 2, []),
                (opp2, "player_b", False, 8, []),
            ],
            context_mode="strict",
        )
        id_a, id_b = a.id, b.id

    start = threading.Barrier(2)
    import agent_arena.finalization as fin

    real_elo = fin._apply_leaderboard_elo_pg

    def _elo_overlap(session, battle, scores):
        start.wait(timeout=10)
        return real_elo(session, battle, scores)

    fin._apply_leaderboard_elo_pg = _elo_overlap
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(
                finalize_battle,
                id_a,
                override_results=[
                    _trusted_override(m_new, "player_a", True, 2),
                    _trusted_override(opp1, "player_b", False, 8),
                ],
            )
            f2 = pool.submit(
                finalize_battle,
                id_b,
                override_results=[
                    _trusted_override(m_new, "player_a", True, 2),
                    _trusted_override(opp2, "player_b", False, 8),
                ],
            )
            f1.result()
            f2.result()
    finally:
        fin._apply_leaderboard_elo_pg = real_elo

    with factory() as session:
        overall = session.scalars(
            select(LeaderboardEntry).where(
                LeaderboardEntry.model_id == m_new,
                LeaderboardEntry.scope == "overall",
            )
        ).one()
        assert overall.games_played == 2
        assert overall.elo > 1230.0


def test_c4_concurrent_skill_learning(pg_bound):
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    skill = f"skill_{uuid.uuid4().hex[:8]}"
    with factory() as session:
        a = _create_running_battle(
            session,
            model_ids=["m-skill-a1", "m-skill-a2"],
            results=[
                ("m-skill-a1", "player_a", True, 2, [skill]),
                ("m-skill-a2", "player_b", False, 9, [skill]),
            ],
            context_mode="adaptive",
        )
        b = _create_running_battle(
            session,
            model_ids=["m-skill-b1", "m-skill-b2"],
            results=[
                ("m-skill-b1", "player_a", True, 2, [skill]),
                ("m-skill-b2", "player_b", False, 9, [skill]),
            ],
            context_mode="adaptive",
        )
        id_a, id_b = a.id, b.id

    start = threading.Barrier(2)
    import agent_arena.finalization as fin

    real_learn = fin._apply_self_learning_pg

    def _learn_overlap(session, battle, results):
        start.wait(timeout=10)
        return real_learn(session, battle, results)

    fin._apply_self_learning_pg = _learn_overlap
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(
                finalize_battle,
                id_a,
                override_results=[
                    _trusted_override("m-skill-a1", "player_a", True, 2, [skill]),
                    _trusted_override("m-skill-a2", "player_b", False, 9, [skill]),
                ],
            )
            f2 = pool.submit(
                finalize_battle,
                id_b,
                override_results=[
                    _trusted_override("m-skill-b1", "player_a", True, 2, [skill]),
                    _trusted_override("m-skill-b2", "player_b", False, 9, [skill]),
                ],
            )
            assert f1.result()["status"] == "completed"
            assert f2.result()["status"] == "completed"
    finally:
        fin._apply_self_learning_pg = real_learn

    with factory() as session:
        row = session.get(SkillRecord, skill)
        assert row is not None
        assert row.uses == 4
        assert row.wins == 2
        assert row.losses == 2
        assert row.elo != 1200.0


def test_c5_rollback_then_retry_exactly_once(pg_bound, monkeypatch):
    import agent_arena.finalization as fin

    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    with factory() as session:
        battle = _create_running_battle(
            session,
            model_ids=["mod-a", "mod-b"],
            results=[
                ("mod-a", "player_a", True, 3, ["skill-rollback"]),
                ("mod-b", "player_b", False, 8, ["skill-rollback"]),
            ],
        )
        bid = battle.id

    real_learn = fin._apply_self_learning_pg
    calls = {"n": 0}

    def _maybe_boom(session, battle, results):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected failure before commit")
        return real_learn(session, battle, results)

    monkeypatch.setattr(fin, "_apply_self_learning_pg", _maybe_boom)
    c5_overrides = [
        _trusted_override("mod-a", "player_a", True, 3, ["skill-rollback"]),
        _trusted_override("mod-b", "player_b", False, 8, ["skill-rollback"]),
    ]
    with pytest.raises(RuntimeError, match="injected failure"):
        finalize_battle(bid, override_results=c5_overrides)

    with factory() as session:
        row = session.get(Battle, bid)
        assert row.status == "running"
        assert row.finalized_at is None
        assert repositories.scores.score_list(session, bid) == []
        assert repositories.results.results_list_by_battle(session, bid) == []
        assert session.get(SkillRecord, "skill-rollback") is None
        assert list(session.scalars(select(Memory).where(Memory.battle_id == bid))) == []
        assert (
            session.scalars(
                select(LeaderboardEntry).where(LeaderboardEntry.model_id.in_(["mod-a", "mod-b"]))
            ).first()
            is None
        )

    retry = finalize_battle(bid, override_results=c5_overrides)
    assert retry["status"] == "completed"
    assert retry.get("already_finalized") is False
    assert calls["n"] == 2

    with factory() as session:
        row = session.get(Battle, bid)
        assert row.status == "completed"
        assert row.finalized_at is not None
        assert len(repositories.scores.score_list(session, bid)) == 2
        skill = session.get(SkillRecord, "skill-rollback")
        assert skill is not None
        assert skill.uses == 2
        assert len(list(session.scalars(select(Memory).where(Memory.battle_id == bid)))) == 1


def test_c6_missing_evidence_is_retryable_then_completes(pg_bound):
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    with factory() as session:
        battle = repositories.battles.battle_create(
            session,
            user_id="user-c",
            format_id="fast-code",
            arena_size=2,
            timeout_seconds=600,
            round_visibility="isolated",
            model_ids=["model-a", "model-b"],
            status="running",
            ranked=True,
            target_id="c6-target",
            battle_config={"context_mode": "strict"},
        )
        session.commit()
        bid = battle.id

    first = finalize_battle(bid)
    assert first.get("retryable") is True
    assert first.get("authoritative") is False
    with factory() as session:
        row = session.get(Battle, bid)
        assert row.status == "running"
        assert row.finalized_at is None
        session.add(
            Round(
                battle_id=bid,
                phase="race",
                model_id="model-a",
                artifact=_trusted_payload("model-a", "player_a", True, 3, []),
            )
        )
        session.add(
            Round(
                battle_id=bid,
                phase="race",
                model_id="model-b",
                artifact=_trusted_payload("model-b", "player_b", False, 8, []),
            )
        )
        session.commit()

    second = finalize_battle(bid)
    assert second["status"] == "completed"
    with factory() as session:
        row = session.get(Battle, bid)
        assert row.status == "completed"
        assert row.finalized_at is not None


def test_c7_uncommitted_evidence_overlaps_finalize(pg_bound):
    """Scenario A: uncommitted rounds exist before finalize acquires FOR UPDATE.

    Writer already holds FOR KEY SHARE on Battle via the Round FK. Finalize's
    SELECT ... FOR UPDATE therefore waits. After the writer commits, finalize
    sees durable EXECUTOR_RESULT telemetry and still returns retryable
    INCOMPLETE_EVIDENCE. Sandbox JSON cannot complete the battle.
    """
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    mid_a = f"c7a_{uuid.uuid4().hex[:8]}"
    mid_b = f"c7b_{uuid.uuid4().hex[:8]}"
    skill = f"skill_c7a_{uuid.uuid4().hex[:8]}"
    with factory() as session:
        battle = repositories.battles.battle_create(
            session,
            user_id="user-c",
            format_id="fast-code",
            arena_size=2,
            timeout_seconds=600,
            round_visibility="isolated",
            model_ids=[mid_a, mid_b],
            status="running",
            ranked=True,
            battle_config={"context_mode": "adaptive"},
        )
        session.commit()
        bid = battle.id

    writer = factory()
    try:
        _add_race_rounds(writer, bid, mid_a, mid_b, skill)
        writer.flush()
        with factory() as reader:
            _assert_no_authoritative_side_effects(reader, bid, [mid_a, mid_b], skill)
            assert list(reader.scalars(select(Round).where(Round.battle_id == bid))) == []

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(finalize_battle, bid)
            _wait_for_blocked_backend(pg_bound)
            with factory() as reader:
                _assert_no_authoritative_side_effects(reader, bid, [mid_a, mid_b], skill)
            writer.commit()
            first = pending.result(timeout=20)
    except Exception:
        writer.rollback()
        raise
    finally:
        writer.close()

    assert first.get("retryable") is True
    assert first.get("already_finalized") is False
    assert first["status"] == "running"
    assert first.get("error") == "INCOMPLETE_EVIDENCE"

    with factory() as session:
        _assert_no_authoritative_side_effects(session, bid, [mid_a, mid_b], skill)

    replay = finalize_battle(bid)
    assert replay.get("retryable") is True
    assert replay["status"] == "running"
    with factory() as session:
        _assert_no_authoritative_side_effects(session, bid, [mid_a, mid_b], skill)


def test_c7_finalize_first_writer_blocks_then_retryable(pg_bound):
    """Scenario B: finalize starts with no committed evidence; writer overlaps.

    Finalize holds FOR UPDATE. Writer INSERT waits on the parent FK. The test
    only waits until that lock wait is visible, then lets finalize continue.
    Finalize must return retryable/nonterminal without waiting for the writer
    to commit. After the writer commits EXECUTOR_RESULT, a later host-direct
    finalize stays retryable. Sandbox JSON cannot complete the battle.
    """
    import agent_arena.finalization as fin

    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    mid_a = f"c7c_{uuid.uuid4().hex[:8]}"
    mid_b = f"c7d_{uuid.uuid4().hex[:8]}"
    skill = f"skill_c7b_{uuid.uuid4().hex[:8]}"
    with factory() as session:
        battle = repositories.battles.battle_create(
            session,
            user_id="user-c",
            format_id="fast-code",
            arena_size=2,
            timeout_seconds=600,
            round_visibility="isolated",
            model_ids=[mid_a, mid_b],
            status="running",
            ranked=True,
            battle_config={"context_mode": "adaptive"},
        )
        session.commit()
        bid = battle.id

    lock_held = threading.Event()
    writer_blocked = threading.Event()
    real_extract = fin._extract_results_from_sources

    def extract_after_writer_is_waiting(battle_id, databases, database_id, session=None):
        lock_held.set()
        assert writer_blocked.wait(timeout=15)
        return real_extract(battle_id, databases, database_id, session=session)

    def watch_for_writer_wait():
        _wait_for_blocked_backend(pg_bound)
        writer_blocked.set()

    def writer():
        assert lock_held.wait(timeout=15)
        with factory() as s2:
            _add_race_rounds(s2, bid, mid_a, mid_b, skill)
            s2.commit()

    fin._extract_results_from_sources = extract_after_writer_is_waiting
    watcher = threading.Thread(target=watch_for_writer_wait, name="c7-lock-watch", daemon=True)
    try:
        watcher.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            early_f = pool.submit(finalize_battle, bid)
            writer_f = pool.submit(writer)
            early = early_f.result(timeout=20)
            writer_f.result(timeout=20)
    finally:
        fin._extract_results_from_sources = real_extract
        watcher.join(timeout=5)

    assert early.get("retryable") is True
    assert early.get("authoritative") is False
    assert early.get("already_finalized") is False
    assert early["status"] == "running"
    assert early.get("error") == "INCOMPLETE_EVIDENCE"

    with factory() as session:
        _assert_no_authoritative_side_effects(session, bid, [mid_a, mid_b], skill)
        rounds = list(session.scalars(select(Round).where(Round.battle_id == bid)))
        assert len(rounds) == 2

    second = finalize_battle(bid)
    assert second.get("retryable") is True
    assert second["status"] == "running"
    assert second.get("error") == "INCOMPLETE_EVIDENCE"
    with factory() as session:
        _assert_no_authoritative_side_effects(session, bid, [mid_a, mid_b], skill)

    replay = finalize_battle(bid)
    assert replay.get("retryable") is True
    assert replay["status"] == "running"
    with factory() as session:
        _assert_no_authoritative_side_effects(session, bid, [mid_a, mid_b], skill)
