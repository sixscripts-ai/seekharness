"""Hermetic tests for diagnostic-zero score reconciliation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reconcile_scores.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("reconcile_scores", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def rec():
    return _load_mod()


class RecordingConn:
    def __init__(self, rowcount: int = 1):
        self.commits = 0
        self.rollbacks = 0
        self.statements: list[tuple[str, tuple | None]] = []
        self._rowcount = rowcount
        self._cursor = RecordingCursor(self)

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class RecordingCursor:
    def __init__(self, conn: RecordingConn):
        self.conn = conn
        self.rowcount = conn._rowcount

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, params))
        self.rowcount = self.conn._rowcount

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_parse_authoritative_score_event(rec):
    parsed = rec.parse_authoritative_score_payload(
        _judge_payload({"a": 86, "b": 12}, {"a": "ok"})
    )
    assert parsed is not None
    scores, justifications, judge = parsed
    assert scores == {"a": 86.0, "b": 12.0}
    assert justifications["a"] == "ok"
    assert judge == rec.ARENA_SCORE_SOURCE


def test_parse_authoritative_score_payload_rejects_malformed_or_untrusted_data(rec):
    assert rec.parse_authoritative_score_payload("not-json") is None
    assert rec.parse_authoritative_score_payload({"artifact": "plain text"}) is None
    assert rec.parse_authoritative_score_payload(
        {"authoritative": True, "source": rec.ARENA_SCORE_SOURCE, "scores": "nope"}
    ) is None
    assert rec.parse_authoritative_score_payload({"scores": {"a": "x"}}) is None


def test_is_diagnostic_wipeout(rec):
    assert rec.is_diagnostic_wipeout(0.0, "Finalized via untrusted-diagnostic")
    assert rec.is_diagnostic_wipeout(0, "diagnostic fallback")
    assert not rec.is_diagnostic_wipeout(12.0, "Finalized via untrusted-diagnostic")
    assert not rec.is_diagnostic_wipeout(0.0, "arena-score-v1 verified")


def test_validate_repair_refuses_nonzero(rec):
    err = rec.validate_repair(
        [("a", 12.0, "j", "untrusted-diagnostic"), ("b", 0.0, "j", "untrusted")],
        ["a", "b"],
        {"a": 86.0, "b": 12.0},
    )
    assert err is not None
    assert "non-wipeout" in err


def test_validate_repair_refuses_partial_map(rec):
    err = rec.validate_repair(
        [("a", 0.0, "j", "untrusted"), ("b", 0.0, "j", "untrusted")],
        ["a", "b"],
        {"a": 86.0},
    )
    assert err is not None
    assert "does not match expected participants" in err


def test_validate_repair_refuses_missing_rows(rec):
    err = rec.validate_repair([], ["a"], {"a": 1.0})
    assert err is not None
    assert "No score rows" in err


def test_validate_repair_accepts_wipeout(rec):
    err = rec.validate_repair(
        [("a", 0.0, "j", "untrusted-diagnostic"), ("b", 0.0, "j", "diagnostic")],
        ["a", "b"],
        {"a": 86.0, "b": 12.0},
    )
    assert err is None


def _patch_fetches(
    rec,
    monkeypatch,
    *,
    scores,
    participants,
    payload,
    existing=None,
):
    monkeypatch.setattr(rec, "_fetch_score_rows", lambda cur, bid: scores)
    monkeypatch.setattr(rec, "_fetch_participants", lambda cur, bid: participants)
    monkeypatch.setattr(rec, "_fetch_authoritative_score_payload", lambda cur, bid: payload)
    monkeypatch.setattr(rec, "_fetch_reconciliation", lambda cur, bid: existing)


def _judge_payload(scores: dict, justifications: dict | None = None):
    return {
        "authoritative": True,
        "source": "arena-score-v1",
        "scores": scores,
        "justifications": justifications or {},
        "judge_model": "arena-deterministic",
    }


def test_reconcile_refuses_missing_judge(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[("a", 0.0, "j", "untrusted")],
        participants=["a"],
        payload=None,
    )
    conn = RecordingConn()
    out = rec.reconcile_battle(conn, "b1")
    assert out["status"] == "REFUSED"
    assert out["reason"] == "NO_AUTHORITATIVE_SCORE_EVENT_FOUND"
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_reconcile_refuses_malformed_authoritative_score_event(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[("a", 0.0, "j", "untrusted")],
        participants=["a"],
        payload={
            "authoritative": True,
            "source": rec.ARENA_SCORE_SOURCE,
            "scores": "nope",
        },
    )
    out = rec.reconcile_battle(RecordingConn(), "b1")
    assert out["status"] == "REFUSED"
    assert out["reason"] == "MALFORMED_AUTHORITATIVE_SCORE_EVENT"


def test_reconcile_refuses_sandbox_judge_payload(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[("a", 0.0, "j", "untrusted-diagnostic")],
        participants=["a"],
        payload={
            "artifact": {
                "scores": {"a": 86.0},
                "justifications": {"a": "model-provided"},
                "judge_model": "kimi",
            }
        },
    )

    out = rec.reconcile_battle(RecordingConn(), "b1")

    assert out["status"] == "REFUSED"
    assert out["reason"] == "UNTRUSTED_SCORE_EVENT"


def test_reconcile_refuses_authoritative_nonzero(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[("a", 40.0, "j", "arena-score-v1")],
        participants=["a"],
        payload=_judge_payload({"a": 86.0}),
    )
    conn = RecordingConn()
    out = rec.reconcile_battle(conn, "b1")
    assert out["status"] == "REFUSED"
    assert "non-wipeout" in out["reason"]
    assert conn.commits == 0
    assert not any("UPDATE scores" in sql for sql, _ in conn.statements)


def test_reconcile_dry_run_does_not_write(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[("a", 0.0, "j", "untrusted-diagnostic")],
        participants=["a"],
        payload=_judge_payload({"a": 86.0}, {"a": "good"}),
    )
    conn = RecordingConn()
    out = rec.reconcile_battle(conn, "b1", dry_run=True)
    assert out["status"] == "WOULD_RECONCILE"
    assert out["handoff"] == rec.PENDING_STATUS
    assert out["new_scores"] == {"a": 86.0}
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert not any("UPDATE scores" in sql for sql, _ in conn.statements)


def test_reconcile_writes_pending_handoff(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[("a", 0.0, "j", "untrusted-diagnostic")],
        participants=["a"],
        payload=_judge_payload({"a": 86.0}, {"a": "good"}),
    )
    conn = RecordingConn()
    out = rec.reconcile_battle(conn, "b1")
    assert out["status"] == rec.PENDING_STATUS
    assert out["handoff"] == rec.PENDING_STATUS
    assert conn.commits == 1
    assert any("UPDATE scores" in sql for sql, _ in conn.statements)
    assert any("score_reconciliations" in sql for sql, _ in conn.statements)


def test_reconcile_conditional_update_failure_rolls_back(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[("a", 0.0, "j", "untrusted-diagnostic")],
        participants=["a"],
        payload=_judge_payload({"a": 86.0}),
    )
    conn = RecordingConn(rowcount=0)
    out = rec.reconcile_battle(conn, "b1")
    assert out["status"] == "REFUSED"
    assert conn.rollbacks == 1
    assert conn.commits == 0


def test_reconcile_idempotent_pending(rec, monkeypatch):
    _patch_fetches(
        rec,
        monkeypatch,
        scores=[
            ("a", 86.0, "kimi", f"{rec.REPAIR_PREFIX} good"),
        ],
        participants=["a"],
        payload=_judge_payload({"a": 86.0}),
        existing=(rec.PENDING_STATUS, {"a": 86.0}),
    )
    conn = RecordingConn()
    out = rec.reconcile_battle(conn, "b1")
    assert out["status"] == rec.PENDING_STATUS
    assert out["idempotent"] is True
    assert conn.commits == 0
    assert not any("UPDATE scores" in sql for sql, _ in conn.statements)


def test_acknowledge_elo_idempotent(rec, monkeypatch):
    monkeypatch.setattr(
        rec,
        "_fetch_reconciliation",
        lambda cur, bid: (rec.ACK_STATUS, {"a": 86.0}),
    )
    conn = RecordingConn()
    out = rec.acknowledge_elo(conn, "b1")
    assert out["status"] == "ALREADY_ACKNOWLEDGED"
    assert out["idempotent"] is True
    assert conn.commits == 0


def test_acknowledge_elo_requires_pending(rec, monkeypatch):
    monkeypatch.setattr(rec, "_fetch_reconciliation", lambda cur, bid: None)
    out = rec.acknowledge_elo(RecordingConn(), "b1")
    assert out["status"] == "REFUSED"


def test_acknowledge_elo_updates_marker(rec, monkeypatch):
    monkeypatch.setattr(
        rec,
        "_fetch_reconciliation",
        lambda cur, bid: (rec.PENDING_STATUS, {"a": 86.0}),
    )
    conn = RecordingConn()
    out = rec.acknowledge_elo(conn, "b1")
    assert out["status"] == rec.ACK_STATUS
    assert conn.commits == 1
    assert any(rec.ACK_STATUS in str(params) for _, params in conn.statements)


def test_exit_for_results_pending_is_nonzero(rec):
    assert rec._exit_for_results([{"status": rec.PENDING_STATUS}]) == rec.EXIT_ELO_PENDING
    assert rec._exit_for_results([{"status": "REFUSED"}]) == rec.EXIT_REFUSED
    assert rec._exit_for_results([{"status": rec.ACK_STATUS}]) == rec.EXIT_OK
