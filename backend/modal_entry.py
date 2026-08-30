import os
import sys
import tempfile
from pathlib import Path

import modal

_BASE_DIR = Path(__file__).resolve().parent.parent
_BACKEND_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _BASE_DIR / ".agents" / "skills"
_TARGETS_DIR = _BASE_DIR / "targets" / "library"

# Private evaluator material (hidden tests, reference solutions, trusted
# fixtures) is delivered by a named Modal Volume, never baked into an image and
# never attached to a fighter sandbox. Baking would copy the deployer's local
# gitignored tree into a runtime image that anyone with image or container
# access could read.
EVALUATOR_MOUNT_PATH = "/opt/arena-evaluators"
EVALUATOR_VOLUME_NAME = os.environ.get("ARENA_EVALUATOR_VOLUME", "arena-evaluators")

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agent_arena.target_library import materialize_fighter_visible_library

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_pyproject(str(Path(__file__).resolve().parent / "pyproject.toml"))
    .add_local_python_source("agent_arena")
)
if _SKILLS_DIR.is_dir():
    image = image.add_local_dir(str(_SKILLS_DIR), remote_path="/opt/arena-skills")

# Public allowlist only. Never add_local_dir the raw repository library:
# .gitignore is not a packaging boundary.
if _TARGETS_DIR.is_dir():
    _PUBLIC_TARGETS_DIR = Path(tempfile.mkdtemp(prefix="arena-public-targets-"))
    materialize_fighter_visible_library(_TARGETS_DIR, _PUBLIC_TARGETS_DIR)
    image = image.add_local_dir(str(_PUBLIC_TARGETS_DIR), remote_path="/opt/arena-targets")

# create_if_missing=False: an unpopulated evaluator root must fail the deploy
# instead of silently serving a library whose targets all fail closed.
evaluator_volume = modal.Volume.from_name(
    EVALUATOR_VOLUME_NAME,
    create_if_missing=False,
)

app = modal.App("agent-arena-backend", image=image)


_CURRENT_SHA = os.environ.get("ARENA_BUILD_SHA") or "unknown"
if _CURRENT_SHA == "unknown":
    try:
        import subprocess
        _CURRENT_SHA = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(_BASE_DIR)
        ).decode().strip()
    except Exception:
        pass


@app.function(
    secrets=[
        modal.Secret.from_name("agent-arena-dotenv"),
        modal.Secret.from_dict({"ARENA_BUILD_SHA": _CURRENT_SHA}),
    ],
    min_containers=1,
    # Trusted verification backend only. Read-only so a compromised backend
    # cannot rewrite hidden tests or reference solutions.
    volumes={EVALUATOR_MOUNT_PATH: evaluator_volume.read_only()},
    env={
        "ARENA_SKILLS_ROOT": "/opt/arena-skills",
        "ARENA_TARGETS_DIR": "/opt/arena-targets",
        "ARENA_EVALUATOR_DIR": EVALUATOR_MOUNT_PATH,
        "ARENA_BUILD_SHA": _CURRENT_SHA,
    },
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    from agent_arena.main import app as fastapi_application

    return fastapi_application


@app.function(
    secrets=[modal.Secret.from_name("agent-arena-dotenv")],
    schedule=modal.Period(minutes=1),
)
def reap_stale_battles():
    from agent_arena.reaper import reap_stale_battles as _reap

    reaped = _reap()
    print(f"reaper: failed {len(reaped)} stale battle(s): {reaped}")
