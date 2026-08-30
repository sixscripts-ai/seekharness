"""Fighter sandbox pip set and canonical YAML must ship without a deploy overlay."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import yaml

from agent_arena.runtime_packaging import (
    CANONICAL_SKILL_REMOTE_DIR,
    FIGHTER_SANDBOX_PIP,
    attach_canonical_skill_yaml,
    canonical_skill_runtime_env,
    fighter_sandbox_pip_packages,
    local_canonical_skill_yaml_paths,
    packaging_source_is_self_contained,
)
from agent_arena.skills.canonical_metadata import (
    canonical_catalog_path,
    load_canonical_catalog,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MODAL_ENTRY = REPO_ROOT / "backend" / "modal_entry.py"
LAUNCHER = REPO_ROOT / "backend" / "agent_arena" / "sandbox_launcher.py"


def _source_order(path: Path, first: str, second: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert first in text
    assert second in text
    assert text.rindex(first) < text.rindex(second)


def test_fighter_sandbox_pip_includes_pyyaml_only():
    packages = fighter_sandbox_pip_packages()
    assert packages == ("httpx", "pytest", "pyyaml")
    assert FIGHTER_SANDBOX_PIP == packages
    assert yaml.__name__ == "yaml"


def test_canonical_yaml_files_exist_on_package_path():
    paths = local_canonical_skill_yaml_paths()
    assert {path.name for path in paths} == {"catalog.v0.3.yaml", "graph.v0.3.yaml"}
    for path in paths:
        assert path.is_file()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
    catalog_path = canonical_catalog_path()
    assert Path(catalog_path).is_file()


def test_canonical_catalog_loads_from_packaged_runtime():
    catalog = load_canonical_catalog()
    assert catalog.skills
    assert catalog.get("python-kata-fixer") is not None


def test_executor_import_path_does_not_require_backend_extras():
    advanced = importlib.import_module("agent_arena.sandbox.executors.advanced_executor")
    skill_pool = importlib.import_module("agent_arena.sandbox.executors.skill_pool")
    executors = importlib.import_module("agent_arena.sandbox.executors")
    assert advanced.AdvancedExecutor is not None
    assert skill_pool.load_skill is not None
    assert executors.get_executor is not None


def test_modal_and_sandbox_images_attach_yaml_after_python_source():
    modal_src = MODAL_ENTRY.read_text(encoding="utf-8")
    launcher_src = LAUNCHER.read_text(encoding="utf-8")
    assert packaging_source_is_self_contained(modal_src)
    assert packaging_source_is_self_contained(launcher_src)
    _source_order(MODAL_ENTRY, 'add_local_python_source("agent_arena")', "attach_canonical_skill_yaml")
    _source_order(LAUNCHER, 'add_local_python_source("agent_arena")', "attach_canonical_skill_yaml")
    assert "fighter_sandbox_pip_packages()" in launcher_src
    assert 'pip_install("httpx", "pytest")' not in launcher_src
    env = canonical_skill_runtime_env()
    assert env["ARENA_CANONICAL_SKILL_CATALOG"] == f"{CANONICAL_SKILL_REMOTE_DIR}/catalog.v0.3.yaml"
    assert env["ARENA_CANONICAL_SKILL_GRAPH"] == f"{CANONICAL_SKILL_REMOTE_DIR}/graph.v0.3.yaml"
    assert "canonical_skill_runtime_env()" in modal_src
    assert "canonical_skill_runtime_env()" in launcher_src
    assert "manual overlay" not in modal_src.lower()


def test_attach_helper_mounts_both_runtime_copies():
    calls: list[tuple[str, str]] = []

    class _Image:
        def add_local_file(self, local_path: str, remote_path: str):
            calls.append((local_path, remote_path))
            return self

    attach_canonical_skill_yaml(_Image())
    remotes = [remote for _local, remote in calls]
    assert any(remote.endswith("/catalog.v0.3.yaml") and remote.startswith("/opt/arena-canonical") for remote in remotes)
    assert any(remote.endswith("/graph.v0.3.yaml") and remote.startswith("/opt/arena-canonical") for remote in remotes)
    assert any(remote.endswith("/catalog.v0.3.yaml") and remote.startswith("/root/agent_arena/skills") for remote in remotes)
    assert any(remote.endswith("/graph.v0.3.yaml") and remote.startswith("/root/agent_arena/skills") for remote in remotes)
    for local_path, _remote in calls:
        assert Path(local_path).is_file()


def test_modal_entry_parses_and_still_keeps_evaluator_volume_private():
    source = MODAL_ENTRY.read_text(encoding="utf-8")
    ast.parse(source)
    assert source.count('"ARENA_EVALUATOR_DIR"') == 1
    assert "attach_canonical_skill_yaml" in source
