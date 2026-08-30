from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from agent_arena.sandbox.executors.tool_result import ToolResult
from agent_arena.sandbox.executors.advanced_executor import ToolSession


def test_tool_result_dataclass():
    res = ToolResult(
        tool="write",
        success=True,
        output="WROTE main.py 50 bytes",
        exit_code=0,
        duration_ms=12,
        mutated=True,
        step_charged=True,
    )
    assert res.tool == "write"
    assert res.success is True
    assert res.exit_code == 0
    assert res.duration_ms == 12
    assert str(res) == "WROTE main.py 50 bytes"
    assert res.error is None
    assert res.mutated is True
    assert res.step_charged is True

    d = res.to_dict()
    assert d["tool"] == "write"
    assert d["success"] is True
    assert d["exit_code"] == 0
    assert d["output"] == "WROTE main.py 50 bytes"


def test_tool_session_rc_zero_success():
    with tempfile.TemporaryDirectory() as tmp:
        sess = ToolSession(Path(tmp))
        res = sess.shell("echo 'success'")
        assert res.success is True
        assert res.exit_code == 0
        assert res.error_type is None
        assert res.step_charged is True
        assert sess.steps == 1


def test_tool_session_nonzero_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        sess = ToolSession(Path(tmp))
        res = sess.shell("exit 42")
        assert res.success is False
        assert res.exit_code == 42
        assert res.error_type == "execution_error"
        assert res.step_charged is True
        assert sess.steps == 1


def test_tool_session_test_failure_structured():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        tests_dir = work / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_target.py").write_text("assert False, 'intentional fail'")
        sess = ToolSession(work)
        res = sess.test("")
        assert res.success is False
        assert res.error_type == "test_failed"
        assert res.exit_code != 0
        assert res.step_charged is True
        assert sess.steps == 1


def test_tool_session_timeout_structured():
    with tempfile.TemporaryDirectory() as tmp:
        sess = ToolSession(Path(tmp), tool_timeout=1)
        res = sess.shell("sleep 5")
        assert res.success is False
        assert res.timed_out is True
        assert res.error_type == "timeout"
        assert res.exit_code == 124
        assert res.step_charged is True
        assert sess.steps == 1


def test_tool_session_policy_rejection_structured():
    with tempfile.TemporaryDirectory() as tmp:
        sess = ToolSession(Path(tmp))
        # Path escape policy rejection
        res = sess.read("../../etc/passwd")
        assert res.success is False
        assert res.policy_rejected is True
        assert res.error_type == "policy_rejection"
        assert res.exit_code == 1
        assert res.step_charged is True
        assert sess.steps == 1


def test_tool_session_missing_file_accounting():
    with tempfile.TemporaryDirectory() as tmp:
        sess = ToolSession(Path(tmp))
        res = sess.read("non_existent_file.txt")
        assert res.success is False
        assert res.error_type == "not_found"
        assert res.exit_code == 1
        assert res.step_charged is True
        assert sess.steps == 1


def test_tool_session_internal_verification_does_not_consume_steps():
    with tempfile.TemporaryDirectory() as tmp:
        sess = ToolSession(Path(tmp))
        sess.write("app.py", "x = 1")
        assert sess.steps == 1

        # Internal listing and verification passing count_step=False
        ls_res = sess.ls(count_step=False)
        assert ls_res.step_charged is False
        assert sess.steps == 1

        test_res = sess.test("", count_step=False)
        assert test_res.step_charged is False
        assert sess.steps == 1


def test_tool_session_truncation_truthfulness():
    """Gap 4: uncapped output -> truncated=False, capped output -> truncated=True."""
    with tempfile.TemporaryDirectory() as tmp:
        # Output cap set to 50 bytes
        sess = ToolSession(Path(tmp), output_cap=50)

        # 1. Uncapped write and read
        sess.write("short.txt", "short content")
        read_short = sess.read("short.txt")
        assert read_short.truncated is False
        assert "[TRUNCATED]" not in read_short.output

        # 2. Capped read
        long_content = "x" * 200
        sess.write("long.txt", long_content)
        read_long = sess.read("long.txt")
        assert read_long.truncated is True
        assert "[TRUNCATED]" in read_long.output

        # 3. Capped shell command
        shell_res = sess.shell("python3 -c \"print('a' * 300)\"")
        assert shell_res.truncated is True
        assert "[TRUNCATED]" in shell_res.output

        # 4. Uncapped shell command
        shell_short = sess.shell("echo 'hello'")
        assert shell_short.truncated is False


def test_validation_failure_produces_structured_tool_result():
    """Gap 5: validation rejection produces canonical ToolResult with error_type='validation_error'."""
    from agent_arena.tool_protocol import REGISTRY

    norm_args, errors = REGISTRY.validate_call("read", {"path": 12345})
    assert len(errors) > 0

    err_msg = f"ERROR: validation failed: {'; '.join(errors)}"
    val_res = ToolResult(
        tool="read",
        success=False,
        output=err_msg,
        error=f"validation failed: {'; '.join(errors)}",
        exit_code=1,
        error_type="validation_error",
        step_charged=True,
        truncated=False,
    )
    assert val_res.success is False
    assert val_res.error_type == "validation_error"
    assert val_res.exit_code == 1
    assert val_res.step_charged is True
    assert val_res.truncated is False

