"""Shared Modal/fighter-sandbox packaging for executor bootstrap.

``add_local_python_source`` ships ``.py`` files only. Skill Graph D0 loads
``catalog.v0.3.yaml`` / ``graph.v0.3.yaml`` at import time, so those assets
must be attached explicitly. The fighter sandbox image is a small pip set
(not the full backend extra), and must include PyYAML.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Smallest third-party set required to import and run the current executor
# stack inside a fighter Modal Sandbox. AgentConfig is loaded during executor
# bootstrap, so its explicit Pydantic dependency belongs in this image.
# Never add Appwrite, FastAPI, SQLAlchemy, or other control-plane packages:
# SANDBOX_BOOT_FAILURE is what happens when the fighter process imports them.
FIGHTER_SANDBOX_PIP: tuple[str, ...] = ("httpx", "pytest", "pyyaml", "pydantic")

CANONICAL_SKILL_YAML_NAMES: tuple[str, ...] = (
    "catalog.v0.3.yaml",
    "graph.v0.3.yaml",
)
CANONICAL_SKILL_REMOTE_DIR = "/opt/arena-canonical"
PACKAGE_SKILLS_REMOTE_DIR = "/root/agent_arena/skills"
FIGHTER_SKILLS_REMOTE_DIR = "/opt/arena-skills"


def fighter_skill_directory() -> Path:
    """Resolve battle skill bodies, never the host-agent .agents/skills tree."""
    configured = os.environ.get("ARENA_SKILLS_ROOT", "").strip()
    if configured:
        return Path(configured)
    mounted = Path(FIGHTER_SKILLS_REMOTE_DIR)
    if mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2] / "arena-fighter-skills"


def attach_fighter_skills(image: Any) -> Any:
    root = fighter_skill_directory()
    if not root.is_dir() or not any(root.glob("*/SKILL.md")):
        raise FileNotFoundError(f"Fighter skill directory is missing or empty: {root}")
    return image.add_local_dir(str(root), remote_path=FIGHTER_SKILLS_REMOTE_DIR)


def fighter_sandbox_pip_packages() -> tuple[str, ...]:
    return FIGHTER_SANDBOX_PIP


def local_canonical_skill_dir() -> Path:
    package_dir = Path(__file__).resolve().parent / "skills"
    if all((package_dir / name).is_file() for name in CANONICAL_SKILL_YAML_NAMES):
        return package_dir
    mounted = Path(CANONICAL_SKILL_REMOTE_DIR)
    if all((mounted / name).is_file() for name in CANONICAL_SKILL_YAML_NAMES):
        return mounted
    return package_dir


def local_canonical_skill_yaml_paths() -> tuple[Path, ...]:
    root = local_canonical_skill_dir()
    paths = tuple(root / name for name in CANONICAL_SKILL_YAML_NAMES)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "canonical skill YAML missing from package: " + ", ".join(missing)
        )
    return paths


def canonical_skill_runtime_env() -> dict[str, str]:
    """Env that points loaders at the dedicated Modal mount, not a deploy overlay."""
    return {
        "ARENA_CANONICAL_SKILL_CATALOG": f"{CANONICAL_SKILL_REMOTE_DIR}/catalog.v0.3.yaml",
        "ARENA_CANONICAL_SKILL_GRAPH": f"{CANONICAL_SKILL_REMOTE_DIR}/graph.v0.3.yaml",
    }


def attach_canonical_skill_yaml(image: Any) -> Any:
    """Attach D0 YAML onto the Modal image used by backend and fighter sandboxes.

    Files are mounted at a stable ``/opt/arena-canonical`` path (env-selected)
    and also next to the Python package so ``importlib.resources`` works if
    env is unset. Both copies come from the committed package tree.
    """
    for path in local_canonical_skill_yaml_paths():
        image = image.add_local_file(
            str(path),
            remote_path=f"{CANONICAL_SKILL_REMOTE_DIR}/{path.name}",
        )
        image = image.add_local_file(
            str(path),
            remote_path=f"{PACKAGE_SKILLS_REMOTE_DIR}/{path.name}",
        )
    return image


def packaging_source_is_self_contained(source: str) -> bool:
    """True when a Modal entry/spawn module attaches YAML in-code (no overlay)."""
    return "attach_canonical_skill_yaml" in source
