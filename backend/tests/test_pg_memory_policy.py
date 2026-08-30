"""Postgres adaptive memory must honor Change Set B provenance policy."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from agent_arena.memory import maybe_remember_pg, retrieve_pg
from agent_arena.persistence.models import Base
from tests.pg_support import postgres_tests_enabled, sqlalchemy_test_url

pytestmark = pytest.mark.postgres

INSIGHT = "keep ping returning pong on the login form handler"


@pytest.fixture(scope="module")
def pg_engine():
    if not postgres_tests_enabled():
        pytest.skip("ARENA_INTEGRATION_TESTS=1 and ARENA_PG_TEST_URL required")
    schema = f"memtest_{uuid.uuid4().hex[:12]}"
    eng = create_engine(
        sqlalchemy_test_url(),
        execution_options={"schema_translate_map": {None: schema}},
        poolclass=QueuePool,
        pool_size=4,
        max_overflow=4,
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
def session(pg_engine):
    factory = sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)
    sess = factory()
    yield sess
    sess.rollback()
    sess.close()


def _store(session, **overrides):
    marker = uuid.uuid4().hex
    defaults = dict(
        insight=f"{INSIGHT} {marker}",
        battle_id=f"b-mem-{marker[:10]}",
        model_id="model-private",
        target_id="tinyshop",
        role="builder",
        visibility_class="model_private",
        outcome="TEST_PASS",
        user_id="user-a",
        context_mode="adaptive",
        chosen_skills=["python-kata-fixer"],
        theory=f"keep ping returning pong {marker}",
        novelty_threshold=0.0,
    )
    defaults.update(overrides)
    return maybe_remember_pg(session, **defaults)


def test_builder_memory_hidden_from_breaker(session):
    stored = _store(session, role="builder", user_id="user-a", model_id="m1")
    assert stored is not None
    session.commit()
    hits = retrieve_pg(
        session,
        stored["insight"],
        context_mode="adaptive",
        user_id="user-a",
        model_id="m1",
        role="breaker",
        target_id="tinyshop",
        skills=["python-kata-fixer"],
    )
    assert stored["id"] not in {h["id"] for h in hits}


def test_breaker_memory_hidden_from_builder(session):
    stored = _store(session, role="breaker", user_id="user-a", model_id="m1")
    assert stored is not None
    session.commit()
    hits = retrieve_pg(
        session,
        stored["insight"],
        context_mode="adaptive",
        user_id="user-a",
        model_id="m1",
        role="builder",
        target_id="tinyshop",
        skills=["python-kata-fixer"],
    )
    assert stored["id"] not in {h["id"] for h in hits}


def test_different_user_blocked(session):
    stored = _store(session, user_id="user-a", model_id="m1")
    assert stored is not None
    session.commit()
    hits = retrieve_pg(
        session,
        stored["insight"],
        context_mode="adaptive",
        user_id="user-b",
        model_id="m1",
        role="builder",
        skills=["python-kata-fixer"],
    )
    assert stored["id"] not in {h["id"] for h in hits}


def test_different_private_model_blocked(session):
    stored = _store(session, user_id="user-a", model_id="m1", visibility_class="model_private")
    assert stored is not None
    session.commit()
    hits = retrieve_pg(
        session,
        stored["insight"],
        context_mode="adaptive",
        user_id="user-a",
        model_id="m2",
        role="builder",
        skills=["python-kata-fixer"],
    )
    assert stored["id"] not in {h["id"] for h in hits}


def test_evaluator_private_memory_blocked(session):
    stored = _store(session, visibility_class="evaluator_private")
    assert stored is not None
    session.commit()
    hits = retrieve_pg(
        session,
        stored["insight"],
        context_mode="adaptive",
        user_id="user-a",
        model_id="model-private",
        role="builder",
        skills=["python-kata-fixer"],
    )
    assert stored["id"] not in {h["id"] for h in hits}


def test_strict_mode_returns_zero(session):
    stored = _store(session)
    assert stored is not None
    session.commit()
    hits = retrieve_pg(
        session,
        stored["insight"],
        context_mode="strict",
        user_id="user-a",
        model_id="model-private",
        role="builder",
        skills=["python-kata-fixer"],
    )
    assert hits == []


def test_infrastructure_failure_produces_no_memory(session):
    battle_id = f"b-infra-{uuid.uuid4().hex[:10]}"
    stored = _store(session, outcome="PROVIDER_ERROR", battle_id=battle_id)
    assert stored is None
    session.commit()
    from agent_arena.persistence.repositories import memories as mem_repo

    assert [m for m in mem_repo.memory_list_all(session) if m.battle_id == battle_id] == []


def test_trusted_learnable_outcome_follows_b_policy(session):
    stored = _store(session, role="builder", user_id="user-a", model_id="m1")
    assert stored is not None
    assert stored["visibility_class"] == "model_private"
    assert stored["authoritative_status"] == "verified_pass"
    assert stored["role"] == "builder"
    assert stored["target_id"] == "tinyshop"
    session.commit()
    hits = retrieve_pg(
        session,
        stored["insight"],
        context_mode="adaptive",
        user_id="user-a",
        model_id="m1",
        role="builder",
        target_id="tinyshop",
        skills=["python-kata-fixer"],
    )
    assert stored["id"] in {h["id"] for h in hits}
    match = next(h for h in hits if h["id"] == stored["id"])
    assert match["role"] == "builder"
