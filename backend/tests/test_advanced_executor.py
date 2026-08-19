import json

from agent_arena.sandbox.executors.advanced_executor import (
    AdvancedExecutor,
    ToolSession,
    fighter_roles,
    parse_tool_calls,
    tool_phase_name,
)
from agent_arena.sandbox.executors.skill_pool import load_skill_pool, mount_skills
from agent_arena.sandbox.executors import get_executor
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor as AE


def test_parse_tool_calls_single_line():
    calls = parse_tool_calls("TOOL ls path=work\nTOOL read path=sandbox.py\nDONE")
    assert calls[0]["tool"] == "ls"
    assert calls[1]["tool"] == "read"
    assert calls[2]["tool"] == "done"


def test_parse_tool_calls_block():
    text = "TOOL write path=solution.py\nprint('hi')\nEND_TOOL\nDONE"
    calls = parse_tool_calls(text)
    assert calls[0]["tool"] == "write"
    assert calls[0]["content"] == "print('hi')"


def test_parse_tool_calls_skills():
    calls = parse_tool_calls("SKILLS: python-kata-fixer, secure-code-execution\nDONE")
    assert calls[0]["tool"] == "skills"
    assert "python-kata-fixer" in calls[0]["chosen"]


def test_skill_pool_loads_real_agents_skills():
    pool = load_skill_pool()
    names = {s["name"] for s in pool}
    assert "secure-code-execution" in names
    assert "python-kata-fixer" in names
    assert len(pool) >= 6
    assert all(s.get("body") for s in pool)


def test_mount_skills_copies_bodies(tmp_path):
    pool = load_skill_pool()
    dest = tmp_path / "work_a"
    dest.mkdir()
    mount_skills(dest, pool)
    skill_md = dest / ".agents" / "skills" / "python-kata-fixer" / "SKILL.md"
    assert skill_md.is_file()
    assert "solution.py" in skill_md.read_text()


def test_tool_session_reject_dotdot(tmp_path):
    sess = ToolSession(tmp_path / "work")
    try:
        sess._resolve("../../etc/passwd")
        assert False
    except ValueError as e:
        assert ".." in str(e) or "escape" in str(e).lower()


def test_tool_session_write_read(tmp_path):
    sess = ToolSession(tmp_path / "work")
    res = sess.write("solution.py", "print('hi')")
    assert "WROTE" in res
    content = sess.read("solution.py")
    assert "hi" in content


def test_tool_session_run_timeout(tmp_path):
    sess = ToolSession(tmp_path / "work", tool_timeout=1)
    sess.write("loop.py", "while True: pass")
    out = sess.run("loop.py")
    assert "timeout" in out.lower()


def test_tool_session_isolation(tmp_path):
    a = ToolSession(tmp_path / "work_a")
    b = ToolSession(tmp_path / "work_b")
    a.write("secret.py", "A_ONLY = 1")
    assert "ERROR" in b.read("secret.py") or "not found" in b.read("secret.py")


def test_repo_owned_harness_not_model_print(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "tests").mkdir()
    (work / "tests" / "test_target.py").write_text(
        "from solution import is_palindrome\n"
        "assert is_palindrome('racecar') is True\n"
        "print('TEST_PASS')\n",
        encoding="utf-8",
    )
    sess = ToolSession(work)
    sess.write("solution.py", "def is_palindrome(s):\n    return True\n")
    # cheating solution fails the real harness (Racecar / hello not asserted here —
    # this harness only checks racecar). Write a failing solution instead:
    sess.write("solution.py", "def is_palindrome(s):\n    return False\n")
    out = sess.test("")
    assert "TEST_FAIL" in out or "rc=1" in out or "Error" in out or "assert" in out.lower() or "FAIL" in out


def test_skill_read_tracked(tmp_path):
    pool = load_skill_pool()
    work = tmp_path / "work"
    work.mkdir()
    mount_skills(work, pool)
    sess = ToolSession(work)
    sess.read(".agents/skills/python-kata-fixer/SKILL.md")
    assert "python-kata-fixer" in sess.skill_reads


def test_advanced_executor_requires_sandbox_gate():
    import os

    os.environ.pop("ARENA_IN_SANDBOX", None)
    ex = AdvancedExecutor()
    try:
        ex.run_battle(
            battle_id="b",
            format_config={
                "name": "Tool-using coding race",
                "engine": "agent_tool_race",
                "roles": ["player_a", "player_b", "judge"],
                "phases": [{"name": "race", "participants": ["player_a", "player_b"]}],
                "target_code": "x",
                "max_tool_turns": 1,
            },
            model_ids=["a", "b"],
            round_visibility="open",
            timeout_seconds=60,
            role_to_model={"player_a": "a", "player_b": "b"},
            client=None,
        )
        assert False, "should have raised"
    except RuntimeError as e:
        assert "sandbox" in str(e).lower()


def test_get_executor_resolves_advanced():
    cfg = {"name": "Tool-using coding race", "engine": "agent_tool_race"}
    assert isinstance(get_executor(cfg), AE)
    cfg2 = {"id": "tool-using-coding-race", "engine": "agent_tool_race"}
    assert isinstance(get_executor(cfg2), AE)
    assert isinstance(get_executor("agent_tool_race"), AE)


def test_universal_flag_routes_to_advanced():
    # A non-race engine opts into the toolbelt purely via `universal: True`.
    cfg = {
        "name": "Debugging race",
        "id": "debugging-race",
        "engine": "same_target_race",
        "universal": True,
    }
    assert isinstance(get_executor(cfg), AE)
    # Without the flag, the same engine resolves to its prose executor.
    from agent_arena.sandbox.executors.same_target_race import SameTargetRaceExecutor

    assert isinstance(
        get_executor({"name": "Debugging race", "engine": "same_target_race"}),
        SameTargetRaceExecutor,
    )
    assert isinstance(
        get_executor(
            {
                "name": "Injection agent vs hardened agent",
                "engine": "agent_vs_agent",
                "universal": True,
            }
        ),
        AE,
    )
    from agent_arena.sandbox.executors.agent_vs_agent import AgentVsAgentExecutor

    assert isinstance(
        get_executor(
            {
                "name": "Injection agent vs hardened agent",
                "engine": "agent_vs_agent",
            }
        ),
        AgentVsAgentExecutor,
    )


def test_race_loop_reads_skill_and_passes_harness(monkeypatch):
    import os

    from agent_arena.sandbox.client import FakeTransport, InternalClient

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    reply = (
        "SKILLS: python-kata-fixer\n"
        "TOOL read path=.agents/skills/python-kata-fixer/SKILL.md\n"
        "TOOL write path=solution.py\n"
        "def is_palindrome(s: str) -> bool:\n"
        "    n = ''.join(c.lower() for c in s if c.isalnum())\n"
        "    return n == n[::-1]\n"
        "END_TOOL\n"
        "TOOL write path=THEORY.md\n"
        "Used python-kata-fixer.\n"
        "END_TOOL\n"
        "TOOL test\n"
        "DONE\n"
    )
    transport = FakeTransport()
    transport.model_replies = {"a": reply, "b": reply}
    transport.judge_result = {
        "scores": {"a": 90.0, "b": 80.0},
        "justifications": {"a": "pass", "b": "pass"},
        "judge_model": "mock",
    }
    client = InternalClient(transport)
    ex = AdvancedExecutor()
    scores = ex.run_battle(
        battle_id="race-1",
        format_config={
            "name": "Tool-using coding race",
            "engine": "agent_tool_race",
            "roles": ["player_a", "player_b", "judge"],
            "phases": [{"name": "race", "participants": ["player_a", "player_b"]}],
            "target_code": "def is_palindrome(s): return s == s[::-1]\n",
            "max_tool_turns": 2,
            "max_tool_steps": 20,
            "pick_per_battle": 1,
            "outcome_markers": ["DONE", "TEST_PASS", "TEST_FAIL"],
        },
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"player_a": "a", "player_b": "b"},
        client=client,
    )
    assert scores["a"] == 90.0
    artifacts = "\n".join(r.get("artifact", "") for r in transport.rounds)
    assert "python-kata-fixer" in artifacts
    assert "TEST_PASS" in artifacts
    os.environ.pop("ARENA_IN_SANDBOX", None)


_PASSING_TOOLS = (
    "SKILLS: python-kata-fixer\n"
    "TOOL read path=.agents/skills/python-kata-fixer/SKILL.md\n"
    "TOOL write path=solution.py\n"
    "def is_palindrome(s: str) -> bool:\n"
    "    n = ''.join(c.lower() for c in s if c.isalnum())\n"
    "    return n == n[::-1]\n"
    "END_TOOL\n"
    "TOOL write path=THEORY.md\n"
    "Used python-kata-fixer.\n"
    "END_TOOL\n"
    "TOOL test\n"
)

_RACE_FORMAT = {
    "name": "Tool-using coding race",
    "engine": "agent_tool_race",
    "roles": ["player_a", "player_b", "judge"],
    "phases": [{"name": "race", "participants": ["player_a", "player_b"]}],
    "target_code": "def is_palindrome(s): return s == s[::-1]\n",
    "pick_per_battle": 1,
    "outcome_markers": ["DONE", "TEST_PASS", "TEST_FAIL"],
}


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


def _run_fake_race(
    monkeypatch,
    reply,
    *,
    max_tool_turns=2,
    max_tool_steps=20,
    format_overlay=None,
    role_to_model=None,
):
    from agent_arena.sandbox.client import FakeTransport, InternalClient

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"a": reply, "b": reply}
    transport.judge_result = {
        "scores": {"a": 90.0, "b": 80.0},
        "justifications": {"a": "pass", "b": "pass"},
        "judge_model": "mock",
    }
    client = InternalClient(transport)
    ex = AdvancedExecutor()
    fmt = {
        **_RACE_FORMAT,
        "max_tool_turns": max_tool_turns,
        "max_tool_steps": max_tool_steps,
    }
    if format_overlay:
        fmt.update(format_overlay)
    mapping = role_to_model or {"player_a": "a", "player_b": "b"}
    scores = ex.run_battle(
        battle_id="race-1",
        format_config=fmt,
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model=mapping,
        client=client,
    )
    return scores, transport


def test_race_loop_passes_without_done(monkeypatch):
    import os

    scores, transport = _run_fake_race(monkeypatch, _PASSING_TOOLS)
    assert scores["a"] == 90.0
    results = _executor_results(transport.rounds)
    assert results, "expected EXECUTOR_RESULT"
    assert all(r.get("passed") is True for r in results)
    assert all(r.get("outcome") == "TEST_PASS" for r in results)
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_race_loop_pass_then_step_cap_still_passed(monkeypatch):
    import os

    extra_ls = "\n".join(["TOOL ls"] * 20) + "\n"
    scores, transport = _run_fake_race(
        monkeypatch,
        _PASSING_TOOLS + extra_ls,
        max_tool_turns=4,
        max_tool_steps=8,
    )
    assert scores["a"] == 90.0
    results = _executor_results(transport.rounds)
    assert results, "expected EXECUTOR_RESULT"
    assert all(r.get("passed") is True for r in results)
    assert all(r.get("outcome") == "TEST_PASS" for r in results)
    wiped = [
        r
        for r in results
        if r.get("outcome") == "STEP_BUDGET_EXCEEDED" and r.get("passed") is False
    ]
    assert wiped == []
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_fighter_roles_from_phases():
    assert fighter_roles(
        {
            "roles": ["agent_a", "agent_b", "judge"],
            "phases": [
                {"name": "engage", "participants": ["agent_a", "agent_b"]},
                {"name": "judge", "participants": ["judge"]},
            ],
        }
    ) == ["agent_a", "agent_b"]
    assert tool_phase_name(
        {
            "phases": [
                {"name": "engage", "participants": ["agent_a", "agent_b"]},
            ]
        }
    ) == "engage"
    assert fighter_roles({"roles": ["player_a", "player_b", "judge"]}) == [
        "player_a",
        "player_b",
    ]


def test_race_loop_uses_agent_roles(monkeypatch):
    import os

    scores, transport = _run_fake_race(
        monkeypatch,
        _PASSING_TOOLS,
        format_overlay={
            "name": "Custom dual-agent race",
            "recommended_skills": ["python-kata-fixer"],
            "roles": ["agent_a", "agent_b", "judge"],
            "phases": [
                {"name": "engage", "participants": ["agent_a", "agent_b"]},
                {"name": "judge", "participants": ["judge"]},
            ],
        },
        role_to_model={"agent_a": "a", "agent_b": "b"},
    )
    assert scores["a"] == 90.0
    results = _executor_results(transport.rounds)
    assert {r.get("role") for r in results} == {"agent_a", "agent_b"}
    assert all(r.get("passed") is True for r in results)
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_extract_on_py_write(tmp_path):
    sess = ToolSession(tmp_path / "work")
    sess.write(
        "solution.py",
        "Here is the code:\n```python\ndef is_palindrome(s):\n    return True\n```\n",
    )
    text = sess.read("solution.py")
    assert "Here is the code" not in text
    assert "def is_palindrome" in text
