"""BattlePlan parser, handoff isolation, and Auth vs breaker first slice."""

from __future__ import annotations

import json

from agent_arena.sandbox.executors.battle_plan import (
    is_forbidden_handoff,
    parse_battle_plan,
    restore_protected,
    snapshot_handoff,
    write_allowed_file,
)
from agent_arena.sandbox.executors import get_executor
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
from agent_arena.sandbox.executors.build_and_break import BuildAndBreakExecutor
from agent_arena.seed_formats import ALL_FORMATS


def _auth_cfg():
    return next(f for f in ALL_FORMATS if f["name"] == "Auth system vs breaker")


def test_parse_auth_battle_plan():
    plan = parse_battle_plan(_auth_cfg())
    assert plan is not None
    assert [p.phase_id for p in plan.phases] == ["build", "break"]
    assert plan.phases[0].actor == "builder"
    assert plan.phases[1].actor == "breaker"
    assert plan.phases[1].handoff_from == ["build"]
    assert plan.phases[1].handoff_artifacts == ["auth.py"]
    assert plan.phases[1].protected_artifacts == ["auth.py"]
    assert "AUTH_BROKEN" in plan.phases[1].test_code
    assert "register" in plan.phases[0].test_code


def test_no_plan_without_flag():
    assert parse_battle_plan({"engine": "build_and_break"}) is None
    assert parse_battle_plan({"battle_plan": False}) is None


def test_auth_routes_to_advanced_not_build_and_break():
    cfg = _auth_cfg()
    ex = get_executor(cfg)
    assert isinstance(ex, AdvancedExecutor)
    assert not isinstance(ex, BuildAndBreakExecutor)
    other = get_executor(
        {"name": "Code sandbox vs escapee", "engine": "build_and_break"}
    )
    assert isinstance(other, BuildAndBreakExecutor)


def test_handoff_allowlist_only(tmp_path):
    work = tmp_path / "builder"
    work.mkdir()
    (work / "auth.py").write_text("TOKEN=ok\n", encoding="utf-8")
    (work / ".env").write_text("SECRET=nope\n", encoding="utf-8")
    (work / "tests").mkdir()
    (work / "tests" / "test_target.py").write_text("print('TEST_PASS')\n", encoding="utf-8")
    (work / "notes.md").write_text("private\n", encoding="utf-8")
    snap = snapshot_handoff(
        work, ["auth.py", "tests/test_target.py", ".env", "../etc/passwd"]
    )
    assert set(snap["files"]) == {"auth.py"}
    assert b"TOKEN=ok" in snap["files"]["auth.py"]
    dest = tmp_path / "breaker"
    dest.mkdir()
    for rel, data in snap["files"].items():
        assert write_allowed_file(dest, rel, data)
    assert (dest / "auth.py").read_text(encoding="utf-8") == "TOKEN=ok\n"
    assert not (dest / "tests" / "test_target.py").exists()
    assert not (dest / ".env").exists()
    assert not (dest / "notes.md").exists()


def test_forbidden_paths():
    assert is_forbidden_handoff("tests/test_target.py")
    assert is_forbidden_handoff(".env")
    assert is_forbidden_handoff("id_rsa")
    assert not is_forbidden_handoff("auth.py")
    assert not is_forbidden_handoff("exploit.py")


def test_protected_restore_overwrites_cheat(tmp_path):
    work = tmp_path / "breaker"
    work.mkdir()
    frozen = b"FROZEN_AUTH = 1\n"
    write_allowed_file(work, "auth.py", b"CHEAT = 1\n")
    restore_protected(work, {"auth.py": frozen})
    assert (work / "auth.py").read_bytes() == frozen


_BUILDER_OK = """SKILLS: python-kata-fixer
TOOL write path=auth.py
_users = {}
_tokens = {}

def register(username, password):
    if not username or not password:
        raise ValueError('required')
    _users[username] = password
    return True

def login(username, password):
    if username == 'admin':
        tok = 'admin-tok'
        _tokens[tok] = 'admin'
        return tok
    if not password:
        return None
    if _users.get(username) == password:
        tok = username + '-tok'
        _tokens[tok] = username
        return tok
    return None

def verify(token):
    return _tokens.get(token)
END_TOOL
TOOL write path=THEORY.md
Alice login works; left an admin shortcut.
END_TOOL
TOOL test
"""

_BREAKER_OK = """SKILLS: python-kata-fixer
TOOL write path=auth.py
print('CHEAT')
END_TOOL
TOOL write path=exploit.py
from pathlib import Path
assert not Path('../work_builder').exists()
import auth
tok = auth.login('admin', 'nope')
print('AUTH_BROKEN', tok)
END_TOOL
TOOL write path=THEORY.md
Used the admin shortcut.
END_TOOL
DONE
"""

_BREAKER_STUB = """SKILLS: python-kata-fixer
TOOL write path=exploit.py
print('AUTH_BROKEN')
END_TOOL
DONE
"""

_BREAKER_MONKEYPATCH = """SKILLS: python-kata-fixer
TOOL write path=exploit.py
import auth
auth.verify = lambda token: 'admin'
print('AUTH_BROKEN', 'faketok')
END_TOOL
TOOL write path=THEORY.md
Monkeypatched verify.
END_TOOL
DONE
"""

_BREAKER_INJECT = """SKILLS: python-kata-fixer
TOOL write path=exploit.py
import auth
auth._tokens['injected'] = 'admin'
print('AUTH_BROKEN', 'injected')
END_TOOL
TOOL write path=THEORY.md
Wrote straight to the session store.
END_TOOL
DONE
"""

_BUILDER_NO_AUTH = """SKILLS: python-kata-fixer
TOOL write path=THEORY.md
No auth.py on purpose.
END_TOOL
DONE
"""


def _executor_results(rounds):
    found = []
    marker = "EXECUTOR_RESULT:"
    for r in rounds:
        art = r.get("artifact") or ""
        if marker not in art:
            continue
        payload = art.split(marker, 1)[1].strip()
        found.append(json.loads(payload))
    return found


def _run_auth_battle(monkeypatch, builder_reply, breaker_reply):
    from agent_arena.sandbox.client import FakeTransport, InternalClient

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"builder": builder_reply, "breaker": breaker_reply}
    transport.judge_result = {
        "scores": {"builder": 70.0, "breaker": 80.0},
        "justifications": {"builder": "ok", "breaker": "ok"},
        "judge_model": "mock",
    }
    client = InternalClient(transport)
    cfg = dict(_auth_cfg())
    cfg["max_tool_turns"] = 2
    cfg["max_tool_steps"] = 20
    ex = AdvancedExecutor()
    scores = ex.run_battle(
        battle_id="auth-1",
        format_config=cfg,
        model_ids=["builder", "breaker"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"builder": "builder", "breaker": "breaker"},
        client=client,
    )
    monkeypatch.delenv("ARENA_IN_SANDBOX", raising=False)
    monkeypatch.delenv("ARENA_PREVIEW", raising=False)
    return scores, transport, cfg


def test_auth_vs_breaker_two_phase_fake_battle(monkeypatch):
    from agent_arena import evidence, scoring

    _scores, transport, cfg = _run_auth_battle(monkeypatch, _BUILDER_OK, _BREAKER_OK)
    results = _executor_results(transport.rounds)
    phases = {r.get("phase"): r for r in results}
    assert "build" in phases and "break" in phases
    assert phases["build"]["role"] == "builder"
    assert phases["break"]["role"] == "breaker"
    assert phases["build"]["passed"] is True
    assert phases["break"]["passed"] is True
    assert phases["build"]["outcome"] == "TEST_PASS"
    assert phases["break"]["outcome"] == "TEST_PASS"
    assert (phases["build"].get("policy") or {}).get("status") == "clean"
    assert (phases["break"].get("policy") or {}).get("status") == "clean"
    action_logs = []
    for r in transport.rounds:
        if r.get("event_type") != "action_log":
            continue
        payload = json.loads(r.get("artifact") or "{}")
        action_logs.append(payload)
    action_phases = {p.get("phase_id") for p in action_logs}
    assert "build" in action_phases
    assert "break" in action_phases
    finalize_tests = [
        p
        for p in action_logs
        if p.get("action") == "test"
        and str(p.get("exec_id") or "").startswith("exec_")
    ]
    assert finalize_tests
    break_files = None
    for r in transport.rounds:
        if r.get("event_type") != "artifact" or r.get("model_id") != "breaker":
            continue
        art = r.get("artifact") or ""
        if art.strip().startswith("{"):
            try:
                break_files = json.loads(art)
            except Exception:
                continue
    assert isinstance(break_files, dict)
    auth_src = (break_files.get("files") or {}).get("auth.py") or ""
    assert "admin-tok" in auth_src
    assert "CHEAT" not in auth_src
    assert "exploit.py" in (break_files.get("files") or {})
    summary = evidence.build_battle_evidence("auth-1", results, cfg)
    decision = scoring.decide_winner(summary, cfg)
    assert decision["reason"] != "incomplete_evidence"
    assert decision["winner"] == "breaker"
    assert decision["verified_solution"] is True
    assert "breaker" in decision["verified_fighters"]
    assert set(summary["fighters"][0]["phases"]) <= {"build", "break"}
    builder_f = next(f for f in summary["fighters"] if f["role"] == "builder")
    breaker_f = next(f for f in summary["fighters"] if f["role"] == "breaker")
    assert set(builder_f["phases"]) == {"build"}
    assert set(breaker_f["phases"]) == {"break"}


def test_stub_auth_broken_print_fails(monkeypatch):
    _scores, transport, _cfg = _run_auth_battle(
        monkeypatch, _BUILDER_OK, _BREAKER_STUB
    )
    results = _executor_results(transport.rounds)
    phases = {r.get("phase"): r for r in results}
    assert phases["build"]["passed"] is True
    assert phases["break"]["passed"] is False


def test_monkeypatch_verify_fails(monkeypatch):
    _scores, transport, _cfg = _run_auth_battle(
        monkeypatch, _BUILDER_OK, _BREAKER_MONKEYPATCH
    )
    results = _executor_results(transport.rounds)
    phases = {r.get("phase"): r for r in results}
    assert phases["build"]["passed"] is True
    assert phases["break"]["passed"] is False


def test_store_injection_fails(monkeypatch):
    _scores, transport, _cfg = _run_auth_battle(
        monkeypatch, _BUILDER_OK, _BREAKER_INJECT
    )
    results = _executor_results(transport.rounds)
    phases = {r.get("phase"): r for r in results}
    assert phases["build"]["passed"] is True
    assert phases["break"]["passed"] is False


def test_missing_auth_handoff_skips_break(monkeypatch):
    _scores, transport, _cfg = _run_auth_battle(
        monkeypatch, _BUILDER_NO_AUTH, _BREAKER_OK
    )
    results = _executor_results(transport.rounds)
    phases = {r.get("phase"): r for r in results}
    assert phases["build"]["passed"] is False
    assert phases["break"]["passed"] is False
    assert (phases["break"].get("policy") or {}).get("status") == "invalid"
    assert "missing-handoff" in (phases["break"].get("policy") or {}).get(
        "violations"
    )
    assert not any(
        (r.get("event_type") == "phase_start" and r.get("phase") == "break")
        or (
            r.get("event_type") == "action_log"
            and json.loads(r.get("artifact") or "{}").get("phase_id") == "break"
            and json.loads(r.get("artifact") or "{}").get("action")
            in {"write", "read", "preview"}
        )
        for r in transport.rounds
    )


def test_fullstack_services_spec_parsing():
    """Verify target-driven service specification parsing."""
    from agent_arena.sandbox.executors.battle_plan import parse_services_spec

    # Default fallback when target.yaml has no custom services
    defaults = parse_services_spec({})
    assert defaults["frontend"].port == 5173
    assert defaults["frontend"].readiness_path == "/"
    assert defaults["backend"].port == 8000
    assert defaults["backend"].readiness_path == "/health"

    # Custom target.yaml specification
    custom = parse_services_spec(
        {
            "services": {
                "web_frontend": {"port": 3000, "readiness_path": "/ready"},
                "api_server": {"port": 9000, "readiness_path": "/api/health"},
            }
        }
    )
    assert custom["web_frontend"].port == 3000
    assert custom["web_frontend"].readiness_path == "/ready"
    assert custom["api_server"].port == 9000
    assert custom["api_server"].readiness_path == "/api/health"


def test_fullstack_3_tier_filesystem_isolation(tmp_path):
    """Verify 3-tier filesystem snapshot and builder-private wipe.

    1. Builder writes code in /arena/builder-private
    2. Snapshot approved deployment to /arena/deployment (excluding secrets/.git)
    3. Wipe /arena/builder-private
    4. Breaker has zero access to builder source code.
    """
    from agent_arena.sandbox.executors.battle_plan import (
        snapshot_to_deployment,
        wipe_builder_private,
    )

    builder_private = tmp_path / "builder-private"
    builder_private.mkdir()
    deployment = tmp_path / "deployment"

    # Write builder files
    (builder_private / "backend").mkdir()
    (builder_private / "backend" / "main.py").write_text("print('fastapi')", encoding="utf-8")
    (builder_private / "frontend").mkdir()
    (builder_private / "frontend" / "App.tsx").write_text("console.log('react')", encoding="utf-8")
    (builder_private / ".env").write_text("SUPER_SECRET=leak", encoding="utf-8")
    (builder_private / ".arena_secret").write_text("FLAG{secret}", encoding="utf-8")

    # Snapshot to deployment
    copied = snapshot_to_deployment(builder_private, deployment)
    assert "backend/main.py" in copied
    assert "frontend/App.tsx" in copied
    assert (deployment / "backend" / "main.py").exists()
    assert (deployment / "frontend" / "App.tsx").exists()
    # Secrets must not be copied to deployment
    assert not (deployment / ".env").exists()
    assert not (deployment / ".arena_secret").exists()

    # Builder phase ends -> wipe builder-private
    wiped = wipe_builder_private(builder_private)
    assert wiped is True
    assert not builder_private.exists()

    # Breaker workspace now initialized fresh
    breaker_private = tmp_path / "breaker-private"
    breaker_private.mkdir()
    assert not (breaker_private / "backend").exists()
    assert not (breaker_private / "frontend").exists()


def test_classify_deployment_failure():
    """Verify distinction between BUILDER_OWNED error and ARENA_INFRA_FAILURE."""
    from agent_arena.sandbox.executors.battle_plan import classify_deployment_failure

    # Builder owned
    assert classify_deployment_failure("SyntaxError: invalid syntax in main.py") == "BUILDER_OWNED"
    assert classify_deployment_failure("ModuleNotFoundError: No module named 'fastapi'") == "BUILDER_OWNED"
    assert classify_deployment_failure("pnpm build failed with exit code 1") == "BUILDER_OWNED"

    # Arena infra failure
    assert classify_deployment_failure("Error: address already in use 0.0.0.0:5173") == "ARENA_INFRA_FAILURE"
    assert classify_deployment_failure("Permission denied: cannot bind socket") == "ARENA_INFRA_FAILURE"
    assert classify_deployment_failure("Neon API unavailable: 503 Service Unavailable") == "ARENA_INFRA_FAILURE"

