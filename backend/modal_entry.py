import os
from pathlib import Path

import modal

_BASE_DIR = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _BASE_DIR / ".agents" / "skills"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_pyproject(str(Path(__file__).resolve().parent / "pyproject.toml"))
    .add_local_python_source("agent_arena")
)
if _SKILLS_DIR.is_dir():
    image = image.add_local_dir(str(_SKILLS_DIR), remote_path="/opt/arena-skills")

app = modal.App("agent-arena-backend", image=image)


@app.function(
    secrets=[modal.Secret.from_name("agent-arena-dotenv")],
    min_containers=1,
    env={
        "ARENA_SKILLS_ROOT": "/opt/arena-skills",
        "ARENA_BUILD_SHA": os.environ.get("ARENA_BUILD_SHA") or "unknown",
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
