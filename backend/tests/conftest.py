import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Hermetic battle tests use mock_runner unless a test opts into the real runner.
os.environ.setdefault("ARENA_USE_MOCK", "1")

HAVE_APPWRITE = bool(os.environ.get("APPWRITE_API_KEY"))
requires_appwrite = pytest.mark.skipif(
    not HAVE_APPWRITE, reason="Appwrite credentials not configured"
)
modal_mark = pytest.mark.modal


def make_user_id() -> str:
    return f"test-{uuid.uuid4().hex[:16]}"


def playable_format_id() -> str:
    import json

    from appwrite.query import Query

    from agent_arena import db
    from agent_arena.seed_formats import is_playable_format

    res = db.get_databases().list_documents(
        db.get_database_id(), "formats", queries=[Query.limit(100)]
    )
    for doc in res.documents:
        try:
            cfg = json.loads(doc.data.get("config") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if is_playable_format(cfg):
            return doc.id
    raise AssertionError("no playable format seeded")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from agent_arena.main import app

    return TestClient(app)
