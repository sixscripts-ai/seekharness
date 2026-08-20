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
import auth
tok = auth.login('admin', 'nope')
print('AUTH_BROKEN', tok)
END_TOOL
TOOL write path=THEORY.md
Used the admin shortcut.
END_TOOL
TOOL test
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


def test_auth_vs_breaker_two_phase_fake_battle(monkeypatch):
    from agent_arena.sandbox.client import FakeTransport, InternalClient

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"builder": _BUILDER_OK, "breaker": _BREAKER_OK}
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
    assert scores["builder"] == 70.0
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
    action_phases = set()
    breaker_auth = ""
    for r in transport.rounds:
        if r.get("event_type") == "action_log":
            payload = json.loads(r.get("artifact") or "{}")
            action_phases.add(payload.get("phase_id"))
        if r.get("event_type") == "artifact" and r.get("model_id") == "breaker":
            art = r.get("artifact") or ""
            if "FROZEN" in art or "admin-tok" in art or "CHEAT" in art or "auth.py" in art:
                breaker_auth += art
    assert "build" in action_phases
    assert "break" in action_phases
    # Protected restore: final breaker workspace snapshot must keep frozen auth, not CHEAT.
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
    monkeypatch.delenv("ARENA_IN_SANDBOX", raising=False)
    monkeypatch.delenv("ARENA_PREVIEW", raising=False)
