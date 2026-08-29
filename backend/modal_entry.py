import os
from pathlib import Path

import modal

_BASE_DIR = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _BASE_DIR / ".agents" / "skills"
_TARGETS_DIR = _BASE_DIR / "targets" / "library"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_pyproject(str(Path(__file__).resolve().parent / "pyproject.toml"))
    .add_local_python_source("agent_arena")
)
if _SKILLS_DIR.is_dir():
    image = image.add_local_dir(str(_SKILLS_DIR), remote_path="/opt/arena-skills")
if _TARGETS_DIR.is_dir():
    # The immutable Target Library ships with the deployment image (repository-backed;
    # never stored in the database).
    image = image.add_local_dir(str(_TARGETS_DIR), remote_path="/opt/arena-targets")

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
    env={
        "ARENA_SKILLS_ROOT": "/opt/arena-skills",
        "ARENA_TARGETS_DIR": "/opt/arena-targets",
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
