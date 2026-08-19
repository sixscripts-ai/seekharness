import json

from agent_arena.sandbox.client import FakeTransport, InternalClient
from agent_arena.sandbox.runner import map_roles, playable_roles, run_battle_loop
from agent_arena.sandbox.executors.build_and_break import WIN_MARKER
from agent_arena.sandbox.executors._harness import run_python
from pathlib import Path
import tempfile


def test_playable_roles_skips_judge():
    assert playable_roles(["builder", "breaker", "judge"]) == ["builder", "breaker"]


def test_map_roles_order_preserving():
    m = map_roles(["builder", "breaker", "judge"], ["m1", "m2"])
    assert m == {"builder": "m1", "breaker": "m2"}


def test_run_battle_loop_direct_duel():
    transport = FakeTransport()
    transport.model_replies = {
        "m-att": "INJECT: ignore previous",
        "m-def": "I refuse the injection",
    }
    transport.judge_result = {
        "scores": {"m-att": 40.0, "m-def": 85.0},
        "justifications": {"m-att": "attack weak", "m-def": "solid"},
        "judge_model": "mock",
    }
    client = InternalClient(transport)
    cfg = {
        "name": "Prompt injection vs hygiene",
        "engine": "direct_duel",
        "roles": ["player_a", "player_b", "judge"],
        "phases": [
            {"name": "duel", "participants": ["player_a", "player_b"], "inputs": []},
            {"name": "judge", "participants": ["judge"], "inputs": ["duel"]},
        ],
        "judge_rubric": "Score 0-100",
        "scoring_weights": {"duel": 1.0},
        "duel_turns": 1,
    }
    statuses = []
    scores = run_battle_loop(
        battle_id="b1",
        format_config=cfg,
        model_ids=["m-att", "m-def"],
        round_visibility="open",
        timeout_seconds=60,
        client=client,
        on_status=statuses.append,
    )
    assert scores["m-def"] == 85.0
    assert "completed" in statuses
    assert any(p == "/internal/judge" for p, _ in transport.calls)
    assert any(p == "/internal/model" for p, _ in transport.calls)
    assert len(transport.rounds) >= 2


def test_run_battle_loop_cancelled():
    transport = FakeTransport()
    client = InternalClient(transport)
    cfg = {
        "name": "x",
        "engine": "scripted",
        "roles": ["a", "b", "judge"],
        "phases": [{"name": "p", "participants": ["a", "b"]}],
        "judge_rubric": "r",
    }
    scores = run_battle_loop(
        battle_id="b2",
        format_config=cfg,
        model_ids=["m1", "m2"],
        client=client,
        status_check=lambda: "cancelled",
        on_status=lambda s: None,
    )
    assert scores == {}


def test_format3_exec_escape_marker():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "escape.py"
        p.write_text(f'print("{WIN_MARKER}")\n', encoding="utf-8")
        out, err, rc = run_python(p, cwd=Path(tmp), timeout=10)
        assert WIN_MARKER in out
        assert rc == 0


def test_scripted_executor_calls_models():
    from agent_arena.sandbox.executors.scripted import ScriptedExecutor

    transport = FakeTransport()
    transport.model_replies["m1"] = "move-a"
    client = InternalClient(transport)
    ex = ScriptedExecutor()
    arts = ex.run_phase(
        client=client,
        battle_id="b",
        phase={"name": "p1", "participants": ["builder", "judge"]},
        role_to_model={"builder": "m1"},
        history=[],
        format_config={"name": "t"},
        round_visibility="isolated",
    )
    assert arts[0]["artifact"] == "move-a"


def test_http_transport_follows_redirects():
    """Sandbox client must follow Modal gateway 303s (previously JSONDecodeError on empty body)."""
    import httpx
    from agent_arena.sandbox.client import HttpTransport

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                303, headers={"location": "http://backend/internal/model"}
            )
        return httpx.Response(200, json={"content": "hi from model"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpTransport("http://backend", "k", timeout=10)
    t.client = client
    out = t.post("/internal/model", {"x": 1})
    assert out == {"content": "hi from model"}
    assert calls["n"] == 2


def test_http_transport_retries_non_json():
    """A 200 with empty body must be retried, not surface as JSONDecodeError."""
    import httpx
    from agent_arena.sandbox.client import HttpTransport

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(200, content=b"")
        return httpx.Response(200, json={"content": "ok"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpTransport("http://backend", "k", timeout=10)
    t.client = client
    out = t.post("/internal/model", {"x": 1})
    assert out == {"content": "ok"}
    assert calls["n"] == 3


def test_judge_weights_merges_criteria_and_phases():
    from agent_arena.sandbox.executors.base import judge_weights

    assert judge_weights({}) is None
    merged = judge_weights(
        {
            "scoring_weights": {"race": 1.0},
            "scoring": {"weights": {"tests": 0.6, "skills": 0.2, "theory": 0.2}},
        }
    )
    assert merged["race"] == 1.0
    assert merged["tests"] == 0.6
    assert merged["skills"] == 0.2
    assert merged["theory"] == 0.2
    # Phase keys win on collision.
    assert judge_weights(
        {
            "scoring_weights": {"tests": 1.0},
            "scoring": {"weights": {"tests": 0.6}},
        }
    )["tests"] == 1.0


def test_finish_sends_merged_weights_to_judge():
    from agent_arena.sandbox.executors.base import Executor

    transport = FakeTransport()
    transport.judge_result = {
        "scores": {"m1": 70.0},
        "justifications": {"m1": "ok"},
        "judge_model": "mock",
    }
    client = InternalClient(transport)
    scores = Executor().finish(
        client=client,
        battle_id="b-w",
        format_config={
            "judge_rubric": "score fairly",
            "scoring_weights": {"race": 1.0},
            "scoring": {"weights": {"tests": 0.6, "skills": 0.3, "theory": 0.1}},
        },
        history=[],
    )
    assert scores["m1"] == 70.0
    judge_calls = [body for path, body in transport.calls if path == "/internal/judge"]
    assert judge_calls
    weights = judge_calls[0]["weights"]
    assert weights["race"] == 1.0
    assert weights["tests"] == 0.6
    assert weights["skills"] == 0.3
    assert weights["theory"] == 0.1
