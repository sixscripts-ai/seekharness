#!/usr/bin/env python3
"""Seed the 63 canonical skills from catalog.v0.3.yaml into the Neon PostgreSQL skills table.

Idempotent: Uses on_conflict_do_nothing so running this multiple times never overwrites
active skill Elo or usage analytics.
"""
from __future__ import annotations

import sys
from pathlib import Path
import yaml

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from agent_arena.persistence import session_scope
from agent_arena.persistence.models import SkillRecord
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func


def main() -> int:
    catalog_path = backend_dir / "agent_arena" / "skills" / "catalog.v0.3.yaml"
    if not catalog_path.is_file():
        print(f"Error: Catalog file not found at {catalog_path}", file=sys.stderr)
        return 1

    with open(catalog_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    catalog_skills = data.get("skills", [])
    print(f"Loaded {len(catalog_skills)} skills from {catalog_path.name}")

    rows_to_insert = []
    for s in catalog_skills:
        skill_id = s.get("id") or s.get("name")
        if not skill_id:
            continue

        tier = s.get("tier")
        if not tier and s.get("roles"):
            tier = s["roles"][0]
        if not tier:
            tier = "general"

        tags = list(dict.fromkeys(s.get("domains", []) + s.get("roles", [])))

        rows_to_insert.append({
            "skill": skill_id,
            "elo": 1000.0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "uses": 0,
            "success_rate": 0.0,
            "tier": tier,
            "tags": tags,
        })

    print(f"Prepared {len(rows_to_insert)} SkillRecord entries for insertion...")

    with session_scope() as session:
        for row in rows_to_insert:
            stmt = (
                pg_insert(SkillRecord)
                .values(**row)
                .on_conflict_do_nothing(constraint="skills_pkey")
            )
            session.execute(stmt)

    # Verification query
    with session_scope() as session:
        total = session.scalar(select(func.count()).select_from(SkillRecord))
        sample = session.scalars(select(SkillRecord).order_by(SkillRecord.skill).limit(5)).all()

    print(f"Successfully seeded Neon database!")
    print(f"Total skills in 'skills' table now: {total}")
    print("\nSample records:")
    for rec in sample:
        print(f" - {rec.skill} (Elo: {rec.elo}, Tier: {rec.tier}, Tags: {rec.tags})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
