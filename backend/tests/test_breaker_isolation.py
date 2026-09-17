"""The Breaker process never shares the trusted evaluator environment."""

from __future__ import annotations

import json
from pathlib import Path

import agent_arena.breaker_isolation as isolation
from agent_arena.breaker_isolation import BreakerExecution, run_breaker_isolated


def test_local_runner_uses_a_minimal_environment(monkeypatch):
    monkeypatch.setenv("ARENA_BREAKER_EXECUTION_MODE", "local")
    monkeypatch.setattr(isolation, "PRIVATE_EVALUATOR_MOUNT", Path("/path/that/is/not-mounted"))

    result = run_breaker_isolated(
        "python3 exploit.py",
        {
            "exploit.py": (
                "import json, os\n"
                "print(json.dumps({\"evaluator_dir\": os.getenv(\"ARENA_EVALUATOR_DIR\"), "
                "\"private_mount\": os.path.isdir(\"/opt/arena-evaluators\")}))\n"
            )
        },
        timeout_seconds=5,
        allow_network=False,
        runtime="python311",
    )

    assert result == BreakerExecution(
        started=True,
        completed=True,
        return_code=0,
        stdout=result.stdout,
        stderr="",
    )
    observation = json.loads(result.stdout)
    assert observation == {"evaluator_dir": None, "private_mount": False}


def test_local_runner_refuses_when_private_mount_is_visible(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_BREAKER_EXECUTION_MODE", "local")
    monkeypatch.setattr(isolation, "PRIVATE_EVALUATOR_MOUNT", tmp_path)

    result = run_breaker_isolated(
        "python3 exploit.py",
        {"exploit.py": "print('should not run')\n"},
        timeout_seconds=5,
        allow_network=False,
        runtime="python311",
    )

    assert result.started is False
    assert result.completed is False
    assert result.error == "breaker_isolation_required_private_mount_visible"


def test_modal_dispatch_is_the_only_production_runner(monkeypatch):
    monkeypatch.setenv("ARENA_BREAKER_EXECUTION_MODE", "modal")
    observed: dict[str, object] = {}

    def fake_modal(command, files, *, timeout_seconds, allow_network, runtime):
        observed.update(
            command=command,
            files=files,
            timeout_seconds=timeout_seconds,
            allow_network=allow_network,
            runtime=runtime,
        )
        return BreakerExecution(error="test-only-modal-stub")

    monkeypatch.setattr(isolation, "_run_modal", fake_modal)
    result = run_breaker_isolated(
        "python3 exploit.py",
        {"exploit.py": "print('ok')\n"},
        timeout_seconds=7,
        allow_network=False,
        runtime="python311",
    )

    assert result.error == "test-only-modal-stub"
    assert observed["command"] == "python3 exploit.py"
    assert observed["runtime"] == "python311"

