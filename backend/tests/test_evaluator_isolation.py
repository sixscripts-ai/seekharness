"""Evaluator isolation: fighter filesystem must not contain hidden/reference files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_arena.sandbox.executors.advanced_executor import ToolSession
from agent_arena.target_library import (
    load_target_bundle,
    materialize_fighter_visible_library,
    rel_is_fighter_public,
    relpath_is_private_evaluator,
)
from agent_arena.target_verifier import verify_target_submission
from agent_arena.target_verifier import verify_target_submission

PRIVATE_MARKER = "PRIVATE_MARKER_evaluator_isolation_xyz"
REFERENCE_MARKER = "PRIVATE_REFERENCE_SOLUTION_abc"


def _write_synth_target(root: Path) -> Path:
    tid = "synth-isolation"
    target = root / tid
    (target / "starter").mkdir(parents=True)
    (target / "tests" / "visible").mkdir(parents=True)
    (target / "tests" / "hidden").mkdir(parents=True)
    (target / "reference").mkdir(parents=True)
    (target / "target.yaml").write_text(
        f"""
schema_version: 1
id: {tid}
name: Synth Isolation
category: security
difficulty: novice
format: solo
runtime: python311
description: Isolation proof target
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
    (target / "starter" / "app.py").write_text("def ping():\n    return 'pong'\n", encoding="utf-8")
    (target / "tests" / "visible" / "test_visible.py").write_text(
        "from app import ping\n\ndef test_ping():\n    assert ping() == 'pong'\n",
        encoding="utf-8",
    )
    (target / "tests" / "hidden" / "SECRET.txt").write_text(PRIVATE_MARKER, encoding="utf-8")
    (target / "tests" / "hidden" / "test_hidden.py").write_text(
        "from pathlib import Path\n\n"
        "def test_secret():\n"
        f"    assert Path('tests/hidden/SECRET.txt').read_text() == {PRIVATE_MARKER!r}\n",
        encoding="utf-8",
    )
    (target / "reference" / "app.py").write_text(
        f"def ping():\n    return 'pong'\n# {REFERENCE_MARKER}\n",
        encoding="utf-8",
    )
    (target / "reference" / "SECRET_REF.txt").write_text(REFERENCE_MARKER, encoding="utf-8")
    (target / "oracle").mkdir()
    (target / "oracle" / "answer.txt").write_text("ORACLE_PRIVATE_xyz", encoding="utf-8")
    (target / "evaluators").mkdir()
    (target / "evaluators" / "hidden_eval.py").write_text("assert False\n", encoding="utf-8")
    return target


def test_relpath_classifier():
    assert relpath_is_private_evaluator("tests/hidden/SECRET.txt") is True
    assert relpath_is_private_evaluator("tests/HIDDEN/x.py") is True
    assert relpath_is_private_evaluator("reference/app.py") is True
    assert relpath_is_private_evaluator("starter/app.py") is False
    assert relpath_is_private_evaluator("tests/visible/test_visible.py") is False
    from agent_arena.target_library import fighter_public_allowlist

    roots, files = fighter_public_allowlist(None)
    assert rel_is_fighter_public("starter/app.py", roots, files) is True
    assert rel_is_fighter_public("tests/visible/test_visible.py", roots, files) is True
    assert rel_is_fighter_public("oracle/answer.txt", roots, files) is False
    assert rel_is_fighter_public("tests/hidden/SECRET.txt", roots, files) is False


def test_public_package_omits_hidden_and_reference(tmp_path: Path):
    library = tmp_path / "library"
    _write_synth_target(library)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    hidden = public / "synth-isolation" / "tests" / "hidden" / "SECRET.txt"
    ref = public / "synth-isolation" / "reference" / "app.py"
    assert not hidden.exists()
    assert not (public / "synth-isolation" / "reference").exists()
    assert (public / "synth-isolation" / "starter" / "app.py").is_file()
    assert (public / "synth-isolation" / "tests" / "visible" / "test_visible.py").is_file()
    assert PRIVATE_MARKER not in (public / "synth-isolation" / "starter" / "app.py").read_text()


def test_a_direct_tool_read_denies_hidden(tmp_path: Path):
    library = tmp_path / "library"
    _write_synth_target(library)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    work = tmp_path / "work"
    sess = ToolSession(work)
    result = sess.read("tests/hidden/SECRET.txt")
    assert result.success is False
    assert PRIVATE_MARKER not in (result.output or "")
    assert PRIVATE_MARKER not in (result.error or "")


def test_b_shell_cannot_read_hidden(tmp_path: Path):
    library = tmp_path / "library"
    target = _write_synth_target(library)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    fighter_root = public / "synth-isolation"
    sess = ToolSession(fighter_root)
    result = sess.shell("cat tests/hidden/SECRET.txt")
    combined = f"{result.output or ''} {result.error or ''}"
    assert PRIVATE_MARKER not in combined
    assert result.success is False
    # Isolation is filesystem absence, not merely a command-guard rejection.
    assert "does not exist" in combined.lower() or "no such file" in combined.lower() or "not found" in combined.lower() or not (fighter_root / "tests" / "hidden" / "SECRET.txt").exists()
    assert not (fighter_root / "tests" / "hidden" / "SECRET.txt").exists()
    # Trusted copy still has the marker.
    assert (target / "tests" / "hidden" / "SECRET.txt").read_text() == PRIVATE_MARKER


def test_c_model_authored_python_cannot_open_hidden(tmp_path: Path):
    library = tmp_path / "library"
    _write_synth_target(library)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    private_path = public / "synth-isolation" / "tests" / "hidden" / "SECRET.txt"
    assert not private_path.exists()
    sess = ToolSession(tmp_path / "work")
    inline = (
        "p = %r\n"
        "try:\n"
        "    data = open(p).read()\n"
        "    print('LEAKED:' + data)\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__ + ':' + str(exc))\n"
    ) % str(private_path)
    result = sess.run(inline=inline)
    combined = f"{result.output or ''} {result.error or ''}"
    assert "LEAKED:" not in combined
    assert PRIVATE_MARKER not in combined
    assert "FileNotFoundError" in combined or "No such file" in combined or "not found" in combined.lower()


def test_d_reference_solution_absent_from_fighter_python(tmp_path: Path):
    library = tmp_path / "library"
    _write_synth_target(library)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    ref_path = public / "synth-isolation" / "reference" / "SECRET_REF.txt"
    assert not ref_path.exists()
    sess = ToolSession(tmp_path / "work")
    inline = (
        "p = %r\n"
        "try:\n"
        "    print('LEAKED:' + open(p).read())\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__ + ':' + str(exc))\n"
    ) % str(ref_path)
    result = sess.run(inline=inline)
    combined = f"{result.output or ''} {result.error or ''}"
    assert "LEAKED:" not in combined
    assert REFERENCE_MARKER not in combined
    assert "FileNotFoundError" in combined or "No such file" in combined


def test_e_trusted_verifier_reads_private_evaluator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    library = tmp_path / "library"
    target = _write_synth_target(library)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    bundle = load_target_bundle(target)
    assert PRIVATE_MARKER in bundle.hidden_test_files["SECRET.txt"].decode("utf-8")
    assert REFERENCE_MARKER in bundle.reference_files["SECRET_REF.txt"].decode("utf-8")
    evidence = verify_target_submission(
        bundle,
        {"app.py": (target / "starter" / "app.py").read_text(encoding="utf-8")},
        run_visible=True,
        run_hidden=True,
    )
    assert evidence.passed is True
    assert evidence.visible_passed is True
    assert evidence.hidden_passed is True
    # Public package still lacks the private files.
    assert not (public / "synth-isolation" / "tests" / "hidden" / "SECRET.txt").exists()


def test_unknown_private_directories_are_denied(tmp_path: Path):
    library = tmp_path / "library"
    _write_synth_target(library)
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    root = public / "synth-isolation"
    assert not (root / "oracle").exists()
    assert not (root / "evaluators").exists()
    assert not (root / "oracle" / "answer.txt").exists()
    assert (root / "starter" / "app.py").is_file()
    assert (root / "target.yaml").is_file()


def test_symlink_escapes_are_not_copied(tmp_path: Path):
    library = tmp_path / "library"
    target = _write_synth_target(library)
    bundle = load_target_bundle(target)
    assert PRIVATE_MARKER in bundle.hidden_test_files["SECRET.txt"].decode("utf-8")
    starter = target / "starter"
    hidden = target / "tests" / "hidden" / "SECRET.txt"
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE_SECRET", encoding="utf-8")
    try:
        (starter / "leak_hidden.txt").symlink_to(hidden)
        mid = starter / "mid_link"
        mid.symlink_to(hidden)
        (starter / "chained.txt").symlink_to(mid)
        (starter / "outside.txt").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not supported on filesystem")
    public = tmp_path / "public"
    materialize_fighter_visible_library(library, public)
    dest = public / "synth-isolation" / "starter"
    assert not (dest / "leak_hidden.txt").exists()
    assert not (dest / "chained.txt").exists()
    assert not (dest / "outside.txt").exists()
    combined = ""
    if dest.exists():
        for p in dest.rglob("*"):
            if p.is_file() and not p.is_symlink():
                combined += p.read_text(encoding="utf-8", errors="ignore")
    assert PRIVATE_MARKER not in combined
    assert "OUTSIDE_SECRET" not in combined
