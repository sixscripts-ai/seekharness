"""Idempotent live migration: flip selected formats onto the universal toolbelt.

The live Appwrite `formats` collection was seeded out-of-band and carries keys
that are not in git (role_missions, role_contracts, ...). A full reseed would
drop them, so this script surgically patches ONLY the flip keys
(universal / target_code / test_code / recommended_skills) on the named
formats, preserving every other live field.

Source of truth for the values is `seed_formats.ALL_FORMATS` (i.e. the git
FORMAT_EXTRA entries), so this stays in sync with what a fresh seed would set.

Usage:
    python -m agent_arena.scripts.patch_universal_formats            # apply
    python -m agent_arena.scripts.patch_universal_formats --dry-run  # preview
"""

from __future__ import annotations

import json
import sys

from appwrite.query import Query

from .. import db
from ..seed_formats import ALL_FORMATS

# Formats to flip (by config name). Fighter roles come from each format's phases.
FLIP_FORMAT_NAMES = (
    "Debugging race",
    "Code review duel",
    "Injection agent vs hardened agent",
)

# Only these keys are overlaid onto the live config; everything else is kept.
PATCH_KEYS = (
    "universal",
    "target_code",
    "test_code",
    "recommended_skills",
    "role_missions",
    "role_test_code",
    "seed_solution_roles",
    "pick_per_battle",
    "outcome_markers",
    "objectives",
)


def _git_cfg_by_name(name: str) -> dict:
    for cfg in ALL_FORMATS:
        if cfg["name"] == name:
            return cfg
    raise KeyError(f"format not defined in git: {name!r}")


def patch_universal_formats(dry_run: bool = False) -> list[dict]:
    """Apply the flip keys to each named live format. Returns a per-format summary."""
    databases = db.get_databases()
    database_id = db.get_database_id()
    summary: list[dict] = []

    for name in FLIP_FORMAT_NAMES:
        git_cfg = _git_cfg_by_name(name)
        res = databases.list_documents(
            database_id,
            "formats",
            queries=[Query.equal("name", name), Query.limit(1)],
        )
        if not res.documents:
            summary.append({"name": name, "status": "missing"})
            continue

        doc = res.documents[0]
        try:
            live_cfg = json.loads(doc.data.get("config") or "{}")
        except (json.JSONDecodeError, TypeError):
            live_cfg = {}

        changed_keys = []
        merged = dict(live_cfg)
        for key in PATCH_KEYS:
            if key not in git_cfg:
                continue
            if merged.get(key) != git_cfg[key]:
                merged[key] = git_cfg[key]
                changed_keys.append(key)

        if not changed_keys:
            summary.append({"name": name, "status": "unchanged", "id": doc.id})
            continue

        if not dry_run:
            databases.update_document(
                database_id,
                "formats",
                doc.id,
                {"config": json.dumps(merged)},
            )
        summary.append(
            {
                "name": name,
                "status": "would-patch" if dry_run else "patched",
                "id": doc.id,
                "changed": changed_keys,
            }
        )

    return summary


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    dry_run = "--dry-run" in args
    results = patch_universal_formats(dry_run=dry_run)
    for r in results:
        detail = f" changed={r['changed']}" if r.get("changed") else ""
        print(f"{r['status']:12} {r['name']}{detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
