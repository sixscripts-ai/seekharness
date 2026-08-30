"""Pytest fixtures and the hermetic-by-default test boundary.

This file MUST run before any test module imports agent_arena.config. Do not
load repository .env here unless ARENA_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _integration_enabled() -> bool:
    return os.environ.get("ARENA_INTEGRATION_TESTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


if _integration_enabled():
    load_dotenv(_REPO_ROOT / ".env", override=False)
    for _candidate in (
        _REPO_ROOT / ".env.local",
        _REPO_ROOT.parent / ".env.local",
    ):
        if _candidate.is_file():
            load_dotenv(_candidate, override=False)
    os.environ.pop("ARENA_HERMETIC", None)
else:
    from agent_arena.hermetic import apply_hermetic_environment

    apply_hermetic_environment()

# Hermetic battle tests use mock_runner unless a test opts into the real runner.
os.environ.setdefault("ARENA_USE_MOCK", "1")

HAVE_APPWRITE = bool(
    os.environ.get("APPWRITE_API_KEY")
    and os.environ.get("APPWRITE_API_KEY") not in ("hermetic-blocked", "")
    and _integration_enabled()
)
requires_appwrite = pytest.mark.integration
modal_mark = pytest.mark.modal


def make_user_id() -> str:
    return f"test-{uuid.uuid4().hex[:16]}"


def playable_format_id() -> str:
    import json

    from appwrite.query import Query

    from agent_arena import db
    from agent_arena.seed_formats import is_direct_launchable_format

    res = db.get_databases().list_documents(
        db.get_database_id(), "formats", queries=[Query.limit(100)]
    )
    for doc in res.documents:
        try:
            cfg = json.loads(doc.data.get("config") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if is_direct_launchable_format(cfg):
            return doc.id
    raise AssertionError("no playable format seeded")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: external Appwrite / paid provider / live HTTP (needs ARENA_INTEGRATION_TESTS=1)",
    )
    config.addinivalue_line(
        "markers",
        "postgres: real PostgreSQL (requires ARENA_INTEGRATION_TESTS=1 and ARENA_PG_TEST_URL)",
    )
    config.addinivalue_line(
        "markers",
        "provider_eval: paid/provider LLM evals (deepeval); not collected in hermetic mode",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _integration_enabled():
        return
    skip_pg = pytest.mark.skip(
        reason="External Postgres access requires ARENA_INTEGRATION_TESTS=1"
    )
    skip_int = pytest.mark.skip(
        reason="External integration requires ARENA_INTEGRATION_TESTS=1"
    )
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip_pg)
        elif "integration" in item.keywords or "provider_eval" in item.keywords:
            item.add_marker(skip_int)


collect_ignore: list[str] = []
if not _integration_enabled():
    collect_ignore = ["evals"]


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from agent_arena.main import app

    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def synthetic_evaluator_root(tmp_path_factory: pytest.TempPathFactory):
    """Point the whole hermetic session at synthetic private evaluator packages.

    A clean public clone has no `targets/evaluators/<id>` tree, and tests must
    never read the real one. Individual tests still override
    `ARENA_EVALUATOR_DIR` via monkeypatch to exercise fail-closed paths.
    """
    if _integration_enabled():
        yield None
        return

    from tests.eval_fixtures import write_synthetic_evaluator_overlays

    eval_root = tmp_path_factory.mktemp("arena-synthetic-evaluators")
    write_synthetic_evaluator_overlays(_REPO_ROOT / "targets" / "library", eval_root)
    previous = os.environ.get("ARENA_EVALUATOR_DIR")
    os.environ["ARENA_EVALUATOR_DIR"] = str(eval_root)
    try:
        yield eval_root
    finally:
        if previous is None:
            os.environ.pop("ARENA_EVALUATOR_DIR", None)
        else:
            os.environ["ARENA_EVALUATOR_DIR"] = previous


@pytest.fixture(autouse=True)
def _isolate_target_library_cache():
    """Keep a temp library root from leaking into later tests via the registry."""
    yield
    try:
        from tests.eval_fixtures import reset_target_library_cache

        reset_target_library_cache()
    except Exception:
        pass
