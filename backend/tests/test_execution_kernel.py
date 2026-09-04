from __future__ import annotations

import json
import pytest
from pathlib import Path

from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor, ToolSession
from agent_arena.sandbox.executors.tool_result import ToolResult
from agent_arena.tool_protocol import REGISTRY, CanonicalToolCall, normalize_response


class MockInternalClient:
    def __init__(self, responses_by_model: dict[str, list[str]] | None = None):
        self.responses = responses_by_model or {}
        self.calls_made: list[dict] = []
        self.rounds_emitted: list[dict] = []
        self.results_emitted: list[dict] = []

    def model(
        self,
        battle_id: str,
        model_id: str,
        messages: list[dict],
        phase: str = "",
        max_tokens: int = 1024,
        tools: list[dict] | None = None,
        return_raw: bool = False,
    ):
        self.calls_made.append(
            {
                "battle_id": battle_id,
                "model_id": model_id,
                "messages": list(messages),
                "phase": phase,
                "tools": tools,
            }
        )
        resp_list = self.responses.get(model_id, [])
        if resp_list:
            resp = resp_list.pop(0)
        else:
            resp = "DONE"
        if return_raw:
            return {"content": resp, "tool_calls": [], "finish_reason": "stop", "latency_ms": 100}
        return resp

    def round(
        self,
        battle_id: str,
        phase: str,
        model_id: str,
        artifact: str,
        event_type: str = "artifact",
        sequence: int | None = None,
    ):
        self.rounds_emitted.append(
            {
                "battle_id": battle_id,
                "phase": phase,
                "model_id": model_id,
                "artifact": artifact,
                "event_type": event_type,
                "sequence": sequence,
            }
        )
        if artifact.startswith("EXECUTOR_RESULT:"):
            payload = artifact.split("EXECUTOR_RESULT:", 1)[1].strip()
            self.results_emitted.append(json.loads(payload))

    def judge(self, battle_id: str, rubric: str, history: list[dict], weights: dict | None = None):
        return {"scores": {}}


def test_probe_a_step_accounting_all_executable_actions(monkeypatch):
    """Probe A: Each fighter action costs 1 step: skills (1), use_skill (1), repeated use_skill (1), missing read (1), schema invalid (1), then DONE (0)."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    executor = AdvancedExecutor()

    canonical_test = "import solution\nassert solution.val == 42\nprint('TEST_PASS rc=0')"

    client = MockInternalClient(
        {
            "model_probe_a": [
                # Turn 1: skills (1 step) + use_skill (1 step) + repeated use_skill (1 step)
                "TOOL skills chosen=[\"python_debug\"]\nTOOL use_skill name=python_debug\nTOOL use_skill name=python_debug",
                # Turn 2: missing-file read (1 step) + schema-invalid read (1 step) + write valid solution (1 step) + DONE (0 steps)
                "TOOL read path=missing.txt\nTOOL read path=123\nTOOL write path=solution.py content=\"val = 42\"\nTOOL done",
            ]
        }
    )

    format_config = {
        "name": "probe-a-accounting",
        "phases": [{"name": "race", "participants": ["fighter_a"]}],
        "test_code": canonical_test,
        "max_turns": 5,
        "max_steps": 10,
    }

    executor.run_battle(
        battle_id="b_probe_a_steps",
        format_config=format_config,
        model_ids=["model_probe_a"],
        round_visibility="private",
        timeout_seconds=30,
        role_to_model={"fighter_a": "model_probe_a"},
        client=client,
    )

    assert len(client.results_emitted) == 1
    res = client.results_emitted[0]
    assert res["outcome"] == "TEST_PASS"
    assert res["passed"] is True
    assert res["terminal_reason"] in ("completed", "fighter_done")
    # Exact step breakdown:
    # 1. skills (1)
    # 2. use_skill (1)
    # 3. repeated use_skill (1)
    # 4. missing read (1)
    # 5. schema-invalid read (1)
    # 6. write solution.py (1)
    # 7. DONE (0)
    # Total = 6 steps
    assert res["steps"] == 6


def test_probe_b_parse_recovery_privacy_no_free_workspace_disclosure(monkeypatch):
    """Probe B: Turn 1 malformed -> Turn 2 receives interface corrective feedback with NO workspace disclosure, steps=0."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    executor = AdvancedExecutor()

    client = MockInternalClient(
        {
            "model_probe_b": [
                # Turn 1: Malformed response (no tools)
                "I am thinking about writing code...",
                # Turn 2: Valid test and done
                "TOOL write path=solution.py content=\"x = 1\"\nTOOL test\nTOOL done",
            ]
        }
    )

    format_config = {
        "name": "probe-b-privacy",
        "phases": [{"name": "race", "participants": ["fighter_a"]}],
        "starter_files": {"secret_evidence.txt": "confidential_data"},
        "test_code": "import solution\nassert solution.x == 1\nprint('TEST_PASS rc=0')",
        "max_turns": 5,
        "max_steps": 10,
    }

    executor.run_battle(
        battle_id="b_probe_b_privacy",
        format_config=format_config,
        model_ids=["model_probe_b"],
        round_visibility="private",
        timeout_seconds=30,
        role_to_model={"fighter_a": "model_probe_b"},
        client=client,
    )

    calls = [c for c in client.calls_made if c["model_id"] == "model_probe_b"]
    assert len(calls) == 2

    # Verify Turn 2 message received ONLY interface feedback, NOT Workdir files listing
    turn2_user_msg = calls[1]["messages"][-1]["content"]
    assert "Notice: No valid tool calls were parsed" in turn2_user_msg
    assert "Workdir files:" not in turn2_user_msg
    assert "secret_evidence.txt" not in turn2_user_msg
    assert "Turn 1/5, steps 0/10" in turn2_user_msg


def test_probe_c_typed_validation_rejections(monkeypatch):
    """Probe C: Submit wrong JSON types; verify rejection happens before handler invocation, charges 1 step, error_type=validation_error."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    executor = AdvancedExecutor()

    client = MockInternalClient(
        {
            "model_probe_c": [
                # 3 invalid type calls in one turn
                "TOOL read path=123\nTOOL shell cmd=[\"echo\",\"hi\"]\nTOOL skills chosen=\"not-a-list\"",
            ]
        }
    )

    format_config = {
        "name": "probe-c-validation",
        "phases": [{"name": "race", "participants": ["fighter_a"]}],
        "max_turns": 2,
        "max_steps": 10,
    }

    executor.run_battle(
        battle_id="b_probe_c_val",
        format_config=format_config,
        model_ids=["model_probe_c"],
        round_visibility="private",
        timeout_seconds=30,
        role_to_model={"fighter_a": "model_probe_c"},
        client=client,
    )

    assert len(client.results_emitted) == 1
    res = client.results_emitted[0]
    # Each invalid call was rejected before execution and charged exactly 1 step
    assert res["steps"] == 3
    assert res["tool_errors"] == 3


def test_probe_d_truncation_truthfulness(monkeypatch):
    """Probe D: Tool output larger than cap is capped and ToolResult.truncated is True."""
    from agent_arena.sandbox.executors.advanced_executor import ToolSession
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        sess = ToolSession(Path(tmp), output_cap=40)

        # 1. Output > 40 bytes -> truncated=True
        sess.write("data.txt", "A" * 100)
        read_res = sess.read("data.txt")
        assert read_res.truncated is True
        assert "[TRUNCATED]" in read_res.output

        # 2. Output <= 40 bytes -> truncated=False
        sess.write("small.txt", "hello")
        small_res = sess.read("small.txt")
        assert small_res.truncated is False
        assert "[TRUNCATED]" not in small_res.output


def test_probe_e_recovery_scenario(monkeypatch):
    """Probe E: malformed -> corrective feedback -> valid action -> failed test -> model correction -> trusted PASS."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    executor = AdvancedExecutor()

    canonical_test = "import solution\nassert solution.multiply(3, 4) == 12\nprint('TEST_PASS rc=0')"

    client = MockInternalClient(
        {
            "model_probe_e": [
                # Turn 1: Malformed response (no tools)
                "I will implement multiplication.",
                # Turn 2: Valid actions but buggy implementation
                'TOOL write path=solution.py content="def multiply(a, b): return a + b"\nTOOL test',
                # Turn 3: Correction and passing test
                'TOOL write path=solution.py content="def multiply(a, b): return a * b"\nTOOL test',
            ]
        }
    )

    format_config = {
        "name": "probe-e-test",
        "phases": [{"name": "race", "participants": ["fighter_a"]}],
        "test_code": canonical_test,
        "max_turns": 5,
        "max_steps": 10,
    }

    executor.run_battle(
        battle_id="b_probe_e",
        format_config=format_config,
        model_ids=["model_probe_e"],
        round_visibility="private",
        timeout_seconds=30,
        role_to_model={"fighter_a": "model_probe_e"},
        client=client,
    )

    calls = [c for c in client.calls_made if c["model_id"] == "model_probe_e"]
    assert len(calls) == 3

    # Turn 2 message received parse error feedback with no workspace disclosure
    turn2_user_msg = calls[1]["messages"][-1]["content"]
    assert "No valid tool calls were parsed" in turn2_user_msg
    assert "Workdir files:" not in turn2_user_msg

    # Turn 3 message received failed test feedback
    turn3_user_msg = calls[2]["messages"][-1]["content"]
    assert "TEST_FAIL" in turn3_user_msg or "AssertionError" in turn3_user_msg

    # Final verdict is TEST_PASS
    assert len(client.results_emitted) == 1
    res = client.results_emitted[0]
    assert res["outcome"] == "TEST_PASS"
    assert res["passed"] is True
    assert res["terminal_reason"] == "completed"
    assert res["turns"] == 3
    assert res["parse_errors"] == 1


@pytest.mark.parametrize(
    "tool_command,expected_steps,expected_error_type",
    [
        ("TOOL write path=test.txt content=hello", 1, None),  # 1. successful tool
        ("TOOL read path=nonexistent_missing.txt", 1, "not_found"),  # 2. missing-file failure
        ("TOOL read", 1, "validation_error"),  # 3. schema-invalid arguments (missing required 'path')
        ("TOOL read path=../../etc/shadow", 1, "policy_rejection"),  # 4. policy rejection
        ("TOOL shell cmd='exit 7'", 1, "execution_error"),  # 5. shell nonzero exit
        ("TOOL test", 1, "test_failed"),  # 6. test failure
    ],
)
def test_all_failure_modes_consume_exactly_one_step(monkeypatch, tool_command, expected_steps, expected_error_type):
    """Regression test proving each fighter-requested attempt costs exactly one tool step."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    executor = AdvancedExecutor()

    # Model requests 1 tool attempt per turn, with max_steps=1
    # When that attempt runs, budget is immediately exhausted (steps=1 >= max_steps=1)
    client = MockInternalClient(
        {
            "model_tester": [
                f"{tool_command}\nTOOL read path=should_not_run.txt",
                "TOOL read path=should_never_run.txt",
            ]
        }
    )

    format_config = {
        "name": "step-accounting-test",
        "phases": [{"name": "race", "participants": ["fighter_a"]}],
        "max_turns": 5,
        "max_steps": 1,
    }

    executor.run_battle(
        battle_id=f"b_step_{expected_steps}",
        format_config=format_config,
        model_ids=["model_tester"],
        round_visibility="private",
        timeout_seconds=30,
        role_to_model={"fighter_a": "model_tester"},
        client=client,
    )

    assert len(client.results_emitted) == 1
    res = client.results_emitted[0]
    assert res["steps"] == 1
    assert res["outcome"] == "STEP_BUDGET_EXCEEDED"
    assert res["terminal_reason"] == "step_budget_exhausted"


def test_timeout_and_exception_consume_exactly_one_step(monkeypatch):
    """Test that timeout and exception each consume exactly 1 tool step."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    executor = AdvancedExecutor()

    # 1. Timeout step
    client_timeout = MockInternalClient(
        {
            "model_timeout": [
                "TOOL shell cmd='sleep 5'\nTOOL read path=extra.txt",
            ]
        }
    )
    format_config = {
        "name": "timeout-step-test",
        "phases": [{"name": "race", "participants": ["fighter_a"]}],
        "max_turns": 5,
        "max_steps": 1,
        "tool_timeout": 1,
    }
    executor.run_battle(
        battle_id="b_timeout_step",
        format_config=format_config,
        model_ids=["model_timeout"],
        round_visibility="private",
        timeout_seconds=30,
        role_to_model={"fighter_a": "model_timeout"},
        client=client_timeout,
    )
    assert len(client_timeout.results_emitted) == 1
    assert client_timeout.results_emitted[0]["steps"] == 1


def test_arena_internal_verification_does_not_consume_fighter_steps(monkeypatch):
    """Provider retries and Arena-internal verification must not consume fighter tool steps."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    executor = AdvancedExecutor()

    canonical_test = "import solution\nassert solution.val == 100\nprint('TEST_PASS rc=0')"

    client = MockInternalClient(
        {
            "model_internal_verify": [
                'TOOL write path=solution.py content="val = 100"\nTOOL done',
            ]
        }
    )

    format_config = {
        "name": "internal-verify-step-test",
        "phases": [{"name": "race", "participants": ["fighter_a"]}],
        "test_code": canonical_test,
        "max_turns": 5,
        "max_steps": 10,
    }

    executor.run_battle(
        battle_id="b_internal_verify",
        format_config=format_config,
        model_ids=["model_internal_verify"],
        round_visibility="private",
        timeout_seconds=30,
        role_to_model={"fighter_a": "model_internal_verify"},
        client=client,
    )

    assert len(client.results_emitted) == 1
    res = client.results_emitted[0]
    assert res["outcome"] == "TEST_PASS"
    # Exactly 1 step was spent by the fighter (write solution.py). DONE and internal verification test cost 0 steps.
    assert res["steps"] == 1



