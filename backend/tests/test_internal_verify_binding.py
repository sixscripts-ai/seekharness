""" /internal/verify binds target/kind from trusted battle state, not the sandbox."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_arena.battle_token import issue_battle_token
from agent_arena.internal_router import VerifyBody, _derive_verify_binding
from agent_arena.target_library import load_target_bundle
from fastapi import HTTPException


def _battle(**overrides) -> dict:
    data = {
        "id": "b-verify",
        "status": "running",
        "target_id": "synth-iso",
        "format_id": "fast-code",
        "model_ids": ["model-a"],
        "target_manifest_hash": "",
        "battle_config": {"format": "solo", "target_id": "synth-iso", "roles": ["fighter"]},
    }
    data.update(overrides)
    return data


def test_derive_rejects_unbound_target():
    body = VerifyBody(battle_id="b1", target_id="tinyshop")
    with pytest.raises(HTTPException) as exc:
        _derive_verify_binding({"status": "running", "model_ids": ["m"]}, {}, body)
    assert exc.value.status_code == 400
    assert "no bound target" in str(exc.value.detail)


def test_derive_rejects_cross_target():
    body = VerifyBody(battle_id="b1", target_id="other-target")
    with pytest.raises(HTTPException) as exc:
        _derive_verify_binding(_battle(), {"format": "solo", "target_id": "synth-iso"}, body)
    assert exc.value.status_code == 400


def test_derive_rejects_path_target_id():
    body = VerifyBody(battle_id="b1", target_id="../evaluators/secret")
    with pytest.raises(HTTPException) as exc:
        _derive_verify_binding(_battle(), {"format": "solo", "target_id": "synth-iso"}, body)
    assert exc.value.status_code == 400


def test_derive_rejects_wrong_kind():
    body = VerifyBody(battle_id="b1", target_id="synth-iso", kind="solo")
    fmt = {"format": "builder_breaker", "target_id": "synth-iso", "roles": ["builder", "breaker"]}
    with pytest.raises(HTTPException) as exc:
        _derive_verify_binding(_battle(target_id="synth-iso"), fmt, body)
    assert "kind" in str(exc.value.detail)


def test_derive_rejects_unknown_participant():
    body = VerifyBody(battle_id="b1", target_id="synth-iso", model_id="not-in-battle")
    with pytest.raises(HTTPException) as exc:
        _derive_verify_binding(_battle(), {"format": "solo", "roles": ["fighter"]}, body)
    assert exc.value.status_code == 400


def test_derive_rejects_wrong_role_and_phase():
    fmt = {
        "format": "solo",
        "target_id": "synth-iso",
        "roles": ["fighter"],
        "battle_plan": {"phases": [{"phase_id": "solve", "actor": "fighter"}]},
    }
    with pytest.raises(HTTPException):
        _derive_verify_binding(_battle(), fmt, VerifyBody(battle_id="b1", target_id="synth-iso", role="breaker"))
    with pytest.raises(HTTPException):
        _derive_verify_binding(_battle(), fmt, VerifyBody(battle_id="b1", target_id="synth-iso", phase="break"))


def test_derive_solo_requires_participant():
    body = VerifyBody(battle_id="b1", target_id="synth-iso")
    with pytest.raises(HTTPException) as exc:
        _derive_verify_binding(_battle(), {"format": "solo", "roles": ["fighter"]}, body)
    assert exc.value.status_code == 400
    assert "participant" in str(exc.value.detail)


def test_derive_accepts_matching_hints():
    fmt = {
        "format": "solo",
        "target_id": "synth-iso",
        "roles": ["fighter"],
        "battle_plan": {"phases": [{"phase_id": "solve", "actor": "fighter"}]},
    }
    target_id, kind, phase, role, model_id = _derive_verify_binding(
        _battle(),
        fmt,
        VerifyBody(
            battle_id="b1",
            target_id="synth-iso",
            kind="solo",
            phase="solve",
            role="fighter",
            model_id="model-a",
        ),
    )
    assert target_id == "synth-iso"
    assert kind == "solo"
    assert phase == "solve"
    assert role == "fighter"
    assert model_id == "model-a"


def test_http_verify_unbound_rejected(client, monkeypatch):
    monkeypatch.setattr(
        "agent_arena.internal_router._active_battle",
        lambda *a, **k: {"id": "b-x", "status": "running", "target_id": None, "model_ids": ["m"], "format_id": "f"},
    )
    monkeypatch.setattr("agent_arena.internal_router._rate_limit", lambda bid: None)
    monkeypatch.setattr("agent_arena.persistence.service.format_get", lambda fid: None)
    token = issue_battle_token("b-x")
    resp = client.post(
        "/internal/verify",
        headers={"X-Sandbox-Token": token},
        json={"battle_id": "b-x", "target_id": "tinyshop", "kind": "solo"},
    )
    assert resp.status_code == 400
    assert "no bound target" in resp.json()["detail"]


def test_http_verify_hides_hidden_oracle(client, monkeypatch, tmp_path: Path):
    tid = "oracle-hide"
    target = tmp_path / tid
    (target / "starter").mkdir(parents=True)
    (target / "tests" / "visible").mkdir(parents=True)
    (target / "tests" / "hidden").mkdir(parents=True)
    (target / "target.yaml").write_text(
        f"""
schema_version: 1
id: {tid}
name: Oracle Hide
category: security
difficulty: novice
format: solo
runtime: python311
description: hide oracle
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
    (target / "starter" / "app.py").write_text("def ping():\n    return 'pong'\n", encoding="utf-8")
    (target / "tests" / "visible" / "test_visible.py").write_text(
        "from app import ping\n\ndef test_ping():\n    assert ping() == 'pong'\n",
        encoding="utf-8",
    )
    (target / "tests" / "hidden" / "test_hidden.py").write_text(
        "from app import ping\n\ndef test_hidden():\n    assert ping() == 'pong'\n",
        encoding="utf-8",
    )
    bundle = load_target_bundle(target)

    class _Lib:
        def get_target(self, target_id):
            return bundle if target_id == tid else None

    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    monkeypatch.setattr("agent_arena.internal_router._rate_limit", lambda bid: None)
    monkeypatch.setattr(
        "agent_arena.internal_router._active_battle",
        lambda *a, **k: _battle(target_id=tid, id="b-oracle"),
    )
    monkeypatch.setattr("agent_arena.persistence.service.format_get", lambda fid: None)
    monkeypatch.setattr(
        "agent_arena.target_library.get_target_library",
        lambda root: _Lib(),
    )
    persisted: list[str] = []
    monkeypatch.setattr(
        "agent_arena.persistence.service.round_create",
        lambda *a, **k: persisted.append(a[3] if len(a) > 3 else ""),
    )

    token = issue_battle_token("b-oracle")
    resp = client.post(
        "/internal/verify",
        headers={"X-Sandbox-Token": token},
        json={
            "battle_id": "b-oracle",
            "target_id": tid,
            "kind": "solo",
            "phase": "solve",
            "role": "fighter",
            "model_id": "model-a",
            "submitted_files": {"app.py": "def ping():\n    return 'pong'\n"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["passed"] is True
    assert "visible_passed" in body
    for leaked in (
        "hidden_passed",
        "hidden_exit_code",
        "visible_exit_code",
        "hidden_output",
        "duration_seconds",
        "test_hidden",
        "tests/hidden",
    ):
        assert leaked not in body
    assert persisted
    assert "TRUSTED_VERIFICATION:" in persisted[0]
    assert "hidden_output" not in persisted[0]
    assert "model-a" in persisted[0]


def test_http_verify_solo_missing_model_rejected(client, monkeypatch):
    monkeypatch.setattr(
        "agent_arena.internal_router._active_battle",
        lambda *a, **k: _battle(),
    )
    monkeypatch.setattr("agent_arena.internal_router._rate_limit", lambda bid: None)
    monkeypatch.setattr("agent_arena.persistence.service.format_get", lambda fid: None)
    token = issue_battle_token("b-verify")
    resp = client.post(
        "/internal/verify",
        headers={"X-Sandbox-Token": token},
        json={"battle_id": "b-verify", "target_id": "synth-iso", "kind": "solo"},
    )
    assert resp.status_code == 400
    assert "participant" in resp.json()["detail"]


def test_http_verify_stale_manifest_rejected(client, monkeypatch):
    class _Bundle:
        id = "synth-iso"
        format = "solo"
        manifest_hash = "aaa"
        hidden_hash = "bbb"

    class _Lib:
        def get_target(self, target_id):
            return _Bundle()

    monkeypatch.setattr("agent_arena.internal_router._rate_limit", lambda bid: None)
    monkeypatch.setattr(
        "agent_arena.internal_router._active_battle",
        lambda *a, **k: _battle(target_manifest_hash="ffffffffffffffff"),
    )
    monkeypatch.setattr("agent_arena.persistence.service.format_get", lambda fid: None)
    monkeypatch.setattr(
        "agent_arena.target_library.get_target_library",
        lambda root: _Lib(),
    )
    token = issue_battle_token("b-verify")
    resp = client.post(
        "/internal/verify",
        headers={"X-Sandbox-Token": token},
        json={
            "battle_id": "b-verify",
            "target_id": "synth-iso",
            "kind": "solo",
            "model_id": "model-a",
        },
    )
    assert resp.status_code == 409
    assert "manifest" in resp.json()["detail"]
