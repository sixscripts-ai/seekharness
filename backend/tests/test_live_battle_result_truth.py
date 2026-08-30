"""P0 live-battle result truth: no verified winner without trusted verification."""

from __future__ import annotations

import json
from pathlib import Path

from agent_arena.battle_public import (
    public_battle_payload,
    public_winner,
    scrub_evaluator_private,
    verified_solution_from_results,
)
from agent_arena.finalization import _merge_trusted_authority, derive_trusted_scores, finalize_battle
from agent_arena.persistence import service
from agent_arena.results import TRUSTED_VERIFICATION_MARKER
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
from agent_arena.target_library import (
    compile_target_to_battle_config,
    fighter_visible_battle_config,
)
from tests.eval_fixtures import point_evaluators, write_private_evaluator


def _round(marker: str, payload: dict, phase: str = "race") -> dict:
    return {
        "phase": phase,
        "model_id": payload.get("model_id") or "",
        "artifact": marker + " " + json.dumps(payload),
    }


def _target_battle(battle_id: str, *, ranked: bool = False) -> dict:
    return {
        "id": battle_id,
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 1,
        "model_ids": ["host:modal-kimi"],
        "ranked": ranked,
        "target_id": "tinyshop",
        "target_version": "1.0.0",
        "battle_config": {
            "target_id": "tinyshop",
            "hidden_hash": "should-not-leak",
            "verification": {
                "visible_command": "pytest -q tests/visible",
                "hidden_command": "PYTHONPATH=. pytest -q tests/hidden",
            },
        },
    }


def test_turn_budget_unverified_cannot_return_verified_winner():
    results = [
        {
            "model_id": "host:modal-kimi",
            "phase": "race",
            "role": "fighter",
            "passed": False,
            "score": 0.0,
            "verification_status": "verified_fail",
            "termination_reason": "TURN_BUDGET_EXCEEDED",
            "executor_outcome": "TURN_BUDGET_EXCEEDED",
        }
    ]
    assert verified_solution_from_results(results) is False
    assert public_winner(verified_solution=False, results=results) is None
    payload = public_battle_payload(
        _target_battle("b-ui"),
        results=results,
        score_rows=[{"model_id": "host:modal-kimi", "score": 0.0}],
    )
    assert payload["verified_solution"] is False
    assert payload["winner"] is None
    assert payload["scores"]["host:modal-kimi"] == 0.0
    assert payload["termination_reason"] == "TURN_BUDGET_EXCEEDED"
    assert payload["verification_status"] == "verified_fail"
    assert "hidden_command" not in json.dumps(payload)
    assert "hidden_hash" not in json.dumps(payload)


def test_owner_payload_uses_authoritative_score_not_legacy_58():
    payload = public_battle_payload(
        _target_battle("b-58"),
        results=[
            {
                "model_id": "host:modal-kimi",
                "passed": False,
                "score": 0.0,
                "verification_status": "verified_fail",
                "termination_reason": "TURN_BUDGET_EXCEEDED",
            }
        ],
        score_rows=[{"model_id": "host:modal-kimi", "score": 0.0}],
    )
    assert payload["scores"] == {"host:modal-kimi": 0.0}
    assert 58 not in payload["scores"].values()
    assert payload["winner"] is None


def test_owner_and_browser_payloads_strip_hidden_command_and_hash(
    tmp_path: Path, monkeypatch
):
    tid = "truth-secrecy"
    target = tmp_path / "library" / tid
    (target / "starter").mkdir(parents=True)
    (target / "tests" / "visible").mkdir(parents=True)
    (target / "target.yaml").write_text(
        f"""
schema_version: 1
id: {tid}
name: Truth Secrecy
category: security
difficulty: novice
format: solo
runtime: python311
description: secrecy
objectives: [pong]
workspace:
  starter_dir: starter
  visible_tests_dir: tests/visible
  hidden_tests_dir: tests/hidden
  reference_dir: reference
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: python3 -m pytest tests/visible -q
  hidden_command: python3 -m pytest tests/hidden -q
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 8
  exec_timeout_seconds: 20
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )
    (target / "starter" / "app.py").write_text("def ping():\n    return 'pong'\n")
    (target / "tests" / "visible" / "test_visible.py").write_text(
        "from app import ping\n\ndef test_ping():\n    assert ping() == 'pong'\n"
    )
    write_private_evaluator(
        tmp_path / "evaluators",
        tid,
        hidden={
            "test_hidden.py": (
                "from app import ping\n\ndef test_hidden():\n    assert ping() == 'pong'\n"
            )
        },
    )
    point_evaluators(monkeypatch, tmp_path / "evaluators")
    from agent_arena.target_library import load_target_bundle

    bundle = load_target_bundle(target)
    trusted = compile_target_to_battle_config(bundle, arena_size=1)
    assert trusted["hidden_hash"]
    assert trusted["verification"]["hidden_command"]
    public = public_battle_payload(
        {"id": "b1", "battle_config": trusted, "target_id": tid},
        results=[],
        score_rows=[],
    )
    blob = json.dumps(public)
    assert "hidden_command" not in blob
    assert "hidden_hash" not in blob
    assert "tests/hidden" not in blob
    assert "hidden_output" not in blob
    fighter = fighter_visible_battle_config(trusted)
    assert "hidden_command" not in (fighter.get("verification") or {})
    assert trusted["hidden_hash"]
    assert trusted["verification"]["hidden_command"]


def test_scrub_evaluator_private_drops_nested_hidden_fields():
    cleaned = scrub_evaluator_private(
        {
            "type": "artifact",
            "hidden_command": "pytest tests/hidden",
            "data": {"hidden_hash": "abc", "visible_command": "pytest tests/visible"},
        }
    )
    assert "hidden_command" not in json.dumps(cleaned)
    assert "hidden_hash" not in json.dumps(cleaned)
    assert cleaned["data"]["visible_command"] == "pytest tests/visible"


def test_finalize_turn_budget_verified_fail_is_unverified_zero(
    monkeypatch,
):
    battle_id = "b-budget-fail"
    battle = _target_battle(battle_id, ranked=False)
    stored_scores: dict = {}
    elo_calls: list = []
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: False)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: stored_scores.__setitem__(mid, score),
    )
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle.update(payload))
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: elo_calls.append(a),
    )
    monkeypatch.setattr(
        service,
        "rounds_list",
        lambda bid: [
            _round(
                TRUSTED_VERIFICATION_MARKER,
                {
                    "source": "trusted_verifier",
                    "target_id": "tinyshop",
                    "kind": "solo",
                    "phase": "race",
                    "role": "fighter",
                    "model_id": "host:modal-kimi",
                    "passed": False,
                    "attempted": True,
                    "verification_status": "verified_fail",
                    "outcome": "TEST_FAIL",
                    "executor_outcome": "TURN_BUDGET_EXCEEDED",
                    "terminal_reason": "turn_budget_exhausted",
                },
            ),
            _round(
                "EXECUTOR_RESULT:",
                {
                    "model_id": "host:modal-kimi",
                    "role": "fighter",
                    "phase": "race",
                    "outcome": "TURN_BUDGET_EXCEEDED",
                    "passed": False,
                    "terminal_reason": "turn_budget_exhausted",
                    "steps": 15,
                },
            ),
        ],
    )
    result = finalize_battle(battle_id, caller_scores={"host:modal-kimi": 58.0})
    assert result.get("retryable") is not True
    assert result["status"] == "completed"
    assert stored_scores["host:modal-kimi"] == 0.0
    assert 58.0 not in stored_scores.values()
    assert elo_calls == []
    assert battle["ranked"] is False

    scores, source, error, summary, decision = derive_trusted_scores(
        battle_id=battle_id,
        results=_merge_trusted_authority(
            [
                {
                    "model_id": "host:modal-kimi",
                    "role": "fighter",
                    "phase": "race",
                    "outcome": "TURN_BUDGET_EXCEEDED",
                    "passed": False,
                }
            ],
            [
                {
                    "kind": "solo",
                    "phase": "race",
                    "role": "fighter",
                    "model_id": "host:modal-kimi",
                    "passed": False,
                    "verification_status": "verified_fail",
                    "outcome": "TEST_FAIL",
                    "executor_outcome": "TURN_BUDGET_EXCEEDED",
                }
            ],
            require_trusted=True,
        ),
        fmt_cfg={},
        battle_model_ids=["host:modal-kimi"],
        untrusted_hint_scores={"host:modal-kimi": 58.0},
    )
    assert error is None
    assert source == "arena-score-v1"
    assert scores == {"host:modal-kimi": 0.0}
    assert decision["verified_solution"] is False
    assert decision.get("winner") is None or decision.get("verified_solution") is False


def test_finalize_not_attempted_stays_explicitly_unverified(monkeypatch):
    battle_id = "b-not-attempted"
    battle = _target_battle(battle_id, ranked=False)
    stored_scores: dict = {}
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: False)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: stored_scores.__setitem__(mid, score),
    )
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle.update(payload))
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("unranked must not elo")),
    )
    monkeypatch.setattr(
        service,
        "rounds_list",
        lambda bid: [
            _round(
                TRUSTED_VERIFICATION_MARKER,
                {
                    "source": "trusted_verifier",
                    "target_id": "tinyshop",
                    "kind": "solo",
                    "phase": "race",
                    "role": "fighter",
                    "model_id": "host:modal-kimi",
                    "passed": False,
                    "attempted": False,
                    "verification_status": "not_attempted",
                    "outcome": "VERIFICATION_NOT_ATTEMPTED",
                    "executor_outcome": "TURN_BUDGET_EXCEEDED",
                },
            ),
            _round(
                "EXECUTOR_RESULT:",
                {
                    "model_id": "host:modal-kimi",
                    "role": "fighter",
                    "phase": "race",
                    "outcome": "TURN_BUDGET_EXCEEDED",
                    "passed": False,
                    "steps": 6,
                },
            ),
        ],
    )
    result = finalize_battle(battle_id)
    assert result["status"] == "completed"
    assert stored_scores["host:modal-kimi"] == 0.0
    payload = public_battle_payload(
        battle,
        results=[
            {
                "model_id": "host:modal-kimi",
                "passed": False,
                "score": 0.0,
                "verification_status": "not_attempted",
                "termination_reason": "TURN_BUDGET_EXCEEDED",
            }
        ],
        score_rows=[{"model_id": "host:modal-kimi", "score": 0.0}],
    )
    assert payload["verification_status"] == "not_attempted"
    assert payload["verified_solution"] is False
    assert payload["winner"] is None


def test_finalize_role_still_verifies_after_turn_budget(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    monkeypatch.delenv("ARENA_IN_SANDBOX", raising=False)
    called: list[dict] = []

    def _fake_verify(self, **kwargs):
        called.append(kwargs)
        return {
            "target_id": "tinyshop",
            "passed": False,
            "attempted": True,
            "verification_status": "verified_fail",
            "visible_passed": False,
        }, None

    monkeypatch.setattr(AdvancedExecutor, "_verify_target_trusted", _fake_verify)
    work = tmp_path / "work"
    work.mkdir()
    (work / "shop.py").write_text("print('hi')\n")
    (work / "tests").mkdir()
    (work / "tests" / "test_target.py").write_text("def test_ok():\n    assert True\n")

    class _Sess:
        steps = 15
        skill_reads = set()

        def test(self, *_a, **_k):
            return "TEST_FAIL rc=1"

        def ls(self, **_k):
            return "shop.py"

    class _Client:
        def round(self, *a, **k):
            return None

        def result(self, *a, **k):
            return None

    exe = AdvancedExecutor()
    exe.emit_result = lambda *a, **k: "EXECUTOR_RESULT: {}"
    result = exe._finalize_role(
        client=_Client(),
        battle_id="b-verify-after-budget",
        work=work,
        sess=_Sess(),
        model_id="host:modal-kimi",
        role="fighter",
        chosen_skills=[],
        preview_url="",
        format_config={"target_id": "tinyshop", "spec_hash": "abc"},
        history=[],
        results=[],
        seq={"n": 0},
        outcome_override="TURN_BUDGET_EXCEEDED",
        terminal_reason="turn_budget_exhausted",
        turns=6,
    )
    assert called, "trusted verification must run after turn-budget exhaustion"
    assert called[0]["files"]["shop.py"]
    assert called[0]["executor_outcome"] == "TURN_BUDGET_EXCEEDED"
    assert result["outcome"] == "TEST_FAIL"
    assert result["passed"] is False
    assert result["verification_status"] == "verified_fail"
    assert result["terminal_reason"] == "turn_budget_exhausted"


def test_ranked_false_turn_budget_does_not_change_elo(monkeypatch):
    battle_id = "b-unranked-elo"
    battle = _target_battle(battle_id, ranked=False)
    elo_calls: list = []
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: False)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(service, "score_upsert", lambda *a, **k: None)
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle.update(payload))
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: elo_calls.append(a),
    )
    monkeypatch.setattr(
        service,
        "rounds_list",
        lambda bid: [
            _round(
                TRUSTED_VERIFICATION_MARKER,
                {
                    "source": "trusted_verifier",
                    "kind": "solo",
                    "phase": "race",
                    "role": "fighter",
                    "model_id": "host:modal-kimi",
                    "passed": False,
                    "verification_status": "verified_fail",
                    "outcome": "TEST_FAIL",
                },
            ),
            _round(
                "EXECUTOR_RESULT:",
                {
                    "model_id": "host:modal-kimi",
                    "role": "fighter",
                    "phase": "race",
                    "outcome": "TURN_BUDGET_EXCEEDED",
                    "passed": False,
                },
            ),
        ],
    )
    result = finalize_battle(battle_id)
    assert result["status"] == "completed"
    assert elo_calls == []
    assert battle["ranked"] is False
