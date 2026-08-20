"""Idempotent live migration: overlay BattlePlan keys onto Auth system vs breaker.

The live Appwrite Auth document is a generic build_and_break config with
out-of-band keys (role_contracts, share_opponent, ...). A full reseed would
drop them. This script overlays ONLY the git FORMAT_EXTRA BattlePlan keys and
preserves every other live field.

Source of truth: seed_formats.ALL_FORMATS["Auth system vs breaker"].

Usage:
    python -m agent_arena.scripts.patch_auth_battle_plan            # apply
    python -m agent_arena.scripts.patch_auth_battle_plan --dry-run  # preview
"""

from __future__ import annotations

import json
import sys

from appwrite.query import Query

from .. import db
from ..seed_formats import ALL_FORMATS

FORMAT_NAME = "Auth system vs breaker"

PATCH_KEYS = (
    "battle_plan",
    "phase_plans",
    "target_code",
    "test_code",
    "role_test_code",
    "role_missions",
    "artifacts",
    "objectives",
    "recommended_skills",
    "pick_per_battle",
    "outcome_markers",
    "limits",
    "environment",
    "scoring",
    "max_tool_turns",
    "max_tool_steps",
    "tool_timeout",
    "exec_timeout_seconds",
    "race_max_tokens",
)


def _git_auth_cfg() -> dict:
    for cfg in ALL_FORMATS:
        if cfg["name"] == FORMAT_NAME:
            return cfg
    raise KeyError(f"format not defined in git: {FORMAT_NAME!r}")


def patch_auth_battle_plan(dry_run: bool = False) -> dict:
    git_cfg = _git_auth_cfg()
    databases = db.get_databases()
    database_id = db.get_database_id()
    res = databases.list_documents(
        database_id,
        "formats",
        queries=[Query.equal("name", FORMAT_NAME), Query.limit(1)],
    )
    if not res.documents:
        return {"name": FORMAT_NAME, "status": "missing"}

    doc = res.documents[0]
    try:
        live_cfg = json.loads(doc.data.get("config") or "{}")
    except (json.JSONDecodeError, TypeError):
        live_cfg = {}

    changed_keys: list[str] = []
    merged = dict(live_cfg)
    for key in PATCH_KEYS:
        if key not in git_cfg:
            continue
        if merged.get(key) != git_cfg[key]:
            merged[key] = git_cfg[key]
            changed_keys.append(key)

    if not changed_keys:
        return {"name": FORMAT_NAME, "status": "unchanged", "id": doc.id}

    if not dry_run:
        databases.update_document(
            database_id,
            "formats",
            doc.id,
            {"config": json.dumps(merged)},
        )
    return {
        "name": FORMAT_NAME,
        "status": "would-patch" if dry_run else "patched",
        "id": doc.id,
        "changed": changed_keys,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    dry_run = "--dry-run" in args
    result = patch_auth_battle_plan(dry_run=dry_run)
    detail = f" changed={result['changed']}" if result.get("changed") else ""
    print(f"{result['status']:12} {result['name']}{detail}")
    return 0 if result.get("status") != "missing" else 1


if __name__ == "__main__":
    raise SystemExit(main())
