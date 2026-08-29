"""Load + seed the targets library from targets/**/*.yaml into Appwrite.

Collection: `targets`. Each target carries target_code, test_code, objectives,
limits, scoring, recommended_skills, category, tier, format, and a `tier`
used by skills_registry difficulty offsets.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from . import db
from appwrite.query import Query

TARGETS_ROOT = Path(__file__).resolve().parents[2] / "targets"

SCHEMA_FIELDS = (
    "id",
    "category",
    "format",
    "tier",
    "name",
    "description",
    "recommended_skills",
    "target_code",
    "test_code",
    "objectives",
    "limits",
    "scoring",
)


def load_targets(root: Path | None = None) -> list[dict]:
    """Load and validate all legacy YAML targets. Raises ValueError on bad files."""
    if yaml is None:
        raise RuntimeError("PyYAML required to load targets (pip install pyyaml)")
    base = root or TARGETS_ROOT
    targets: list[dict] = []
    for path in sorted(base.rglob("*.yaml")):
        # Skip Target Library v1 bundle packages
        if "library" in path.parts:
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: target must be a YAML mapping")
        missing = [
            f for f in ("id", "category", "target_code", "test_code") if not raw.get(f)
        ]
        if missing:
            raise ValueError(f"{path}: missing required fields {missing}")
        allowed = set(SCHEMA_FIELDS)
        extra = set(raw) - allowed
        if extra:
            raise ValueError(f"{path}: unknown fields {sorted(extra)}")
        targets.append(raw)
    return targets


def seed_targets(root: Path | None = None) -> int:
    databases = db.get_databases()
    database_id = db.get_database_id()
    count = 0
    for t in load_targets(root):
        res = databases.list_documents(
            database_id,
            "targets",
            queries=[Query.equal("id", t["id"]), Query.limit(1)],
        )
        payload = {"id": t["id"], "config": json.dumps(t)}
        if res.documents:
            databases.update_document(
                database_id, "targets", res.documents[0].id, payload
            )
        else:
            databases.create_document(database_id, "targets", "unique()", payload)
        count += 1
    return count


def target_for_format(
    databases, database_id, format_id: str, category: str | None = None
):
    """Pick a target for a battle format (simple first-match by format name or category)."""
    res = databases.list_documents(
        database_id,
        "targets",
        queries=[Query.limit(100)],
    )
    docs = res.documents
    for d in docs:
        cfg = json.loads(d.data["config"])
        if format_id and cfg.get("format") == format_id:
            return cfg
    if category:
        for d in docs:
            cfg = json.loads(d.data["config"])
            if cfg.get("category") == category:
                return cfg
    return docs[0].data and json.loads(docs[0].data["config"]) if docs else None
