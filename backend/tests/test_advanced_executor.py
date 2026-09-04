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
    assert (
        "TEST_FAIL" in out
        or "rc=1" in out
        or "Error" in out
        or "assert" in out.lower()
        or "FAIL" in out
    )


def test_skill_read_tracked(tmp_path):
    pool = load_skill_pool()
    work = tmp_path / "work"
    work.mkdir()
    mount_skills(work, pool)
    sess = ToolSession(work)
    blocked = sess.read(".agents/skills/python-kata-fixer/SKILL.md")
    assert blocked.success is False
    assert blocked.policy_rejected is True
    assert "use_skill" in blocked.output
    assert sess.skill_reads == set()
    loaded = sess.use_skill("python-kata-fixer")
    assert loaded.success is True
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
    assert (
        tool_phase_name(
            {
                "phases": [
                    {"name": "engage", "participants": ["agent_a", "agent_b"]},
                ]
            }
        )
        == "engage"
    )
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


def test_injection_toolbelt_attacker_and_defender(monkeypatch):
    import os

    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors import get_executor
    from agent_arena.seed_formats import ALL_FORMATS
    from tests.test_universal_targets import FIXES, INJECTION_EXPLOIT

    cfg = next(
        c for c in ALL_FORMATS if c["name"] == "Injection agent vs hardened agent"
    )
    cfg = {**cfg, "pick_per_battle": 1, "max_tool_turns": 2, "max_tool_steps": 20}
    exe = get_executor(cfg)
    assert isinstance(exe, AdvancedExecutor)
    assert fighter_roles(cfg) == ["agent_a", "agent_b"]

    atk = (
        "SKILLS: python-kata-fixer\n"
        "TOOL read path=.agents/skills/python-kata-fixer/SKILL.md\n"
        "TOOL write path=exploit.py\n"
        f"{INJECTION_EXPLOIT}"
        "END_TOOL\n"
        "TOOL write path=THEORY.md\n"
        "empty query dumps FLAG\n"
        "END_TOOL\n"
        "TOOL test\n"
    )
    dfn = (
        "SKILLS: python-kata-fixer\n"
        "TOOL read path=.agents/skills/python-kata-fixer/SKILL.md\n"
        "TOOL write path=solution.py\n"
        f"{FIXES['Injection agent vs hardened agent']}"
        "END_TOOL\n"
        "TOOL write path=THEORY.md\n"
        "never return FLAG\n"
        "END_TOOL\n"
        "TOOL test\n"
    )
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"a": atk, "b": dfn}
    transport.judge_result = {
        "scores": {"a": 90.0, "b": 80.0},
        "justifications": {"a": "leak", "b": "harden"},
        "judge_model": "mock",
    }
    scores = exe.run_battle(
        battle_id="inj-1",
        format_config=cfg,
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"agent_a": "a", "agent_b": "b"},
        client=InternalClient(transport),
    )
    results = {r.get("role"): r for r in _executor_results(transport.rounds)}
    assert scores["a"] == 90.0
    assert set(results) == {"agent_a", "agent_b"}
    assert results["agent_a"].get("passed") is True
    assert results["agent_a"].get("outcome") == "TEST_PASS"
    assert results["agent_b"].get("passed") is True
    assert results["agent_b"].get("outcome") == "TEST_PASS"
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_ls_prompt_does_not_count_step(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.py").write_text("x", encoding="utf-8")
    sess = ToolSession(work)
    sess.ls(count_step=False)
    assert sess.steps == 0
    sess.ls()
    assert sess.steps == 1


def test_duplicate_use_skill_does_not_count(tmp_path):
    """Under canonical execution kernel contract, repeated use_skill costs 1 step."""
    pool = load_skill_pool()
    work = tmp_path / "work"
    work.mkdir()
    mount_skills(work, pool)
    sess = ToolSession(work)
    first = sess.use_skill("python-kata-fixer")
    assert "solution.py" in first
    assert sess.steps == 1
    second = sess.use_skill("python-kata-fixer")
    assert "SKILL_ALREADY_LOADED" in second
    assert sess.steps == 2


def test_injection_format_picks_one_skill():
    from agent_arena.seed_formats import ALL_FORMATS

    cfg = next(
        c for c in ALL_FORMATS if c["name"] == "Injection agent vs hardened agent"
    )
    assert cfg["pick_per_battle"] == 1


def test_tool_run_harness_early_stop(monkeypatch):
    import os

    reply = (
        _PASSING_TOOLS.replace(
            "TOOL test\n", "TOOL run path=tests/test_target.py\nEND_TOOL\n"
        )
        + "\n".join(["TOOL ls"] * 20)
        + "\n"
    )
    scores, transport = _run_fake_race(
        monkeypatch,
        reply,
        max_tool_turns=4,
        max_tool_steps=8,
    )
    assert scores["a"] == 90.0
    results = _executor_results(transport.rounds)
    assert results, "expected EXECUTOR_RESULT"
    assert all(r.get("passed") is True for r in results)
    assert all(r.get("outcome") == "TEST_PASS" for r in results)
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_injection_attacker_duplicate_skills_then_exploit(monkeypatch):
    import os

    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors import get_executor
    from agent_arena.seed_formats import ALL_FORMATS
    from tests.test_universal_targets import FIXES, INJECTION_EXPLOIT

    cfg = next(
        c for c in ALL_FORMATS if c["name"] == "Injection agent vs hardened agent"
    )
    cfg = {**cfg, "pick_per_battle": 3, "max_tool_turns": 2, "max_tool_steps": 15}
    exe = get_executor(cfg)
    waste = (
        "SKILLS: python-kata-fixer, secure-code-execution, sandbox-runtime-engineer\n"
        "TOOL use_skill name=python-kata-fixer\n"
        "TOOL use_skill name=secure-code-execution\n"
        "TOOL use_skill name=sandbox-runtime-engineer\n"
        "TOOL read path=TARGET.md\n"
        "TOOL read path=solution.py\n"
        "TOOL read path=README.md\n"
        "TOOL ls path=tests\n"
        "TOOL use_skill name=python-kata-fixer\n"
        "TOOL use_skill name=secure-code-execution\n"
        "TOOL use_skill name=sandbox-runtime-engineer\n"
        "TOOL read path=tests/test_target.py\n"
        "TOOL write path=exploit.py\n"
        f"{INJECTION_EXPLOIT}"
        "END_TOOL\n"
        "TOOL write path=THEORY.md\n"
        "empty query dumps FLAG\n"
        "END_TOOL\n"
        "TOOL test\n"
    )
    dfn = (
        "SKILLS: python-kata-fixer\n"
        "TOOL use_skill name=python-kata-fixer\n"
        "TOOL write path=solution.py\n"
        f"{FIXES['Injection agent vs hardened agent']}"
        "END_TOOL\n"
        "TOOL write path=THEORY.md\n"
        "never return FLAG\n"
        "END_TOOL\n"
        "TOOL test\n"
    )
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"a": waste, "b": dfn}
    transport.judge_result = {
        "scores": {"a": 90.0, "b": 80.0},
        "justifications": {"a": "leak", "b": "harden"},
        "judge_model": "mock",
    }
    scores = exe.run_battle(
        battle_id="inj-waste-1",
        format_config=cfg,
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"agent_a": "a", "agent_b": "b"},
        client=InternalClient(transport),
    )
    results = {r.get("role"): r for r in _executor_results(transport.rounds)}
    assert scores["a"] == 90.0
    assert results["agent_a"].get("passed") is True
    assert results["agent_a"].get("outcome") == "TEST_PASS"
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_model_error_does_not_abort_opponent(monkeypatch):
    import os

    from agent_arena.sandbox.client import FakeTransport, InternalClient

    class BoomA(FakeTransport):
        def post(self, path, json):
            if path == "/internal/model" and json.get("model_id") == "a":
                raise RuntimeError(
                    "internal /internal/model exhausted retries: server 502"
                )
            return super().post(path, json)

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = BoomA()
    transport.model_replies = {"a": _PASSING_TOOLS, "b": _PASSING_TOOLS}
    transport.judge_result = {
        "scores": {"a": 10.0, "b": 90.0},
        "justifications": {"a": "fail", "b": "pass"},
        "judge_model": "mock",
    }
    ex = AdvancedExecutor()
    scores = ex.run_battle(
        battle_id="boom-a",
        format_config={
            **_RACE_FORMAT,
            "max_tool_turns": 2,
            "max_tool_steps": 20,
        },
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"player_a": "a", "player_b": "b"},
        client=InternalClient(transport),
    )
    results = {r.get("model_id"): r for r in _executor_results(transport.rounds)}
    assert scores["b"] == 90.0
    assert results["a"].get("passed") is False
    assert results["b"].get("passed") is True
    assert results["b"].get("outcome") == "TEST_PASS"
    os.environ.pop("ARENA_IN_SANDBOX", None)


# --- A1: workdir jail escape -------------------------------------------------


def test_tool_session_reject_absolute_path(tmp_path):
    sess = ToolSession(tmp_path / "work")
    try:
        sess._resolve("/etc/passwd")
        assert False, "absolute path should be rejected"
    except ValueError as e:
        assert "absolute" in str(e).lower() or "reject" in str(e).lower()


def test_tool_session_reject_symlink_escape(tmp_path):
    import os

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("TOP_SECRET", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    os.symlink(outside, work / "link")
    sess = ToolSession(work)
    # Reading through a symlink that points outside the jail must be blocked.
    out = sess.read("link/secret.txt")
    assert "ERROR" in out
    assert "TOP_SECRET" not in out


def test_shell_rejects_absolute_path(tmp_path):
    sess = ToolSession(tmp_path / "work")
    out = sess.shell("cat /etc/passwd")
    assert "ERROR" in out
    assert "absolute" in out.lower()
    assert "root:" not in out


def test_shell_rejects_dotdot(tmp_path):
    sess = ToolSession(tmp_path / "work")
    out = sess.shell("cat ../secret.txt")
    assert "ERROR" in out
    assert ".." in out


def test_shell_rejects_home_env_expansion(tmp_path):
    sess = ToolSession(tmp_path / "work")
    for cmd in ("cd $HOME", "cat ${HOME}/secret.txt", "ls $HOME"):
        out = sess.shell(cmd)
        assert "ERROR" in out, cmd
        assert "HOME" in out, cmd


def test_shell_env_strips_secret_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("APPWRITE_API_KEY", "supersecret-key-123")
    monkeypatch.setenv("APPWRITE_ENDPOINT", "https://sfo.cloud.appwrite.io/v1")
    monkeypatch.setenv("HOST_OPENROUTER_KEY", "sk-host-456")
    monkeypatch.setenv("HOST_GROQ_KEY", "sk-groq-789")
    monkeypatch.setenv("HOST_XAI_KEY", "sk-xai-000")
    monkeypatch.setenv("JUDGE_MODAL_SECRET", "judge-secret-111")
    monkeypatch.setenv("MODAL_PROXY_TOKEN", "proxy-tok-222")
    monkeypatch.setenv("FERNET_KEY", "fernet-333")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-444")
    monkeypatch.setenv("BATTLE_TOKEN", "battle-tok-789")
    sess = ToolSession(tmp_path / "work")
    out = sess.shell("env")
    for secret in (
        "supersecret-key-123",
        "sk-host-456",
        "sk-groq-789",
        "sk-xai-000",
        "judge-secret-111",
        "proxy-tok-222",
        "fernet-333",
        "internal-444",
        "battle-tok-789",
    ):
        assert secret not in out
    # Non-credential config must survive (fighters may legitimately need it).
    assert "sfo.cloud.appwrite.io" in out


def test_shell_allows_relative_workdir_file(tmp_path):
    sess = ToolSession(tmp_path / "work")
    sess.write("hello.txt", "workdir-only")
    out = sess.shell("cat hello.txt")
    assert "workdir-only" in out
    assert "ERROR:" not in out


def test_shell_blocks_curl_without_network(tmp_path):
    sess = ToolSession(tmp_path / "work", allow_network=False)
    out = sess.shell("curl https://example.invalid/pwn")
    assert "ERROR" in out
    assert "network" in out.lower() or "blocked" in out.lower()


def test_install_blocks_wget_without_network(tmp_path):
    sess = ToolSession(tmp_path / "work")
    out = sess.install("wget http://10.0.0.1/pkg")
    assert "ERROR" in out
    assert "blocked" in out.lower()


def test_shell_ssrf_even_when_network_enabled(tmp_path):
    sess = ToolSession(tmp_path / "work", allow_network=True)
    out = sess.shell("curl http://127.0.0.1/")
    assert "ERROR" in out
    assert "blocked" in out.lower()
    assert (
        "127.0.0.1" in out
        or "loopback" in out.lower()
        or "not allowed" in out.lower()
        or "non-public" in out.lower()
    )


def test_shell_blocks_urlopen_loopback(tmp_path):
    sess = ToolSession(tmp_path / "work")
    out = sess.shell(
        "python3 -c \"import urllib.request; urllib.request.urlopen('http://169.254.169.254/')\""
    )
    assert "ERROR" in out
    assert "blocked" in out.lower()


def test_bg_rejects_absolute_path(tmp_path):
    sess = ToolSession(tmp_path / "work")
    out = sess.bg("escape", "cat /etc/passwd")
    assert "ERROR" in out
    assert "absolute" in out.lower()


def test_flipped_formats_resolve_to_advanced_executor():
    from agent_arena.seed_formats import ALL_FORMATS

    flipped = {
        "Tool-using coding race",
        "Code review duel",
        "Debugging race",
        "Injection agent vs hardened agent",
        "RE solve race",
        "Pwn exploit race",
    }
    by_name = {c["name"]: c for c in ALL_FORMATS}
    for name in flipped:
        assert isinstance(get_executor(by_name[name]), AdvancedExecutor), name


def test_flipped_formats_carry_tailored_harnesses():
    from agent_arena.seed_formats import ALL_FORMATS

    universal = {
        "Code review duel",
        "Debugging race",
        "Injection agent vs hardened agent",
        "RE solve race",
        "Pwn exploit race",
    }
    by_name = {c["name"]: c for c in ALL_FORMATS}
    for name in universal:
        cfg = by_name[name]
        assert cfg.get("universal") is True, name
        assert cfg.get("target_code"), name
        assert "Implement solution.py for this format" not in cfg["target_code"], name
        assert cfg.get("test_code"), name


# --- A2: test() no longer double-counts the step budget ----------------------


def test_test_counts_single_step(tmp_path):
    work = tmp_path / "work"
    (work / "tests").mkdir(parents=True)
    (work / "tests" / "test_target.py").write_text(
        "from solution import is_palindrome\n"
        "assert is_palindrome('racecar') is True\n"
        "print('TEST_PASS')\n",
        encoding="utf-8",
    )
    (work / "solution.py").write_text(
        "def is_palindrome(s):\n    return s == s[::-1]\n", encoding="utf-8"
    )
    sess = ToolSession(work)
    assert sess.steps == 0
    sess.test("")
    # One harness run = one step (previously counted as two).
    assert sess.steps == 1


# --- A3: no self-learning winner when both fighters fail ----------------------


_FAILING_TOOLS = (
    "SKILLS: python-kata-fixer\n"
    "TOOL read path=.agents/skills/python-kata-fixer/SKILL.md\n"
    "TOOL write path=solution.py\n"
    "def is_palindrome(s):\n"
    "    return False\n"
    "END_TOOL\n"
    "TOOL write path=THEORY.md\n"
    "Tried and failed.\n"
    "END_TOOL\n"
    "TOOL test\n"
)


def test_race_both_fail_awards_no_skill_win(monkeypatch):
    import os

    from agent_arena.sandbox.executors.advanced_executor import SKILL_POOL

    before = {s["name"]: s["elo"] for s in SKILL_POOL}
    scores, transport = _run_fake_race(monkeypatch, _FAILING_TOOLS)
    results = _executor_results(transport.rounds)
    assert results, "expected EXECUTOR_RESULT"
    assert all(r.get("passed") is False for r in results)
    # When nobody passes there is no winner, so no skill Elo may increase.
    assert all(s["elo"] <= before[s["name"]] for s in SKILL_POOL)
    os.environ.pop("ARENA_IN_SANDBOX", None)


# --- A4: halt mid-battle still scores fighters that finished ------------------


def test_halt_after_first_fighter_preserves_scores(monkeypatch):
    import os

    from agent_arena.sandbox.client import FakeTransport, InternalClient

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"a": _PASSING_TOOLS, "b": _PASSING_TOOLS}
    transport.judge_result = {
        "scores": {"a": 90.0, "b": 80.0},
        "justifications": {"a": "pass", "b": "pass"},
        "judge_model": "mock",
    }

    def status_check():
        # Cancel as soon as the first fighter has recorded a result.
        for r in transport.rounds:
            if "EXECUTOR_RESULT:" in (r.get("artifact") or ""):
                return "cancelled"
        return ""

    statuses: list[str] = []
    ex = AdvancedExecutor()
    scores = ex.run_battle(
        battle_id="halt-1",
        format_config={**_RACE_FORMAT, "max_tool_turns": 2, "max_tool_steps": 20},
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"player_a": "a", "player_b": "b"},
        client=InternalClient(transport),
        status_check=status_check,
        on_status=statuses.append,
    )
    results = _executor_results(transport.rounds)
    # The first fighter's work is scored, not discarded...
    assert scores, "partial battle should still return judge scores"
    assert any(r.get("role") == "player_a" for r in results)
    # ...but the terminal status stays truthful (cancelled), never completed.
    assert "cancelled" in statuses
    assert "completed" not in statuses
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_harness_tamper_detected_and_restored(monkeypatch):
    import os

    tamper = (
        "TOOL write path=tests/test_target.py\nprint('TEST_PASS')\nEND_TOOL\n"
        "TOOL test\n"
    )
    scores, transport = _run_fake_race(monkeypatch, tamper)
    assert scores
    results = _executor_results(transport.rounds)
    assert results, "expected EXECUTOR_RESULT"
    r = results[0]
    policy = r.get("policy") or {}
    assert policy.get("status") == "invalid"
    assert "harness-tampered" in policy.get("violations", [])
    # The restored canonical harness decides the verdict - a fake TEST_PASS
    # through a tampered harness can never become the recorded outcome.
    assert r.get("passed") is False
    assert r.get("outcome") == "TEST_FAIL"
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_parse_tool_calls_missing_end_tool():
    calls = parse_tool_calls("TOOL write path=solution.py\nprint('hi')\nTOOL ls")
    assert calls[0]["tool"] == "write"
    assert "missing END_TOOL" in (calls[0].get("error") or "")
    assert all(c.get("tool") != "ls" for c in calls)


_PASSING_NO_SKILL = (
    "TOOL write path=solution.py\n"
    "def is_palindrome(s: str) -> bool:\n"
    "    n = ''.join(c.lower() for c in s if c.isalnum())\n"
    "    return n == n[::-1]\n"
    "END_TOOL\n"
    "TOOL write path=THEORY.md\n"
    "Skipped skills.\n"
    "END_TOOL\n"
    "TOOL test\n"
)


def test_harness_pass_without_skill_read_still_passes(monkeypatch):
    import os

    scores, transport = _run_fake_race(monkeypatch, _PASSING_NO_SKILL)
    results = _executor_results(transport.rounds)
    assert scores["a"] == 90.0
    assert results, "expected EXECUTOR_RESULT"
    assert all(r.get("passed") is True for r in results)
    assert all(r.get("outcome") == "TEST_PASS" for r in results)
    assert all(r.get("skill_read_ok") is False for r in results)
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_fetch_url_blocked_ssrf():
    from agent_arena.sandbox.executors.advanced_executor import _fetch_url_blocked

    assert _fetch_url_blocked("http://127.0.0.1/")
    assert _fetch_url_blocked("http://localhost/secret")
    assert _fetch_url_blocked("http://169.254.169.254/latest/meta-data")
    assert _fetch_url_blocked("http://10.0.0.1/")
    assert _fetch_url_blocked("file:///etc/passwd")
    assert _fetch_url_blocked("ftp://example.com/x")
    assert _fetch_url_blocked("not-a-url")


def test_tool_session_fetch_blocks_loopback(tmp_path):
    sess = ToolSession(tmp_path / "work", allow_network=True)
    out = sess.fetch("http://127.0.0.1/")
    assert "ERROR" in out
    assert "blocked" in out.lower()


def test_fetch_obeys_allow_network_before_any_request(tmp_path, monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise AssertionError(
            "fetch must not open a connection when network is disabled"
        )

    monkeypatch.setattr(httpx, "get", boom)
    from agent_arena.sandbox.executors import advanced_executor as ae

    monkeypatch.setattr(
        ae,
        "_fetch_url_blocked",
        lambda url: (_ for _ in ()).throw(
            AssertionError("SSRF check must not run when network is disabled")
        ),
    )
    sess = ToolSession(tmp_path / "work", allow_network=False)
    out = sess.fetch("https://example.com/public")
    assert out.success is False
    assert out.policy_rejected is True
    assert out.error_type == "policy_rejection"
    assert "network" in out.output.lower()
    assert "blocked" in out.output.lower()


def test_fetch_with_network_enabled_reaches_transport_after_ssrf(tmp_path, monkeypatch):
    import httpx
    from agent_arena.sandbox.executors import advanced_executor as ae

    monkeypatch.setattr(ae, "_fetch_url_blocked", lambda url: None)
    seen: dict[str, object] = {}

    class _Resp:
        is_redirect = False
        status_code = 200
        text = "public-ok"
        headers: dict[str, str] = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["follow"] = kwargs.get("follow_redirects")
        return _Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    sess = ToolSession(tmp_path / "work", allow_network=True)
    out = sess.fetch("https://example.com/page")
    assert seen["url"] == "https://example.com/page"
    assert seen["follow"] is False
    assert out.success is True
    assert "STATUS 200" in out.output
    assert "public-ok" in out.output


def test_fetch_ssrf_when_network_enabled_does_not_call_httpx(tmp_path, monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise AssertionError("SSRF destinations must not reach httpx")

    monkeypatch.setattr(httpx, "get", boom)
    sess = ToolSession(tmp_path / "work", allow_network=True)
    for url in (
        "http://127.0.0.1/",
        "http://localhost/secret",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/",
        "file:///etc/passwd",
    ):
        out = sess.fetch(url)
        assert out.success is False
        assert out.policy_rejected is True
        assert "blocked" in out.output.lower()


def test_read_skill_body_is_policy_rejected_target_and_src_still_work(tmp_path):
    work = tmp_path / "work"
    skill_dir = work / ".agents" / "skills" / "auth-flow-debugger"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("UNIQUE_L3_BODY\n", encoding="utf-8")
    (work / "TARGET.md").write_text("public target\n", encoding="utf-8")
    src = work / "src"
    src.mkdir()
    (src / "app.py").write_text("print('ok')\n", encoding="utf-8")
    sess = ToolSession(work, allow_network=False)

    blocked = sess.read(".agents/skills/auth-flow-debugger/SKILL.md")
    assert blocked.success is False
    assert blocked.policy_rejected is True
    assert "UNIQUE_L3_BODY" not in blocked.output
    assert "use_skill" in blocked.output
    assert sess.skill_reads == set()

    target = sess.read("TARGET.md")
    src_file = sess.read("src/app.py")
    assert target.success is True
    assert target.output == "public target\n"
    assert src_file.success is True
    assert "print('ok')" in src_file.output

    loaded = sess.use_skill("auth-flow-debugger")
    assert loaded.success is True
    assert loaded.output == "UNIQUE_L3_BODY\n"
    assert sess.skill_reads == {"auth-flow-debugger"}


def test_fighters_run_in_parallel(monkeypatch):
    import os
    import threading
    import time

    from agent_arena.sandbox.client import FakeTransport, InternalClient

    overlap = threading.Event()
    started: dict[str, float] = {}

    class Slow(FakeTransport):
        def post(self, path, json):
            if path == "/internal/model":
                mid = str(json.get("model_id") or "")
                started[mid] = time.time()
                if len(started) >= 2:
                    overlap.set()
                overlap.wait(2.0)
            return super().post(path, json)

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = Slow()
    transport.model_replies = {"a": _PASSING_TOOLS, "b": _PASSING_TOOLS}
    transport.judge_result = {
        "scores": {"a": 90.0, "b": 80.0},
        "justifications": {"a": "pass", "b": "pass"},
        "judge_model": "mock",
    }
    t0 = time.time()
    scores = AdvancedExecutor().run_battle(
        battle_id="par-1",
        format_config={**_RACE_FORMAT, "max_tool_turns": 2, "max_tool_steps": 20},
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"player_a": "a", "player_b": "b"},
        client=InternalClient(transport),
    )
    elapsed = time.time() - t0
    assert scores["a"] == 90.0
    assert overlap.is_set()
    assert elapsed < 1.5
    os.environ.pop("ARENA_IN_SANDBOX", None)


_CUSTOM_QUICK = {
    "name": "Greeting",
    "engine": "agent_tool_race",
    "custom": True,
    "evaluation_mode": "quick",
    "judge_only": True,
    "roles": ["fighter_1", "fighter_2", "judge"],
    "phases": [{"name": "race", "participants": ["fighter_1", "fighter_2"]}],
    "target_code": "# Write hello in solution.py\n",
    "test_code": "",
    "spec_hash": "abc123",
    "artifacts": {"required": ["solution.py"]},
    "outcome_markers": ["DONE", "JUDGE_ONLY", "STEP_BUDGET_EXCEEDED"],
    "max_tool_turns": 2,
    "max_tool_steps": 20,
    "pick_per_battle": 1,
}

_CUSTOM_VERIFIED_TEST = (
    "from solution import add\n"
    "def main():\n"
    "    assert add(1, 2) == 3\n"
    "    print('TEST_PASS')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)


def test_quick_custom_never_runs_default_harness(monkeypatch):
    import os

    reply = (
        "TOOL write path=solution.py\n"
        "print('hello')\n"
        "END_TOOL\n"
        "TOOL write path=THEORY.md\n"
        "done\n"
        "END_TOOL\n"
        "DONE\n"
    )
    scores, transport = _run_fake_race(
        monkeypatch,
        reply,
        format_overlay=_CUSTOM_QUICK,
        role_to_model={"fighter_1": "a", "fighter_2": "b"},
    )
    assert scores
    results = _executor_results(transport.rounds)
    assert results
    assert all(r.get("outcome") == "JUDGE_ONLY" for r in results)
    assert all(r.get("passed") is None for r in results)
    blob = "\n".join(r.get("artifact", "") for r in transport.rounds)
    assert "is_palindrome" not in blob
    assert all(r.get("spec_hash") == "abc123" for r in results)
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_verified_custom_restores_generated_canonical_tests(monkeypatch):
    import os

    tamper = (
        "TOOL write path=tests/test_target.py\nprint('TEST_PASS')\nEND_TOOL\n"
        "TOOL test\n"
    )
    overlay = {
        "name": "Add",
        "engine": "agent_tool_race",
        "custom": True,
        "evaluation_mode": "verified",
        "judge_only": False,
        "roles": ["fighter_1", "fighter_2", "judge"],
        "phases": [{"name": "race", "participants": ["fighter_1", "fighter_2"]}],
        "target_code": "# implement add\n",
        "test_code": _CUSTOM_VERIFIED_TEST,
        "spec_hash": "def456",
        "artifacts": {"required": ["solution.py"]},
        "outcome_markers": ["DONE", "TEST_PASS", "TEST_FAIL", "STEP_BUDGET_EXCEEDED"],
        "starter_files": {"solution.py": "def add(a, b):\n    return 0\n"},
        "max_tool_turns": 2,
        "max_tool_steps": 20,
        "pick_per_battle": 1,
    }
    scores, transport = _run_fake_race(
        monkeypatch,
        tamper,
        format_overlay=overlay,
        role_to_model={"fighter_1": "a", "fighter_2": "b"},
    )
    assert scores
    results = _executor_results(transport.rounds)
    assert results
    r = results[0]
    assert r.get("passed") is False
    assert r.get("outcome") == "TEST_FAIL"
    assert (r.get("policy") or {}).get("status") == "invalid"
    blob = "\n".join(x.get("artifact", "") for x in transport.rounds)
    assert "is_palindrome" not in blob
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_dynamic_fighter_roles_are_isolated(monkeypatch):
    import os

    reply = "TOOL write path=solution.py\nprint('hello')\nEND_TOOL\nDONE\n"
    scores, transport = _run_fake_race(
        monkeypatch,
        reply,
        format_overlay=_CUSTOM_QUICK,
        role_to_model={"fighter_1": "a", "fighter_2": "b"},
    )
    starts = [
        r.get("artifact", "")
        for r in transport.rounds
        if r.get("event_type") == "phase_start"
        or "phase_start" in (r.get("artifact") or "")
    ]
    assert any("work_fighter_1" in s for s in starts)
    assert any("work_fighter_2" in s for s in starts)
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_initial_model_prompt_uses_compact_skill_discovery_context(monkeypatch):
    import os

    _, transport = _run_fake_race(
        monkeypatch,
        "DONE",
        max_tool_turns=1,
        max_tool_steps=8,
    )
    model_calls = [
        payload for path, payload in transport.calls if path == "/internal/model"
    ]
    assert model_calls
    messages = model_calls[0]["messages"]
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "SKILLS POOL" not in system
    assert "On turn 1" not in system
    assert "pick 1" not in system
    assert "skills()" in system
    assert 'skills(index="security")' in system
    assert "Skills are optional advisory expertise" in system
    assert "Choose your own strategy" in system
    assert "Discovery Quality" not in system
    assert "Network access is not allowed" in system

    # The target remains a public workspace artifact instead of being duplicated
    # into the bootstrap message.
    assert "TARGET.md" in user
    assert "def is_palindrome(s): return s == s[::-1]" not in user
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_initial_model_prompt_follows_actual_network_policy(monkeypatch):
    import os

    _, transport = _run_fake_race(
        monkeypatch,
        "DONE",
        max_tool_turns=1,
        max_tool_steps=8,
        format_overlay={"environment": {"network": True}},
    )
    model_calls = [
        payload for path, payload in transport.calls if path == "/internal/model"
    ]
    system = model_calls[0]["messages"][0]["content"]
    assert "Network access is available" in system
    assert "Network access is not allowed" not in system
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_cp_skill_body_is_policy_rejected(tmp_path):
    work = tmp_path / "work"
    skill_dir = work / ".agents" / "skills" / "auth-flow-debugger"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("BODY\n", encoding="utf-8")
    sess = ToolSession(work)

    result = sess.cp(
        ".agents/skills/auth-flow-debugger/SKILL.md",
        "leaked.md",
    )
    assert result.success is False
    assert result.policy_rejected is True
    assert "use_skill" in result.output
    assert not (work / "leaked.md").exists()


def test_mv_skill_body_is_policy_rejected(tmp_path):
    work = tmp_path / "work"
    skill_dir = work / ".agents" / "skills" / "auth-flow-debugger"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("BODY\n", encoding="utf-8")
    sess = ToolSession(work)

    result = sess.mv(
        ".agents/skills/auth-flow-debugger/SKILL.md",
        "relocated.md",
    )
    assert result.success is False
    assert result.policy_rejected is True
    assert "use_skill" in result.output
    # Original must still be in place (move was rejected)
    assert (skill_dir / "SKILL.md").exists()
    assert not (work / "relocated.md").exists()


def test_use_skill_does_not_persist_body_to_workdir(tmp_path):
    """When skill is not already in workdir, use_skill reads from repo without persisting."""
    work = tmp_path / "work"
    sess = ToolSession(work)

    loaded = sess.use_skill("python-kata-fixer", count_step=False)
    assert loaded.success is True
    assert len(loaded.output) > 0

    body_file = work / ".agents" / "skills" / "python-kata-fixer" / "SKILL.md"
    assert not body_file.exists(), "use_skill must not persist body to workdir"


def test_use_skill_still_works_with_repeated_loads(tmp_path):
    work = tmp_path / "work"
    sess = ToolSession(work)

    first = sess.use_skill("python-kata-fixer", count_step=False)
    second = sess.use_skill("python-kata-fixer", count_step=False)

    assert first.success is True
    assert len(first.output) > 0
    assert second.success is True
    assert "SKILL_ALREADY_LOADED" in second.output
    assert first.output not in second.output
    assert sess.skill_reads == {"python-kata-fixer"}


def test_blocked_read_does_not_mutate_skill_reads(tmp_path):
    work = tmp_path / "work"
    skill_dir = work / ".agents" / "skills" / "secure-code-execution"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("PRIVATE\n", encoding="utf-8")
    sess = ToolSession(work)

    blocked = sess.read(
        ".agents/skills/secure-code-execution/SKILL.md", count_step=False
    )
    assert blocked.success is False
    assert blocked.policy_rejected is True
    assert "PRIVATE" not in blocked.output
    assert sess.skill_reads == set()


def test_empty_test_with_no_harness_returns_no_harness_error(tmp_path):
    work = tmp_path / "work"
    sess = ToolSession(work)

    result = sess.test("", count_step=False)
    assert result.success is False
    assert result.error_type == "no_harness"
    assert "no test harness" in result.output.lower()
    assert "run needs path" not in result.output


def test_test_cmd_still_works(tmp_path):
    work = tmp_path / "work"
    sess = ToolSession(work, test_cmd="echo 'TEST_PASS'")

    result = sess.test("", count_step=False)
    assert result.success is True
    assert "TEST_PASS" in result.output


def test_harness_fallback_still_works(tmp_path):
    work = tmp_path / "work"
    test_dir = work / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "test_target.py").write_text("print('TEST_PASS')\n", encoding="utf-8")
    sess = ToolSession(work)

    result = sess.test("", count_step=False)
    assert result.success is True
    assert "TEST_PASS" in result.output


def test_model_hang_fails_no_first_token_not_provider_error(monkeypatch):
    import os

    from agent_arena.first_token import FAILURE_REASON
    from agent_arena.sandbox.client import FakeTransport, InternalClient

    class HangBoth(FakeTransport):
        def __init__(self):
            super().__init__()
            self.model_timeouts = []

        def post(self, path, json, timeout=None):
            if path == "/internal/model":
                self.model_timeouts.append(timeout)
                raise TimeoutError("model HTTP hung")
            return super().post(path, json, timeout=timeout)

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    monkeypatch.setenv("ARENA_FIRST_TOKEN_SECONDS", "15")
    transport = HangBoth()
    statuses: list[str] = []
    reasons: list[str | None] = []

    def on_status(status, reason=None):
        statuses.append(status)
        reasons.append(reason)

    scores = AdvancedExecutor().run_battle(
        battle_id="silent-hang",
        format_config={**_RACE_FORMAT, "max_tool_turns": 2, "max_tool_steps": 20},
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=600,
        role_to_model={"player_a": "a", "player_b": "b"},
        client=InternalClient(transport),
        on_status=on_status,
    )
    assert scores == {}
    assert "failed" in statuses
    assert FAILURE_REASON in reasons
    assert transport.model_timeouts
    assert all(
        timeout is not None and timeout <= 15 for timeout in transport.model_timeouts
    )
    actions = []
    for row in transport.rounds:
        if row.get("event_type") != "action_log":
            continue
        try:
            actions.append(json.loads(row.get("artifact") or "{}").get("action"))
        except json.JSONDecodeError:
            continue
    assert "model" not in actions
    os.environ.pop("ARENA_IN_SANDBOX", None)
