"""One-shot bootstrap for a fresh Appwrite Cloud project.

Creates collections/attributes (schema), indexes, and seeds formats + legacy
targets so the backend is fully usable against a brand-new project — the
"fresh piggy bank" migration path that bypasses the old project's exhausted
database-read quota.

Prereqs (Appwrite console, ~5 min):
  1. Create a project on https://cloud.appwrite.io (new account OK).
  2. Settings -> API keys -> Create: Databases (all) + Users (read) scopes.
  3. Note the Project ID, the API endpoint (e.g. https://sfo.cloud.appwrite.io),
     the API key, and the Database ID (create an empty database, note its ID).
  4. Put them in backend .env: APPWRITE_ENDPOINT / APPWRITE_PROJECT_ID /
     APPWRITE_API_KEY / APPWRITE_DATABASE_ID.

Usage (from backend/):
  ./.venv/bin/python scripts/bootstrap_appwrite.py

Idempotent: safe to re-run; seeds merge instead of overwriting.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    from agent_arena.config import settings
    from agent_arena.main import app
    from agent_arena.schema import ensure_schema
    from agent_arena.seed_formats import seed_formats
    from agent_arena.seed_targets import seed_targets
    from agent_arena.target_library import get_target_library
    from fastapi.testclient import TestClient

    try:
        s = settings()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print("Set APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, APPWRITE_DATABASE_ID in .env")
        return 1

    print(f"Target project : {s['APPWRITE_PROJECT_ID']}")
    print(f"Endpoint       : {s['APPWRITE_ENDPOINT']}")
    print(f"Database       : {s['APPWRITE_DATABASE_ID']}")
    print()

    print("[1/5] Ensuring schema (database + collections + attributes)...")
    ensure_schema()
    print("      schema OK")

    print("[2/5] Ensuring Appwrite indexes...")
    _load_module("ensure_indexes", HERE / "ensure_indexes.py").ensure()
    print("      indexes OK")

    print("[3/5] Seeding formats...")
    formats = seed_formats()
    print(f"      formats OK ({formats} documents)")

    print("[4/5] Seeding legacy targets...")
    targets = seed_targets()
    print(f"      legacy targets OK ({targets} documents)")

    print("[5/5] Smoke-checking the app in-process...")
    client = TestClient(app)
    health = client.get("/health")
    print(f"      GET /health    -> {health.status_code}")
    fmt = client.get("/formats")
    print(f"      GET /formats   -> {fmt.status_code} ({len(fmt.json()) if fmt.status_code == 200 else fmt.text} formats)")
    tgt = client.get("/targets")
    print(f"      GET /targets   -> {tgt.status_code} ({len(tgt.json()) if tgt.status_code == 200 else tgt.text} target bundles)")
    lib = get_target_library()
    print(f"      target library -> {lib.count()} bundles on filesystem")

    ok = health.status_code == 200 and fmt.status_code == 200 and tgt.status_code == 200
    print()
    if ok:
        print("BOOTSTRAP COMPLETE — the backend is fully provisioned against the new project.")
        print("Next: update frontend VITE_APPWRITE_ENDPOINT / VITE_APPWRITE_PROJECT_ID, rebuild, and redeploy.")
        return 0
    print("BOOTSTRAP INCOMPLETE — review the smoke results above (auth data like battles/providers is untouched).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
