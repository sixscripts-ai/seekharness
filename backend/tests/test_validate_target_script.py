"""validate_target.py must match production evaluator lookup and reject symlinks."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "targets" / "library" / "scripts" / "validate_target.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("validate_target_script", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_configured_missing_evaluator_does_not_fall_back_to_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ARENA_EVALUATOR_DIR", str(tmp_path / "empty-evals"))
    mod = _load_script()
    assert mod.evaluator_package("authentication-gate") is None
    assert mod.evaluator_package("tinyshop") is None


def test_overlay_rejects_symlink_instead_of_following(tmp_path: Path):
    mod = _load_script()
    secret = tmp_path / "secret.txt"
    secret.write_text("PRIVATE_OVERLAY_MARKER", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    try:
        (src / "leak.py").symlink_to(secret)
    except OSError:
        pytest.skip("Symlinks not supported on filesystem")
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ValueError, match="symlink"):
        mod.overlay(src, dest)
    assert not (dest / "leak.py").exists()
    assert "PRIVATE_OVERLAY_MARKER" not in "".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in dest.rglob("*")
        if p.is_file()
    )


def test_overlay_rejects_symlinked_source_root(tmp_path: Path):
    mod = _load_script()
    real = tmp_path / "real"
    real.mkdir()
    (real / "hidden.py").write_text("PRIVATE_OVERLAY_MARKER", encoding="utf-8")
    src = tmp_path / "src-link"
    try:
        src.symlink_to(real)
    except OSError:
        pytest.skip("Symlinks not supported on filesystem")
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ValueError, match="symlink"):
        mod.overlay(src, dest)
    assert list(dest.iterdir()) == []
