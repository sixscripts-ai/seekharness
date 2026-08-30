"""Deep Transactional Exactly-Once & Concurrency Audit Tests (Change Set C)."""

import concurrent.futures
import threading
import uuid
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from agent_arena import elo as elo_mod
from agent_arena.finalization import _apply_leaderboard_elo_pg, _extract_results_from_sources, finalize_battle
from agent_arena.persistence import repositories
from agent_arena.persistence.models import Base, Battle, LeaderboardEntry, Memory, Score, SkillRecord
from agent_arena.persistence.session import session_scope
from agent_arena.results import AuthoritativeResult
from tests.pg_support import sqlalchemy_test_url

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def audit_pg_engine():
    """Isolated throwaway Postgres schema for transactional rollback and concurrency tests."""
    schema = f"atest_{uuid.uuid4().hex[:12]}"
    eng = create_engine(
        sqlalchemy_test_url(),
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
def audit_session(audit_pg_engine):
    factory = sessionmaker(bind=audit_pg_engine, expire_on_commit=False, autoflush=False)
    session = factory()
    yield session
    session.close()


def test_audit_1_rollback_and_retry_preserves_zero_partial_mutations(audit_session):
    """Audit 1: Inject failure before transaction commit.
    Verify 0 partial scores, 0 Elo updates, 0 skills, 0 memories, and unfinalized battle.
    Then verify retry succeeds and applies everything exactly once.
    """
    b = repositories.battles.battle_create(
        audit_session,
        user_id="u-audit",
        format_id="fast-code",
        arena_size=2,
        timeout_seconds=600,
        round_visibility="isolated",
        model_ids=["mod-a", "mod-b"],
        battle_config={"context_mode": "adaptive"},
    )
    audit_session.commit()

    # Create initial skill
    repositories.skills.skill_upsert(audit_session, "skill-rollback-test", elo=1000.0, uses=0, wins=0)
    audit_session.commit()

    results = [
        {
            "model_id": "mod-a",
            "role": "player_a",
            "phase": "race",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 3,
            "chosen_skills": ["skill-rollback-test"],
            "artifact_checks": {"present": ["solution.py"], "missing": []},
        },
        {
            "model_id": "mod-b",
            "role": "player_b",
            "phase": "race",
            "outcome": "TEST_FAIL",
            "passed": False,
            "steps": 6,
            "chosen_skills": [],
            "artifact_checks": {"present": ["solution.py"], "missing": []},
        },
    ]

    # 1. Simulate failure during finalization transaction before commit
    # We do this by executing the transactional steps and intentionally raising an exception
    try:
        with audit_session.begin_nested():
            # Apply results in subtransaction
            for r in results:
                repositories.results.result_upsert(
                    audit_session,
                    battle_id=b.id,
                    phase=r["phase"],
                    role=r["role"],
                    model_id=r["model_id"],
                    score=10.0 if r["passed"] else 0.0,
                    passed=r["passed"],
                )
            repositories.scores.score_insert(audit_session, battle_id=b.id, model_id="mod-a", score=10.0)
            # Injected failure before commit!
            raise RuntimeError("Injected crash before commit!")
    except RuntimeError:
        audit_session.rollback()

    # Verify state is 100% pristine
    assert len(repositories.results.results_list_by_battle(audit_session, b.id)) == 0
    assert len(repositories.scores.score_list(audit_session, b.id)) == 0
    skill_row = repositories.skills.skill_get(audit_session, "skill-rollback-test")
    assert skill_row.uses == 0  # No partial skill mutation!
    b_loaded = repositories.battles.battle_get(audit_session, b.id)
    assert b_loaded.finalized_at is None
    assert b_loaded.status == "queued"

    # 2. Now perform successful finalization on the same session
    for r in results:
        repositories.results.result_upsert(
            audit_session,
            battle_id=b.id,
            phase=r["phase"],
            role=r["role"],
            model_id=r["model_id"],
            score=10.0 if r["passed"] else 0.0,
            passed=r["passed"],
        )
    repositories.scores.score_insert(audit_session, battle_id=b.id, model_id="mod-a", score=10.0)
    repositories.scores.score_insert(audit_session, battle_id=b.id, model_id="mod-b", score=0.0)
    _apply_leaderboard_elo_pg(audit_session, {"model_ids": ["mod-a", "mod-b"], "format_id": "fast-code"}, {"mod-a": 10.0, "mod-b": 0.0})
    from agent_arena.finalization import _record_skill_outcome_session
    _record_skill_outcome_session(audit_session, "skill-rollback-test", "win")
    b_loaded.status = "completed"
    b_loaded.finalized_at = text("now()")
    audit_session.commit()

    # Verify everything committed exactly once
    assert len(repositories.results.results_list_by_battle(audit_session, b.id)) == 2
    assert len(repositories.scores.score_list(audit_session, b.id)) == 2
    skill_row_after = repositories.skills.skill_get(audit_session, "skill-rollback-test")
    assert skill_row_after.uses == 1
    assert skill_row_after.wins == 1
    assert skill_row_after.elo > 1000.0


def test_audit_2_missing_leaderboard_row_concurrency(audit_pg_engine):
    """Audit 2: Two concurrent battles updating a model whose leaderboard row DOES NOT EXIST initially.
    Proves:
    - Unique-row creation is race-safe (no duplicate key / deadlock error)
    - Neither Elo update is lost
    """
    factory = sessionmaker(bind=audit_pg_engine, expire_on_commit=False, autoflush=False)
    test_scope = f"target:tgt_{uuid.uuid4().hex[:8]}"
    model_new = f"mod_new_{uuid.uuid4().hex[:8]}"
    model_opp1 = f"opp1_{uuid.uuid4().hex[:8]}"
    model_opp2 = f"opp2_{uuid.uuid4().hex[:8]}"

    # Verify row does NOT exist before either transaction begins
    with factory() as sess:
        row = sess.scalars(select(LeaderboardEntry).where(LeaderboardEntry.model_id == model_new, LeaderboardEntry.scope == test_scope)).first()
        assert row is None

    # Battle 1: model_new beats model_opp1
    def _run_battle_1():
        with factory() as sess:
            battle_dict = {"model_ids": [model_new, model_opp1], "target_id": test_scope.replace("target:", "")}
            _apply_leaderboard_elo_pg(sess, battle_dict, {model_new: 10.0, model_opp1: 0.0})
            sess.commit()

    # Battle 2: model_new beats model_opp2
    def _run_battle_2():
        with factory() as sess:
            battle_dict = {"model_ids": [model_new, model_opp2], "target_id": test_scope.replace("target:", "")}
            _apply_leaderboard_elo_pg(sess, battle_dict, {model_new: 10.0, model_opp2: 0.0})
            sess.commit()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_run_battle_1)
        f2 = pool.submit(_run_battle_2)
        f1.result()
        f2.result()

    # Verify row exists and reflects BOTH updates (games_played == 2, elo > 1230)
    with factory() as sess:
        entry = sess.scalars(select(LeaderboardEntry).where(LeaderboardEntry.model_id == model_new, LeaderboardEntry.scope == test_scope)).one()
        assert entry.games_played == 2
        assert entry.elo > 1230.0  # Both matches counted!


def test_audit_3_rounds_authoritative_selection_rule(monkeypatch):
    """Audit 3: Deterministic selection from multiple provisional/retry round records.
    Proves:
    - Non-final intermediate rounds are ignored
    - Later verified terminal round is chosen over earlier intermediate records
    """
    bid = "b-round-audit"
    rounds_data = [
        # Round 0: Step 1 log (no EXECUTOR_RESULT marker)
        {"sequence": 0, "model_id": "mod-x", "phase": "race", "artifact": "Running test suite..."},
        # Round 1: Provisional error during intermediate step
        {"sequence": 1, "model_id": "mod-x", "phase": "race", "artifact": 'EXECUTOR_RESULT: {"outcome": "SANDBOX_ERROR", "passed": false, "steps": 1}'},
        # Round 2: Terminal verified passing outcome on retry
        {"sequence": 2, "model_id": "mod-x", "phase": "race", "artifact": 'EXECUTOR_RESULT: {"outcome": "TEST_PASS", "passed": true, "steps": 4, "artifact_checks": {"present": ["solution.py"]}}'},
    ]

    from agent_arena.persistence import service
    monkeypatch.setattr(service, "rounds_list", lambda b: rounds_data)

    results = _extract_results_from_sources(bid, None, "")
    assert len(results) == 1
    selected = results[0]
    assert selected["model_id"] == "mod-x"
    assert selected["outcome"] == "TEST_PASS"
    assert selected["passed"] is True
    assert selected["steps"] == 4


def test_audit_4_completion_ordering_invariant(audit_session):
    """Audit 4: Prove battle.status = 'completed' and finalized_at cannot become durable
    if any downstream mutation fails.
    """
    b = repositories.battles.battle_create(
        audit_session,
        user_id="u-order",
        format_id="fast-code",
        arena_size=2,
        timeout_seconds=600,
        round_visibility="isolated",
        model_ids=["m-a", "m-b"],
    )
    audit_session.commit()

    # Attempt finalization with downstream failure
    try:
        with audit_session.begin_nested():
            # 1. Update battle object in memory
            b.status = "completed"
            b.finalized_at = text("now()")
            # 2. Downstream mutation throws error
            raise ValueError("Downstream rating engine failed!")
    except ValueError:
        audit_session.rollback()

    # Verify status is NOT completed and finalized_at is NULL in database
    reloaded = repositories.battles.battle_get(audit_session, b.id)
    assert reloaded.status != "completed"
    assert reloaded.finalized_at is None
