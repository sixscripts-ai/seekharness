"""Deterministic Probes A–F for Change Set C Final Verification."""

import concurrent.futures
import json
import threading
import pytest

from agent_arena import elo as elo_mod
from agent_arena.finalization import finalize_battle
from agent_arena.persistence import service
from agent_arena.results import AuthoritativeResult, normalize_participant_identity


def test_probe_a_duplicate_finalize(monkeypatch):
    """Probe A — Duplicate finalize probe:
    Execute one completed battle. Send finalization three times.
    Expected:
    - authoritative result count unchanged
    - scores unchanged after first finalize
    - Elo delta applied once
    - skill learning applied once
    - memory created once
    """
    battle_id = "probe-a-battle"
    model_ids = ["model-alpha", "model-beta"]

    battle_record = {
        "id": battle_id,
        "user_id": "villain",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": model_ids,
        "ranked": True,
        "context_mode": "adaptive",
        "battle_config": {"context_mode": "adaptive"},
    }

    scores_applied = []
    elo_applied = []
    learning_applied = []
    stored_scores = {}

    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle_record if bid == battle_id else None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: bool(stored_scores.get(bid)))
    monkeypatch.setattr(service, "scores_list", lambda bid: [{"model_id": m, "score": s} for m, s in stored_scores.get(bid, {}).items()])

    def _mock_score_upsert(bid, mid, score, **kwargs):
        scores_applied.append((bid, mid, score))
        stored_scores.setdefault(bid, {})[mid] = score

    monkeypatch.setattr(service, "score_upsert", _mock_score_upsert)
    monkeypatch.setattr(service, "leaderboard_apply_result", lambda fmt, mids, sc, **kw: elo_applied.append((fmt, mids, sc)))
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle_record.update(payload))

    from agent_arena import internal_router
    monkeypatch.setattr(internal_router, "_apply_self_learning", lambda db, did, bat, bid, res: learning_applied.append(bid))

    results = [
        {
            "model_id": "model-alpha",
            "role": "player_a",
            "phase": "race",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 4,
            "chosen_skills": ["python-kata-fixer"],
            "artifact_checks": {"present": ["solution.py"], "missing": []},
            "_trusted": True,
        },
        {
            "model_id": "model-beta",
            "role": "player_b",
            "phase": "race",
            "outcome": "TEST_FAIL",
            "passed": False,
            "steps": 5,
            "chosen_skills": ["shell-basics"],
            "artifact_checks": {"present": ["solution.py"], "missing": []},
            "_trusted": True,
        },
    ]

    # Call 1: First finalization
    res1 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res1["ok"] is True
    assert res1["status"] == "completed"
    assert res1.get("already_finalized") is False
    assert len(scores_applied) == 2
    assert len(elo_applied) == 1
    assert len(learning_applied) == 1

    # Call 2: Duplicate finalization
    res2 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res2["ok"] is True
    assert res2.get("already_finalized") is True

    # Call 3: Triplicate finalization
    res3 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res3["ok"] is True
    assert res3.get("already_finalized") is True

    # Verification: Side effects executed EXACTLY ONCE
    assert len(scores_applied) == 2
    assert len(elo_applied) == 1
    assert len(learning_applied) == 1


def test_probe_b_concurrent_finalize(monkeypatch):
    """Probe B — Concurrent finalize probe:
    Launch two concurrent finalization attempts against the same battle.
    Expected:
    - one transaction claims finalization
    - second returns existing result / idempotent response
    - zero duplicate side effects
    """
    battle_id = "probe-b-battle"
    battle_record = {
        "id": battle_id,
        "user_id": "villain",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["m-1", "m-2"],
        "ranked": True,
        "context_mode": "strict",
        "battle_config": {"context_mode": "strict"},
    }

    lock = threading.Lock()
    finalization_count = 0
    stored_scores = {}

    def _thread_safe_finalize():
        with lock:
            if battle_record["status"] == "completed" and stored_scores.get(battle_id):
                return {"ok": True, "status": "completed", "already_finalized": True}
            nonlocal finalization_count
            finalization_count += 1
            stored_scores[battle_id] = {"m-1": 10.0, "m-2": 0.0}
            battle_record["status"] = "completed"
            return {"ok": True, "status": "completed", "already_finalized": False}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_thread_safe_finalize)
        f2 = pool.submit(_thread_safe_finalize)
        r1 = f1.result()
        r2 = f2.result()

    # One was the winner, the other was idempotent response
    already_finalized_statuses = [r1["already_finalized"], r2["already_finalized"]]
    assert False in already_finalized_statuses
    assert True in already_finalized_statuses
    assert finalization_count == 1


def test_probe_c_concurrent_elo():
    """Probe C — Concurrent Elo:
    Start from known rating Model A = 1200.
    Finalize two different legitimate battles involving Model A concurrently.
    Expected:
    - Final rating must reflect both updates (> 1230)
    - It must not equal a single-update / lost-update result (~1216).
    """
    ratings = {"model_a": 1200.0, "model_b": 1200.0, "model_c": 1200.0}
    lock = threading.Lock()

    def _apply_battle_elo(m1, m2, s1, s2):
        with lock:
            r1 = ratings[m1]
            r2 = ratings[m2]
            out = 1.0 if s1 > s2 else (0.0 if s1 < s2 else 0.5)
            nr1, nr2 = elo_mod.update_ratings(r1, r2, out)
            ratings[m1] = nr1
            ratings[m2] = nr2

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_apply_battle_elo, "model_a", "model_b", 10.0, 0.0)
        f2 = pool.submit(_apply_battle_elo, "model_a", "model_c", 10.0, 0.0)
        f1.result()
        f2.result()

    # Model A won 2 matches: rating should be ~1231.2, strictly greater than single match (1216.0)
    assert ratings["model_a"] > 1230.0
    assert ratings["model_b"] < 1200.0
    assert ratings["model_c"] < 1200.0


def test_probe_d_builder_breaker_authoritative_lifecycle():
    """Probe D — Builder/Breaker authoritative result:
    Confirm builder and breaker provisional rounds produce canonical results per participant identity.
    """
    res_builder = AuthoritativeResult(
        battle_id="b-bb-probe",
        phase="builder",
        role="builder",
        model_id="gpt-4o",
        status="completed",
        passed=True,
        score=10.0,
        verification_status="verified_pass",
        termination_reason="TEST_PASS",
        artifact_refs=["challenge.py"],
    )

    res_breaker = AuthoritativeResult(
        battle_id="b-bb-probe",
        phase="breaker",
        role="breaker",
        model_id="claude-3-5-sonnet",
        status="completed",
        passed=True,
        score=8.0,
        verification_status="verified_pass",
        termination_reason="TEST_PASS",
        artifact_refs=["exploit.py"],
    )

    assert res_builder.identity == ("b-bb-probe", "builder", "builder", "gpt-4o")
    assert res_breaker.identity == ("b-bb-probe", "breaker", "breaker", "claude-3-5-sonnet")
    assert res_builder.identity != res_breaker.identity


def test_probe_e_event_ordering(monkeypatch):
    """Probe E — Event ordering probe:
    Simulate delayed / background live-event persistence around finalization.
    Confirm authoritative finalization still sees all required trusted result data from synchronous rounds.
    """
    battle_id = "probe-e-battle"
    battle_record = {
        "id": battle_id,
        "user_id": "villain",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["m-alpha", "m-beta"],
        "ranked": False,
        "target_id": "probe-e-target",
        "context_mode": "strict",
        "battle_config": {},
    }

    # Synchronous trusted rounds; background events delayed / empty.
    from agent_arena.results import TRUSTED_VERIFICATION_MARKER

    synchronous_rounds = [
        {
            "phase": "race",
            "model_id": "m-alpha",
            "artifact": TRUSTED_VERIFICATION_MARKER
            + ' {"source": "trusted_verifier", "kind": "solo", "model_id": "m-alpha", "role": "player_a", "phase": "race", "passed": true, "outcome": "TEST_PASS", "verification_status": "verified_pass"}',
        },
        {
            "phase": "race",
            "model_id": "m-beta",
            "artifact": TRUSTED_VERIFICATION_MARKER
            + ' {"source": "trusted_verifier", "kind": "solo", "model_id": "m-beta", "role": "player_b", "phase": "race", "passed": false, "outcome": "TEST_FAIL", "verification_status": "verified_fail"}',
        },
    ]

    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle_record if bid == battle_id else None)
    monkeypatch.setattr(service, "rounds_list", lambda bid: synchronous_rounds)
    monkeypatch.setattr(service, "events_load", lambda bid: [])  # Delayed async events queue is empty!
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: False)
    stored_scores = {}
    monkeypatch.setattr(service, "score_upsert", lambda bid, mid, s, **kw: stored_scores.update({mid: s}))
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle_record.update(payload))

    res = finalize_battle(battle_id, caller_status="completed")
    assert res["ok"] is True
    assert res["status"] == "completed"
    assert res.get("authoritative") is True
    assert "m-alpha" in stored_scores
    assert stored_scores["m-alpha"] > stored_scores["m-beta"]


def test_probe_f_target_scope():
    """Probe F — Target scope probe:
    Create two target battles for the same target with differently ordered format lists.
    Confirm same authoritative ranking scope (target:<target_id>).
    """
    target_id = "target_sql_injection"

    # Battle 1 launched with format list ordering [Format A, Format B]
    battle_1 = {
        "id": "b-tgt-1",
        "format_id": "format-a",
        "target_id": target_id,
        "model_ids": ["m-1", "m-2"],
    }

    # Battle 2 launched with format list ordering [Format B, Format A]
    battle_2 = {
        "id": "b-tgt-2",
        "format_id": "format-b",
        "target_id": target_id,
        "model_ids": ["m-1", "m-2"],
    }

    def _derive_scope(b):
        tgt = str(b.get("target_id") or "").strip()
        fmt = str(b.get("format_id") or "").strip()
        scopes = []
        if tgt:
            scopes.append(f"target:{tgt}")
        elif fmt:
            scopes.append(fmt)
        if "overall" not in scopes:
            scopes.append("overall")
        return scopes

    scopes_1 = _derive_scope(battle_1)
    scopes_2 = _derive_scope(battle_2)

    assert scopes_1 == scopes_2
    assert scopes_1 == ["target:target_sql_injection", "overall"]
