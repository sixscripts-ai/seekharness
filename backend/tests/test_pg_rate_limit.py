"""Opt-in PostgreSQL contention tests for atomic internal rate-limit admission.

Never uses production Neon / DATABASE_URL. Requires:

    ARENA_INTEGRATION_TESTS=1
    ARENA_PG_TEST_URL=postgresql://...
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from agent_arena.persistence import repositories, service
from agent_arena.persistence.models import Base, BattleRateLimit
from agent_arena.persistence.session import SessionLocal
from tests.pg_support import postgres_tests_enabled, sqlalchemy_test_url

pytestmark = pytest.mark.postgres

_LIMIT = 8


@pytest.fixture(scope="module")
def pg_engine():
    if not postgres_tests_enabled():
        pytest.skip("ARENA_INTEGRATION_TESTS=1 and ARENA_PG_TEST_URL required")
    schema = f"rltest_{uuid.uuid4().hex[:12]}"
    eng = create_engine(
        sqlalchemy_test_url(),
        execution_options={"schema_translate_map": {None: schema}},
        poolclass=QueuePool,
        pool_size=16,
        max_overflow=16,
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
    monkeypatch.setattr("agent_arena.persistence.service.using_postgres", lambda: True)
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    from agent_arena.config import settings

    settings.cache_clear()
    yield pg_engine
    SessionLocal._maker = None


def test_concurrent_admissions_never_exceed_limit(pg_bound):
    battle_id = f"rl_{uuid.uuid4().hex[:12]}"
    now = time.time()
    start = threading.Barrier(24)
    results: list[bool] = []
    lock = threading.Lock()

    def _one():
        start.wait(timeout=10)
        admitted = service.rate_limit_admit(
            battle_id, now=now, limit=_LIMIT, window_seconds=60.0
        )
        with lock:
            results.append(admitted)
        return admitted

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futs = [pool.submit(_one) for _ in range(24)]
        for fut in futs:
            fut.result(timeout=20)

    assert results.count(True) == _LIMIT
    assert results.count(False) == 24 - _LIMIT

    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    with factory() as session:
        row = session.get(BattleRateLimit, battle_id)
        assert row is not None
        assert len(row.window_ts) == _LIMIT


def test_rejected_call_does_not_append_timestamp(pg_bound):
    battle_id = f"rl_full_{uuid.uuid4().hex[:12]}"
    now = 1_000_000.0
    for _ in range(_LIMIT):
        assert service.rate_limit_admit(
            battle_id, now=now, limit=_LIMIT, window_seconds=60.0
        )
    assert (
        service.rate_limit_admit(
            battle_id, now=now + 1.0, limit=_LIMIT, window_seconds=60.0
        )
        is False
    )
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    with factory() as session:
        window = repositories.rate_limits.rate_limit_window(session, battle_id)
        assert window == [now] * _LIMIT


def test_admit_rollback_leaves_no_phantom_admission(pg_bound):
    battle_id = f"rl_rb_{uuid.uuid4().hex[:12]}"
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        admitted = repositories.rate_limits.rate_limit_admit(
            session, battle_id, now=50.0, limit=_LIMIT, window_seconds=60.0
        )
        assert admitted is True
        raise RuntimeError("injected failure before commit")
    except RuntimeError:
        session.rollback()
    finally:
        session.close()

    with factory() as session:
        row = session.get(BattleRateLimit, battle_id)
        assert row is None
        assert session.scalars(select(BattleRateLimit)).first() is None


def test_expired_window_admits_again(pg_bound):
    battle_id = f"rl_exp_{uuid.uuid4().hex[:12]}"
    for i in range(_LIMIT):
        assert service.rate_limit_admit(
            battle_id, now=100.0 + i, limit=_LIMIT, window_seconds=60.0
        )
    assert (
        service.rate_limit_admit(
            battle_id, now=200.0, limit=_LIMIT, window_seconds=60.0
        )
        is True
    )
    factory = sessionmaker(bind=pg_bound, expire_on_commit=False, autoflush=False)
    with factory() as session:
        window = repositories.rate_limits.rate_limit_window(session, battle_id)
        assert window == [200.0]
