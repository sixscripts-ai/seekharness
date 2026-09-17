"""Fighter Modal image must import the battle loop without Appwrite.

Live SANDBOX_BOOT_FAILURE on 2026-09-16 was:

    from agent_arena.sandbox.agent_runtime import ...
    from agent_arena.providers import get_model_spec
    ModuleNotFoundError: No module named 'appwrite'

The fighter pip set is httpx/pytest/pyyaml/pydantic only. A subprocess with
Appwrite blocked is the actual image, not an in-process import that already
loaded providers in this pytest worker.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from agent_arena.runtime_packaging import FIGHTER_SANDBOX_PIP

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SANDBOX_DIR = BACKEND_ROOT / "agent_arena" / "sandbox"

_FIGHTER_BOOT_SCRIPT = r"""
import os
import sys
import types

class _Missing(types.ModuleType):
    def __getattr__(self, name):
        raise ModuleNotFoundError(self.__name__)

for name in (
    "appwrite",
    "appwrite.exception",
    "appwrite.query",
    "appwrite.client",
    "appwrite.services",
    "appwrite.services.databases",
):
    sys.modules[name] = _Missing(name)

os.environ["ARENA_IN_SANDBOX"] = "1"
os.environ["BATTLE_TOKEN"] = "scoped-test-token"
os.environ["BATTLE_BOOTSTRAP_JSON"] = '{"trusted": true}'
os.environ.pop("ARENA_INTEGRATION_TESTS", None)

from agent_arena.sandbox.entrypoint import main
from agent_arena.sandbox.runner import run_battle_loop, map_roles
from agent_arena.sandbox.executors import get_executor
from agent_arena.sandbox.agent_runtime import resolve_role_runtime_bindings
from agent_arena.difficulty import apply_difficulty

assert "agent_arena.providers" not in sys.modules, sorted(sys.modules)
assert "agent_arena.seed_formats" not in sys.modules

cfg = apply_difficulty(
    {
        "roles": ["fighter"],
        "difficulty": "novice",
        "engine": "universal",
        "battle_plan": {"phases": []},
    },
    "novice",
)
assert cfg["limits"]["max_tool_steps"] == 8

bindings = resolve_role_runtime_bindings(
    {"fighter": "host:modal-kimi"},
    {"roles": ["fighter"]},
)
assert bindings["fighter"].model_id == "host:modal-kimi"
assert map_roles(["fighter"], ["host:modal-kimi"])["fighter"] == "host:modal-kimi"

executor = get_executor(cfg)
assert type(executor).__name__ == "AdvancedExecutor"
assert callable(main)
assert callable(run_battle_loop)
print("fighter-boot-ok")
"""


def test_fighter_sandbox_pip_excludes_control_plane_packages():
    packages = {item.lower() for item in FIGHTER_SANDBOX_PIP}
    assert packages == {"httpx", "pytest", "pyyaml", "pydantic"}
    for forbidden in ("appwrite", "fastapi", "sqlalchemy", "modal"):
        assert forbidden not in packages


def test_agent_runtime_does_not_import_providers_at_module_level():
    tree = ast.parse((SANDBOX_DIR / "agent_runtime.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
            "providers"
        ):
            raise AssertionError(
                "agent_runtime.py imports providers at module level; "
                "that crashes the fighter Modal image"
            )


def test_executor_package_does_not_eagerly_import_advanced_executor():
    source = (SANDBOX_DIR / "executors" / "__init__.py").read_text(encoding="utf-8")
    assert "from .advanced_executor import" not in source
    assert "import_module" in source


def test_runner_applies_difficulty_without_seed_formats():
    source = (SANDBOX_DIR / "runner.py").read_text(encoding="utf-8")
    assert "seed_formats" not in source
    assert "from ..difficulty import apply_difficulty" in source


def test_fighter_entrypoint_boots_when_appwrite_is_missing():
    env = dict(os.environ)
    extra = str(BACKEND_ROOT)
    env["PYTHONPATH"] = extra + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.pop("ARENA_INTEGRATION_TESTS", None)
    proc = subprocess.run(
        [sys.executable, "-c", _FIGHTER_BOOT_SCRIPT],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "fighter-boot-ok" in proc.stdout
    assert "appwrite" not in proc.stderr.lower()
