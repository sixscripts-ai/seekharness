"""Trusted verifier owns pytest config; fighter conftest/ini cannot force pass."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from agent_arena.target_library import load_target_bundle
from agent_arena.target_verifier import (
    _HARNESS_BASENAMES,
    verify_target_submission,
)

HIDDEN_ASSERT = "assert ping() == 'pong'"


def _write_bundle(root: Path) -> Path:
    tid = "harness-iso"
    target = root / tid
    (target / "starter").mkdir(parents=True)
    (target / "tests" / "visible").mkdir(parents=True)
    (target / "tests" / "hidden").mkdir(parents=True)
    (target / "target.yaml").write_text(
        f"""
schema_version: 1
id: {tid}
name: Harness Iso
category: security
difficulty: novice
format: solo
runtime: python311
description: Verifier harness isolation
objectives:
  - return pong
workspace:
  starter_dir: starter
  visible_tests_dir: tests/visible
  hidden_tests_dir: tests/hidden
  reference_dir: reference
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: python3 -m pytest tests/visible -q
  hidden_command: python3 -m pytest tests/hidden -q
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 8
  exec_timeout_seconds: 30
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )
    (target / "starter" / "app.py").write_text("def ping():\n    return 'wrong'\n", encoding="utf-8")
    (target / "tests" / "visible" / "test_visible.py").write_text(
        "from app import ping\n\ndef test_ping():\n    " + HIDDEN_ASSERT + "\n",
        encoding="utf-8",
    )
    (target / "tests" / "hidden" / "test_hidden.py").write_text(
        "from app import ping\n\ndef test_hidden():\n    " + HIDDEN_ASSERT + "\n",
        encoding="utf-8",
    )
    return target


def _legacy_naive_verify(bundle, submitted_files: dict[str, str]) -> int:
    """Historical copy-into-cwd + pytest (the attack that used to succeed)."""
    with tempfile.TemporaryDirectory(prefix="legacy-naive-") as tmp:
        work = Path(tmp)
        for rel, data in bundle.starter_files.items():
            dest = work / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        for rel, payload in submitted_files.items():
            dest = work / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(payload, encoding="utf-8")
        vis = work / "tests" / "visible"
        vis.mkdir(parents=True, exist_ok=True)
        for rel, data in bundle.visible_test_files.items():
            (vis / rel).write_bytes(data)
        hid = work / "tests" / "hidden"
        hid.mkdir(parents=True, exist_ok=True)
        for rel, data in bundle.hidden_test_files.items():
            dest = hid / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(work)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/hidden", "-q"],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return proc.returncode


def test_legacy_conftest_injection_used_to_force_pass(tmp_path: Path):
    """Prove the historical attack: fighter conftest.py zeros pytest exit status."""
    target = _write_bundle(tmp_path)
    bundle = load_target_bundle(target)
    malicious = (
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    session.exitstatus = 0\n"
    )
    submitted = {
        "app.py": "def ping():\n    return 'wrong'\n",
        "conftest.py": malicious,
    }
    rc = _legacy_naive_verify(bundle, submitted)
    assert rc == 0, "legacy naive pytest must have been hijackable by conftest.py"


def test_trusted_verifier_ignores_malicious_conftest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    target = _write_bundle(tmp_path)
    bundle = load_target_bundle(target)
    malicious = (
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    session.exitstatus = 0\n"
    )
    evidence = verify_target_submission(
        bundle,
        {
            "app.py": "def ping():\n    return 'wrong'\n",
            "conftest.py": malicious,
            "pytest.ini": "[pytest]\naddopts = --ignore=tests/hidden\n",
            "pyproject.toml": "[tool.pytest.ini_options]\naddopts = --ignore=tests/hidden\n",
            "sitecustomize.py": "raise SystemExit(0)\n",
            "usercustomize.py": "raise SystemExit(0)\n",
            "tests/hidden/conftest.py": malicious,
        },
        run_visible=True,
        run_hidden=True,
    )
    assert evidence.passed is False
    assert evidence.hidden_passed is False


def test_pytest_ini_ignore_hidden_does_not_skip_oracle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    target = _write_bundle(tmp_path)
    bundle = load_target_bundle(target)
    evidence = verify_target_submission(
        bundle,
        {
            "app.py": "def ping():\n    return 'wrong'\n",
            "pytest.ini": "[pytest]\naddopts = --ignore=tests/hidden -p no:cacheprovider\n",
            "tox.ini": "[tox]\nskipsdist = true\n",
            "setup.cfg": "[tool:pytest]\naddopts = --ignore=tests/hidden\n",
        },
        run_visible=True,
        run_hidden=True,
    )
    assert evidence.hidden_passed is False
    assert evidence.passed is False


def test_correct_submission_still_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    target = _write_bundle(tmp_path)
    bundle = load_target_bundle(target)
    evidence = verify_target_submission(
        bundle,
        {"app.py": "def ping():\n    return 'pong'\n"},
        run_visible=True,
        run_hidden=True,
    )
    assert evidence.passed is True
    assert evidence.visible_passed is True
    assert evidence.hidden_passed is True


def test_harness_basenames_cover_pytest_and_site():
    assert "conftest.py" in _HARNESS_BASENAMES
    assert "pytest.ini" in _HARNESS_BASENAMES
    assert "sitecustomize.py" in _HARNESS_BASENAMES
    assert "usercustomize.py" in _HARNESS_BASENAMES
    assert "pyproject.toml" in _HARNESS_BASENAMES
    assert "tox.ini" in _HARNESS_BASENAMES


def test_executor_inprocess_solo_verify_returns_coarse_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """In-process solo verify must not NameError and must not leak hidden fields."""
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    target = _write_bundle(tmp_path)
    bundle = load_target_bundle(target)

    class _Lib:
        def get_target(self, tid):
            return bundle if tid == bundle.id else None

    monkeypatch.setattr(
        "agent_arena.target_library.get_target_library",
        lambda root: _Lib(),
    )
    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor

    transport = FakeTransport()
    client = InternalClient(transport)
    ev, err = AdvancedExecutor()._verify_target_trusted(
        client=client,
        battle_id="b-solo",
        target_id=bundle.id,
        files={"app.py": "def ping():\n    return 'pong'\n"},
        format_config={},
        phase="race",
        role="fighter",
        model_id="m1",
    )
    assert err is None
    assert ev is not None
    assert ev["passed"] is True
    assert ev["visible_passed"] is True
    assert "hidden_passed" not in ev
    assert "hidden_output" not in ev
    assert "hidden_exit_code" not in ev
    arts = [r.get("artifact") or "" for r in transport.rounds]
    assert any("TRUSTED_VERIFICATION:" in a for a in arts)
    assert all("hidden_output" not in a for a in arts)
