"""Tests for extract_python_source and build_and_break code extraction."""
from __future__ import annotations

import ast

from agent_arena.sandbox.client import FakeTransport, InternalClient
from agent_arena.sandbox.executors._harness import extract_python_source
from agent_arena.sandbox.executors.build_and_break import BuildAndBreakExecutor, WIN_MARKER


def test_extract_prose_then_python_fence():
    raw = (
        "Let me think about a sandbox — here is the code:\n\n"
        "```python\n"
        "print('SANDBOX_READY')\n"
        "```\n"
    )
    code = extract_python_source(raw)
    assert code is not None
    assert "SANDBOX_READY" in code
    ast.parse(code)


def test_extract_refusal_prose_only():
    raw = (
        "I can't provide code intended to escape the sandbox, "
        "access secrets outside the work directory, or bypass isolation."
    )
    assert extract_python_source(raw) is None


def test_extract_reply_starts_with_fence():
    raw = "```python\nimport sys\nprint('ok')\n```"
    code = extract_python_source(raw)
    assert code == "import sys\nprint('ok')"
    ast.parse(code)


def test_extract_truncated_incomplete_fence():
    raw = (
        "Here is a sandbox:\n\n"
        "```python\n"
        "def main():\n"
        "    try:\n"
        "        req = json.loads(line)\n"
        "    except Exception as e:\n"
        "        resp =\n"
    )
    assert extract_python_source(raw) is None


def test_extract_prefers_last_valid_fence():
    raw = (
        "```python\nthis is not code —\n```\n"
        "```python\nx = 1\nprint(x)\n```\n"
    )
    code = extract_python_source(raw)
    assert code is not None
    assert "x = 1" in code
    ast.parse(code)


def test_build_retries_then_uses_valid_code():
    transport = FakeTransport()
    transport.model_replies = {
        "builder": [
            "Let me think — not code yet.",
            "```python\nprint('SANDBOX_READY')\n```",
        ],
    }
    client = InternalClient(transport)
    ex = BuildAndBreakExecutor()
    arts = ex.run_phase(
        client=client,
        battle_id="b-extract",
        phase={"name": "build", "participants": ["builder"]},
        role_to_model={"builder": "builder"},
        history=[],
        format_config={"exec_timeout_seconds": 10},
        round_visibility="open",
    )
    assert len(arts) == 1
    art = arts[0]["artifact"]
    assert "extract_ok=True" in art
    assert "sandbox_ready=True" in art
    assert "print('SANDBOX_READY')" in art
    assert len(transport.calls) >= 2


def test_escape_refusal_sets_extract_ok_false():
    transport = FakeTransport()
    transport.model_replies = {
        "breaker": (
            "I can’t provide code intended to escape the sandbox, "
            "access secrets outside the work directory, or bypass isolation."
        ),
    }
    client = InternalClient(transport)
    ex = BuildAndBreakExecutor()
    arts = ex.run_phase(
        client=client,
        battle_id="b-escape",
        phase={"name": "break", "participants": ["breaker"]},
        role_to_model={"breaker": "breaker"},
        history=[{"artifact": "BUILD_CODE:\nprint('SANDBOX_READY')\n"}],
        format_config={"exec_timeout_seconds": 10},
        round_visibility="open",
    )
    assert len(arts) == 1
    art = arts[0]["artifact"]
    assert "extract_ok=False" in art
    assert "escaped=False" in art
    assert WIN_MARKER not in art.split("---STDOUT---")[1].split("---STDERR---")[0]
    assert arts[0].get("escaped") is False


def test_build_and_break_shares_workspace_across_phases():
    import json

    marker = "LIVE_SANDBOX_TOKEN_QQZ"
    transport = FakeTransport()
    transport.model_replies = {
        "builder": (
            "```python\n"
            f"# {marker}\n"
            "print('SANDBOX_READY')\n"
            "```\n"
        ),
        "breaker": f"```python\nprint('{WIN_MARKER}')\n```\n",
    }
    transport.judge_result = {
        "scores": {"builder": 50.0, "breaker": 50.0},
        "justifications": {"builder": "ok", "breaker": "ok"},
        "judge_model": "mock",
    }
    client = InternalClient(transport)
    ex = BuildAndBreakExecutor()
    scores = ex.run_battle(
        battle_id="bb-share",
        format_config={
            "name": "Build and break",
            "engine": "build_and_break",
            "roles": ["builder", "breaker", "judge"],
            "phases": [
                {"name": "build", "participants": ["builder"]},
                {"name": "break", "participants": ["breaker"]},
            ],
            "exec_timeout_seconds": 10,
            "judge_rubric": "score",
        },
        model_ids=["builder", "breaker"],
        round_visibility="open",
        timeout_seconds=30,
        role_to_model={"builder": "builder", "breaker": "breaker"},
        client=client,
    )
    assert scores["builder"] == 50.0
    breaker_msgs = [
        body.get("messages")
        for path, body in transport.calls
        if path == "/internal/model" and body.get("model_id") == "breaker"
    ]
    assert marker in json.dumps(breaker_msgs)
