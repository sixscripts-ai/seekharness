"""Public library must not track or load hidden/reference evaluator material."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_arena.sandbox.executors.advanced_executor import (
    ToolSession,
    _strip_secret_env,
)
from agent_arena.battle_public import public_battle_payload
from agent_arena.target_library import (
    TargetSecurityError,
    compile_target_to_battle_config,
    fighter_visible_battle_config,
    load_target_bundle,
    materialize_fighter_visible_library,
    private_evaluator_dir,
)
from agent_arena.target_verifier import verify_target_submission
from tests.eval_fixtures import point_evaluators, write_private_evaluator

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = REPO_ROOT / "targets" / "library"
PRIVATE_MARKER = "SECRECY_PRIVATE_MARKER_xyz"
DECOY_MARKER = "SECRECY_LIBRARY_DECOY_xyz"

_MIN_MANIFEST = """
schema_version: 1
id: {tid}
name: Secrecy Fixture
category: security
difficulty: novice
format: solo
runtime: python311
description: overlay-only evaluator
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
"""


def _public_target(root: Path, tid: str) -> Path:
    target = root / tid
    (target / "starter").mkdir(parents=True)
    (target / "tests" / "visible").mkdir(parents=True)
    (target / "target.yaml").write_text(_MIN_MANIFEST.format(tid=tid), encoding="utf-8")
    (target / "starter" / "app.py").write_text(
        "def ping():\n    return 'pong'\n", encoding="utf-8"
    )
    (target / "tests" / "visible" / "test_visible.py").write_text(
        "from app import ping\n\ndef test_ping():\n    assert ping() == 'pong'\n",
        encoding="utf-8",
    )
    return target


def test_public_library_contains_no_hidden_or_reference_files():
    leftover = [
        p
        for p in LIBRARY_ROOT.rglob("*")
        if p.is_file()
        and (
            "/tests/hidden/" in p.as_posix()
            or "/reference/" in p.as_posix()
            or p.name == "breaker_harness.py"
        )
    ]
    assert leftover == []


def test_tracked_library_rejects_hidden_and_reference_files():
    listed = subprocess.check_output(
        ["git", "ls-files", "targets/library"],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()
    leaked = [
        path
        for path in listed
        if (
            "/tests/hidden/" in path
            or "/reference/" in path
            or path.endswith("breaker_harness.py")
        )
    ]
    assert leaked == []


def test_tracked_evaluator_tree_contains_only_the_placeholder():
    """git ls-files reads the index, so this also catches staged private files."""
    listed = [
        path
        for path in subprocess.check_output(
            ["git", "ls-files", "targets/evaluators"],
            cwd=REPO_ROOT,
            text=True,
        ).splitlines()
        if path.strip()
    ]
    assert listed == ["targets/evaluators/.gitkeep"]


def _is_ignored(rel_path: str) -> bool:
    return (
        subprocess.run(
            ["git", "check-ignore", "-q", rel_path],
            cwd=REPO_ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


def test_evaluator_directory_is_gitignored():
    assert _is_ignored("targets/evaluators/gitignore-probe/tests/hidden/x.py")
    assert _is_ignored("targets/evaluators/gitignore-probe/reference/app.py")
    # The placeholder stays trackable so the directory survives a clean clone.
    assert not _is_ignored("targets/evaluators/.gitkeep")


def test_private_paths_under_public_library_are_gitignored():
    """Private material re-added under targets/library must not be committable."""
    for probe in (
        "targets/library/probe-target/tests/hidden/test_secret.py",
        "targets/library/probe-target/reference/solution.py",
        "targets/library/probe-target/tests/breaker_harness.py",
        "targets/library/evaluators/probe-target/tests/hidden/x.py",
        "targets/probe/evaluators/probe-target/reference/x.py",
    ):
        assert _is_ignored(probe), f"{probe} must be gitignored"


def test_public_library_paths_remain_trackable():
    """The ignore rules must not swallow legitimate public target files."""
    for probe in (
        "targets/library/probe-target/target.yaml",
        "targets/library/probe-target/README.md",
        "targets/library/probe-target/starter/app.py",
        "targets/library/probe-target/tests/visible/test_visible.py",
    ):
        assert not _is_ignored(probe), f"{probe} must stay trackable"


def test_private_overlay_loads_and_ignores_library_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    tid = "overlay-only"
    library = tmp_path / "library"
    target = _public_target(library, tid)
    (target / "tests" / "hidden").mkdir(parents=True)
    (target / "tests" / "hidden" / "SECRET.txt").write_text(DECOY_MARKER, encoding="utf-8")
    (target / "reference").mkdir(parents=True)
    (target / "reference" / "app.py").write_text(DECOY_MARKER, encoding="utf-8")
    eval_root = tmp_path / "evaluators"
    write_private_evaluator(
        eval_root,
        tid,
        hidden={
            "SECRET.txt": PRIVATE_MARKER,
            "test_hidden.py": (
                "from pathlib import Path\n"
                "from app import ping\n\n"
                "def test_hidden():\n"
                "    assert ping() == 'pong'\n"
                f"    assert Path('tests/hidden/SECRET.txt').read_text() == {PRIVATE_MARKER!r}\n"
            ),
        },
        reference={"SECRET_REF.txt": PRIVATE_MARKER},
        extra={"tests/breaker_harness.py": "def test_break():\n    assert True\n"},
    )
    point_evaluators(monkeypatch, eval_root)
    bundle = load_target_bundle(target)
    assert PRIVATE_MARKER in bundle.hidden_test_files["SECRET.txt"].decode("utf-8")
    assert DECOY_MARKER not in bundle.hidden_test_files["SECRET.txt"].decode("utf-8")
    assert PRIVATE_MARKER in bundle.reference_files["SECRET_REF.txt"].decode("utf-8")
    assert "app.py" not in bundle.reference_files
    assert "tests/breaker_harness.py" in bundle.private_fixture_files
    assert private_evaluator_dir(tid) == (eval_root / tid).resolve()


def test_env_evaluator_dir_does_not_fall_back_to_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    point_evaluators(monkeypatch, tmp_path / "empty-evals")
    with pytest.raises(TargetSecurityError, match="requires a private evaluator"):
        load_target_bundle(LIBRARY_ROOT / "authentication-gate")


def test_missing_evaluator_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tid = "missing-eval-target"
    target = _public_target(tmp_path / "library", tid)
    point_evaluators(monkeypatch, tmp_path / "evaluators-empty")
    with pytest.raises(TargetSecurityError, match="requires a private evaluator"):
        load_target_bundle(target)


def test_empty_evaluator_hidden_tests_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    tid = "empty-hidden-eval"
    target = _public_target(tmp_path / "library", tid)
    empty = tmp_path / "evaluators" / tid
    empty.mkdir(parents=True)
    point_evaluators(monkeypatch, tmp_path / "evaluators")
    with pytest.raises(TargetSecurityError, match="has no hidden tests"):
        load_target_bundle(target)


def test_symlinked_target_root_is_rejected(tmp_path: Path):
    real = _public_target(tmp_path / "real", "symlink-root-target")
    (real / "starter" / "SECRET.txt").write_text(PRIVATE_MARKER, encoding="utf-8")
    library = tmp_path / "library"
    library.mkdir()
    dest_link = library / "symlink-root-target"
    try:
        dest_link.symlink_to(real)
    except OSError:
        pytest.skip("Symlinks not supported on filesystem")
    public = tmp_path / "public"
    with pytest.raises(TargetSecurityError, match="symlink"):
        materialize_fighter_visible_library(library, public)
    leaked = ""
    if public.exists():
        for p in public.rglob("*"):
            if p.is_file() and not p.is_symlink():
                leaked += p.read_text(encoding="utf-8", errors="ignore")
    assert PRIVATE_MARKER not in leaked
    assert not (public / "symlink-root-target" / "starter" / "app.py").exists()


def test_symlinked_public_file_is_rejected(tmp_path: Path):
    library = tmp_path / "library"
    target = _public_target(library, "symlink-file-target")
    secret = tmp_path / "private.txt"
    secret.write_text(PRIVATE_MARKER, encoding="utf-8")
    try:
        (target / "starter" / "leak.txt").symlink_to(secret)
    except OSError:
        pytest.skip("Symlinks not supported on filesystem")
    public = tmp_path / "public"
    with pytest.raises(TargetSecurityError, match="symlink"):
        materialize_fighter_visible_library(library, public)
    leaked = ""
    if public.exists():
        for p in public.rglob("*"):
            if p.is_file() and not p.is_symlink():
                leaked += p.read_text(encoding="utf-8", errors="ignore")
    assert PRIVATE_MARKER not in leaked
    assert not (public / "symlink-file-target" / "starter" / "leak.txt").exists()


def test_hardlink_to_evaluator_content_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    tid = "hardlink-target"
    library = tmp_path / "library"
    target = _public_target(library, tid)
    eval_root = tmp_path / "evaluators"
    write_private_evaluator(
        eval_root,
        tid,
        hidden={"SECRET.txt": PRIVATE_MARKER, "test_hidden.py": "def test_ok():\n    assert True\n"},
    )
    point_evaluators(monkeypatch, eval_root)
    hidden = eval_root / tid / "tests" / "hidden" / "SECRET.txt"
    try:
        (target / "starter" / "aliased.txt").hardlink_to(hidden)
    except OSError:
        try:
            import os

            os.link(hidden, target / "starter" / "aliased.txt")
        except OSError:
            pytest.skip("Hardlinks not supported on filesystem")
    public = tmp_path / "public"
    with pytest.raises(TargetSecurityError, match="hardlink"):
        materialize_fighter_visible_library(library, public)
    leaked = ""
    if public.exists():
        for p in public.rglob("*"):
            if p.is_file() and not p.is_symlink():
                leaked += p.read_text(encoding="utf-8", errors="ignore")
    assert PRIVATE_MARKER not in leaked
    assert not (public / tid / "starter" / "aliased.txt").exists()


def test_sanitized_public_tree_matches_modal_allowlist(tmp_path: Path):
    public = tmp_path / "public"
    materialize_fighter_visible_library(LIBRARY_ROOT, public)
    allowed_root_files = {"target.yaml", "README.md", "TARGET.md"}
    for target_dir in public.iterdir():
        if not target_dir.is_dir():
            continue
        for path in target_dir.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(target_dir).as_posix()
            assert not path.is_symlink(), rel
            assert path.lstat().st_nlink == 1, rel
            assert "/tests/hidden/" not in f"/{rel}/"
            assert not rel.startswith("reference/")
            assert path.name != "breaker_harness.py"
            allowed = rel in allowed_root_files or rel.startswith("starter/") or rel.startswith(
                "tests/visible/"
            )
            assert allowed, rel


def test_fighter_materialization_omits_evaluator_and_library_leftovers(tmp_path: Path):
    tid = "mat-secrecy"
    library = tmp_path / "library"
    target = _public_target(library, tid)
    (target / "tests" / "hidden").mkdir(parents=True)
    (target / "tests" / "hidden" / "SECRET.txt").write_text(PRIVATE_MARKER, encoding="utf-8")
    (target / "reference").mkdir(parents=True)
    (target / "reference" / "app.py").write_text(PRIVATE_MARKER, encoding="utf-8")
    (target / "evaluators").mkdir()
    (target / "evaluators" / "hidden_eval.py").write_text(PRIVATE_MARKER, encoding="utf-8")
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    root = public / tid
    assert (root / "starter" / "app.py").is_file()
    assert not (root / "tests" / "hidden").exists()
    assert not (root / "reference").exists()
    assert not (root / "evaluators").exists()
    combined = ""
    for p in root.rglob("*"):
        if p.is_file():
            combined += p.read_text(encoding="utf-8", errors="ignore")
    assert PRIVATE_MARKER not in combined


def test_fighter_read_shell_python_cannot_access_private_evaluator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    tid = "iso-secrecy"
    library = tmp_path / "library"
    target = _public_target(library, tid)
    eval_root = tmp_path / "evaluators"
    write_private_evaluator(
        eval_root,
        tid,
        hidden={"SECRET.txt": PRIVATE_MARKER, "test_hidden.py": "def test_ok():\n    assert True\n"},
        reference={"SECRET_REF.txt": PRIVATE_MARKER},
    )
    point_evaluators(monkeypatch, eval_root)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    work = public / tid
    sess = ToolSession(work)
    read_res = sess.read("tests/hidden/SECRET.txt")
    assert read_res.success is False
    assert PRIVATE_MARKER not in (read_res.output or "")
    shell_res = sess.shell("cat tests/hidden/SECRET.txt")
    shell_text = f"{shell_res.output or ''} {shell_res.error or ''}"
    assert PRIVATE_MARKER not in shell_text
    assert shell_res.success is False
    fighter_secret = work / "tests" / "hidden" / "SECRET.txt"
    assert not fighter_secret.exists()
    inline = (
        "from pathlib import Path\n"
        "p = Path(%r)\n"
        "assert not p.exists()\n"
        "try:\n"
        "    print('LEAKED:' + p.read_text())\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__ + ':' + str(exc))\n"
    ) % str(fighter_secret)
    py_res = sess.run(inline=inline)
    combined = f"{py_res.output or ''} {py_res.error or ''}"
    assert "LEAKED:" not in combined
    assert PRIVATE_MARKER not in combined
    assert "FileNotFoundError" in combined or "No such file" in combined


def test_trusted_verifier_uses_private_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    tid = "verify-overlay"
    target = _public_target(tmp_path / "library", tid)
    eval_root = tmp_path / "evaluators"
    write_private_evaluator(
        eval_root,
        tid,
        hidden={
            "test_hidden.py": (
                "from app import ping\n\ndef test_hidden():\n    assert ping() == 'pong'\n"
            )
        },
    )
    point_evaluators(monkeypatch, eval_root)
    bundle = load_target_bundle(target)
    evidence = verify_target_submission(
        bundle,
        {"app.py": (target / "starter" / "app.py").read_text(encoding="utf-8")},
        run_visible=True,
        run_hidden=True,
    )
    assert evidence.passed is True
    assert evidence.visible_passed is True
    assert evidence.hidden_passed is True


def test_arena_evaluator_dir_stripped_from_fighter_env():
    cleaned = _strip_secret_env(
        {
            "PATH": "/usr/bin",
            "ARENA_EVALUATOR_DIR": "/opt/arena-evaluators",
            "ARENA_TRUSTED_TARGETS_DIR": "/opt/trusted",
            "BATTLE_BOOTSTRAP_JSON": '{"format_config":{"hidden_hash":"abc"}}',
            "HOME": "/tmp",
        }
    )
    assert "ARENA_EVALUATOR_DIR" not in cleaned
    assert "ARENA_TRUSTED_TARGETS_DIR" not in cleaned
    assert "BATTLE_BOOTSTRAP_JSON" not in cleaned
    assert cleaned["PATH"] == "/usr/bin"


def test_fighter_bootstrap_strips_private_verifier_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    tid = "bootstrap-secrecy"
    target = _public_target(tmp_path / "library", tid)
    eval_root = tmp_path / "evaluators"
    write_private_evaluator(
        eval_root,
        tid,
        hidden={
            "test_hidden.py": (
                "from app import ping\n\ndef test_hidden():\n    assert ping() == 'pong'\n"
            )
        },
    )
    point_evaluators(monkeypatch, eval_root)
    bundle = load_target_bundle(target)
    trusted = compile_target_to_battle_config(bundle, arena_size=1)
    assert trusted["hidden_hash"]
    assert trusted["verification"]["hidden_command"]
    public = fighter_visible_battle_config(trusted)
    assert "hidden_hash" not in public
    assert "hidden_command" not in (public.get("verification") or {})
    assert public["verification"]["visible_command"]
    assert trusted["hidden_hash"]
    assert trusted["verification"]["hidden_command"]
    owner = public_battle_payload(
        {"id": "owner-1", "battle_config": trusted, "target_id": tid}
    )
    owner_blob = json.dumps(owner)
    assert "hidden_hash" not in owner_blob
    assert "hidden_command" not in owner_blob


def test_fighter_env_cannot_recover_private_evaluator_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bootstrap = {
        "format_config": {
            "hidden_hash": "hidden-hash-should-not-leak",
            "verification": {
                "hidden_command": "python3 -m pytest tests/hidden -q",
                "visible_command": "python3 -m pytest tests/visible -q",
            },
        }
    }
    monkeypatch.setenv("ARENA_EVALUATOR_DIR", "/opt/arena-evaluators")
    monkeypatch.setenv("ARENA_TRUSTED_TARGETS_DIR", "/opt/trusted-targets")
    monkeypatch.setenv("BATTLE_BOOTSTRAP_JSON", __import__("json").dumps(bootstrap))
    sess = ToolSession(tmp_path / "work")
    env_res = sess.shell("env")
    env_text = f"{env_res.output or ''} {env_res.error or ''} {env_res}"
    inline = (
        "import os\n"
        "for k, v in os.environ.items():\n"
        "    print(f'{k}={v}')\n"
    )
    py_res = sess.run(inline=inline)
    py_text = f"{py_res.output or ''} {py_res.error or ''} {py_res}"
    combined = env_text + "\n" + py_text
    for needle in (
        "hidden-hash-should-not-leak",
        "hidden_hash",
        "hidden_command",
        "tests/hidden",
        "ARENA_EVALUATOR_DIR",
        "/opt/arena-evaluators",
        "ARENA_TRUSTED_TARGETS_DIR",
        "BATTLE_BOOTSTRAP_JSON",
    ):
        assert needle not in combined, needle


def test_check_tracked_secrecy_script_passes_on_this_tree():
    script = REPO_ROOT / "targets" / "library" / "scripts" / "check_tracked_secrecy.py"
    result = subprocess.run(
        ["python3", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "no tracked private evaluator paths" in result.stdout


def test_check_tracked_secrecy_script_detects_private_paths(monkeypatch: pytest.MonkeyPatch):
    import importlib.util

    script = REPO_ROOT / "targets" / "library" / "scripts" / "check_tracked_secrecy.py"
    spec = importlib.util.spec_from_file_location("check_tracked_secrecy", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def fake_listed(path: str) -> list[str]:
        if path == "targets/library":
            return [
                "targets/library/tinyshop/tests/hidden/test_solver.py",
                "targets/library/tinyshop/reference/solver.py",
                "targets/library/tinyshop/tests/breaker_harness.py",
            ]
        if path == "targets/evaluators":
            return [
                "targets/evaluators/.gitkeep",
                "targets/evaluators/tinyshop/tests/hidden/x.py",
            ]
        return []

    monkeypatch.setattr(mod, "_listed", fake_listed)
    assert mod.main() == 1
