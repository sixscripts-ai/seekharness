from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest

from agent_arena.sandbox.executors.advanced_executor import (
    AdvancedExecutor,
    ToolSession,
    _strip_secret_env,
    parse_tool_calls,
)


def test_child_environment_removes_database_credentials():
    env = {
        "DATABASE_URL": "postgresql://user:password@db.example/arena",
        "BATTLE_RO_DATABASE_URL": "postgresql://readonly:password@db.example/arena",
        "APPWRITE_API_KEY": "appwrite-secret",
        "APPWRITE_ENDPOINT": "https://sfo.cloud.appwrite.io/v1",
    }

    safe = _strip_secret_env(env)

    assert "DATABASE_URL" not in safe
    assert "BATTLE_RO_DATABASE_URL" not in safe
    assert "APPWRITE_API_KEY" not in safe
    assert safe["APPWRITE_ENDPOINT"] == env["APPWRITE_ENDPOINT"]


def test_background_process_receives_sanitized_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_BACKGROUND_SECRET", "background-secret")
    session = ToolSession(tmp_path / "work")
    try:
        started = session.bg(
            "env-check",
            "printf '%s' \"${ARENA_BACKGROUND_SECRET-unset}\"; sleep 0.2",
        )
        assert started.success is True

        output = ""
        for _ in range(50):
            log_result = session.logs("env-check")
            output = log_result.output
            if output and output != "(no logs yet)":
                break
            time.sleep(0.02)

        assert output == "unset"
    finally:
        session.close()


def test_tool_session_context_manager_reaps_background_process(tmp_path):
    with ToolSession(tmp_path / "work") as session:
        started = session.bg("sleeper", "sleep 30")
        assert started.success is True
        managed = session.procs._procs["sleeper"]
        assert managed.alive()

    assert managed.proc.poll() is not None


def test_timeout_drains_and_reaps_process(tmp_path, monkeypatch):
    from agent_arena.sandbox.executors import advanced_executor as module

    real_popen = subprocess.Popen
    observed: dict[str, object] = {}

    class TrackingPopen(real_popen):
        def __init__(self, *args, **kwargs):
            self.communicate_calls = 0
            super().__init__(*args, **kwargs)
            observed["process"] = self

        def communicate(self, *args, **kwargs):
            self.communicate_calls += 1
            return super().communicate(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", TrackingPopen)
    session = ToolSession(tmp_path / "work", tool_timeout=1)
    result = session.run(inline="while True: pass")

    process = observed["process"]
    assert result.timed_out is True
    assert process.poll() is not None
    assert process.communicate_calls >= 2


def test_http_request_rejects_disabled_network_before_transport(tmp_path, monkeypatch):
    import httpx

    def fail_transport(*args, **kwargs):
        raise AssertionError("disabled network must not reach httpx")

    monkeypatch.setattr(httpx, "Client", fail_transport)
    session = ToolSession(tmp_path / "work", allow_network=False)

    result = session.http_request("GET", "https://example.com")

    assert result.success is False
    assert result.policy_rejected is True
    assert result.error_type == "policy_rejection"


def test_http_request_allows_explicit_local_origin_when_network_is_disabled(
    tmp_path, monkeypatch
):
    import httpx

    class Response:
        status_code = 200
        reason_phrase = "OK"
        text = "preview-ok"
        is_redirect = False

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, **kwargs):
            return Response()

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: Client())
    session = ToolSession(
        tmp_path / "work",
        allow_network=False,
        allowed_origins=["http://localhost:8080"],
    )

    result = session.http_request("GET", "http://localhost:8080/api/health")

    assert result.success is True
    assert "preview-ok" in result.output


def test_shell_fetch_is_blocked_when_network_is_disabled_even_for_local_origin(
    tmp_path, monkeypatch
):
    from agent_arena.sandbox.executors.tool_runtime import ProcessRunner

    def fail_process_start(*args, **kwargs):
        raise AssertionError("disabled-network curl must not reach a child process")

    monkeypatch.setattr(ProcessRunner, "start", fail_process_start)
    session = ToolSession(
        tmp_path / "work",
        allow_network=False,
        allowed_origins=["http://localhost:8080"],
    )

    result = session.shell("curl http://localhost:8080/health")

    assert result.success is False
    assert result.policy_rejected is True


def test_public_origin_cannot_bypass_disabled_network(tmp_path, monkeypatch):
    import httpx

    def fail_transport(*args, **kwargs):
        raise AssertionError("public origins must not bypass network policy")

    monkeypatch.setattr(httpx, "Client", fail_transport)
    session = ToolSession(
        tmp_path / "work",
        allow_network=False,
        allowed_origins=["https://example.com"],
    )

    result = session.http_request("GET", "https://example.com/health")

    assert result.success is False
    assert result.policy_rejected is True


def test_install_package_manager_is_blocked_without_network(tmp_path, monkeypatch):
    from agent_arena.sandbox.executors.tool_runtime import ProcessRunner

    def fail_transport(*args, **kwargs):
        raise AssertionError("package installation must not reach a child process")

    monkeypatch.setattr(ProcessRunner, "start", fail_transport)
    session = ToolSession(tmp_path / "work", allow_network=False)

    result = session.install("python3 -m pip install requests")

    assert result.success is False
    assert result.policy_rejected is True


def test_http_request_rejects_private_destination_when_network_is_enabled(
    tmp_path, monkeypatch
):
    import httpx

    def fail_transport(*args, **kwargs):
        raise AssertionError("private destinations must not reach httpx")

    monkeypatch.setattr(httpx, "Client", fail_transport)
    session = ToolSession(tmp_path / "work", allow_network=True)

    result = session.http_request("GET", "http://127.0.0.1:8080")

    assert result.success is False
    assert result.policy_rejected is True


def test_browser_navigation_rejects_disabled_network_before_transport(
    tmp_path, monkeypatch
):
    import httpx

    def fail_transport(*args, **kwargs):
        raise AssertionError("disabled network must not reach browser fallback")

    monkeypatch.setattr(httpx, "Client", fail_transport)
    session = ToolSession(tmp_path / "work", allow_network=False)
    monkeypatch.setattr(session, "_ensure_page", lambda: None)

    result = session.playwright_navigate("http://127.0.0.1:8080")

    assert result.success is False
    assert result.policy_rejected is True
    assert result.error_type == "policy_rejection"


def test_fighter_grammar_lists_every_registered_tool():
    from agent_arena.fighter_context import fighter_tool_grammar
    from agent_arena.tool_protocol import REGISTRY

    grammar = fighter_tool_grammar()

    for name in sorted(REGISTRY.all_names() - {"done"}):
        assert f"TOOL {name}" in grammar, name


def test_advanced_executor_does_not_own_a_second_tool_parser():
    from agent_arena.sandbox.executors import advanced_executor as module

    assert not hasattr(module, "_parse_json_tools")
    assert not hasattr(module, "_normalize_json_call")


def test_artifact_store_upserts_one_result_per_identity():
    from agent_arena.sandbox.executors.battle_runtime import ArtifactStore

    store = ArtifactStore()
    first = {"phase": "build", "role": "builder", "model_id": "m", "passed": False}
    corrected = {"phase": "build", "role": "builder", "model_id": "m", "passed": True}

    store.upsert(first)
    store.upsert(corrected)

    assert store.values() == [corrected]


def test_advanced_run_config_normalizes_format_once():
    from agent_arena.sandbox.executors.battle_runtime import AdvancedRunConfig

    config = AdvancedRunConfig.from_format(
        {
            "limits": {
                "max_tool_turns": 99,
                "max_tool_steps": 0,
                "tool_timeout": 7,
                "race_max_tokens": 128,
            },
            "context_mode": " ADAPTIVE ",
            "environment": {
                "network": True,
                "allowed_origins": ["http://localhost:8080"],
            },
            "allowed_origins": ["http://localhost:8080", "http://localhost:9090"],
        }
    )

    assert config.max_turns == 20
    assert config.max_steps == 1
    assert config.tool_timeout == 7
    assert config.race_max_tokens == 128
    assert config.context_mode == "adaptive"
    assert config.allow_network is True
    assert config.allowed_origins == (
        "http://localhost:8080",
        "http://localhost:9090",
    )


def test_event_sink_allocates_monotonic_sequences_under_concurrency():
    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.battle_runtime import EventSink

    transport = FakeTransport()
    sink = EventSink(InternalClient(transport), "event-battle")

    def emit_events():
        for _ in range(10):
            sink.emit("race", "model", "event", event_type="action_log")

    threads = [threading.Thread(target=emit_events) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    sequences = [row["sequence"] for row in transport.rounds]
    assert sequences == list(range(1, 41))


def test_run_phase_requires_the_advanced_sandbox_gate(monkeypatch):
    monkeypatch.delenv("ARENA_IN_SANDBOX", raising=False)

    with pytest.raises(RuntimeError, match="sandbox"):
        AdvancedExecutor().run_phase(
            client=None,
            battle_id="phase-gate",
            phase={"name": "race", "participants": ["player_a"]},
            role_to_model={"player_a": "model-a"},
            history=[],
            format_config={"name": "Tool-using coding race"},
            round_visibility="isolated",
        )


def test_run_phase_executes_a_fighter_and_returns_result(monkeypatch):
    from agent_arena.sandbox.client import FakeTransport, InternalClient

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {
        "model-a": (
            "TOOL write path=solution.py\n"
            "def is_palindrome(s):\n"
            "    return s == s[::-1]\n"
            "END_TOOL\n"
            "TOOL test\n"
        )
    }
    transport.judge_result = {"scores": {"model-a": 80.0}}

    history: list[dict] = []
    results = AdvancedExecutor().run_phase(
        client=InternalClient(transport),
        battle_id="phase-run",
        phase={"name": "race", "participants": ["player_a"]},
        role_to_model={"player_a": "model-a"},
        history=history,
        format_config={
            "name": "Tool-using coding race",
            "roles": ["player_a", "judge"],
            "target_code": "def is_palindrome(s): return s == s[::-1]\n",
            "max_tool_turns": 2,
            "max_tool_steps": 10,
        },
        round_visibility="isolated",
    )

    assert results
    assert results[0]["role"] == "player_a"
    assert "outcome" in results[0]
    assert any(item.get("role") == "player_a" for item in history)


def test_same_model_can_produce_one_result_per_role(monkeypatch):
    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.battle_runtime import PhaseRunner

    def run_sequential(self, request, *, callback_kwargs=None):
        kwargs = dict(callback_kwargs or {})
        return [
            self.execute_fighter(index, role, **kwargs)
            for index, role in enumerate(request.participants)
        ]

    monkeypatch.setattr(PhaseRunner, "run", run_sequential)

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    transport = FakeTransport()
    transport.model_replies = {"shared": "DONE"}
    transport.judge_result = {"scores": {"shared": 80.0}}

    AdvancedExecutor().run_battle(
        battle_id="same-model-roles",
        format_config={
            "name": "same model role identity",
            "evaluation_mode": "quick",
            "roles": ["role_a", "role_b", "judge"],
            "phases": [{"name": "race", "participants": ["role_a", "role_b"]}],
            "max_tool_turns": 1,
        },
        model_ids=["shared", "shared"],
        round_visibility="isolated",
        timeout_seconds=30,
        role_to_model={"role_a": "shared", "role_b": "shared"},
        client=InternalClient(transport),
    )

    result_rows = []
    for row in transport.rounds:
        if "EXECUTOR_RESULT:" not in (row.get("artifact") or ""):
            continue
        result_rows.append(json.loads(row["artifact"].split("EXECUTOR_RESULT:", 1)[1]))
    identities = [
        (row.get("phase"), row.get("role"), row.get("model_id"))
        for row in result_rows
    ]
    assert set(identities) == {
        ("race", "role_a", "shared"),
        ("race", "role_b", "shared"),
    }
