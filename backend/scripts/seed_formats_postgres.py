#!/usr/bin/env python3
"""Seed the playable battle formats into Postgres (Neon).

A fresh Neon database has an empty ``formats`` table, so ``GET /formats`` returns
nothing and no battle can be launched. Production was originally seeded out of
band; this script makes a brand-new Postgres database usable for local / Cloud
Agent development by writing the git source-of-truth formats
(``agent_arena.seed_formats.ALL_FORMATS``) directly through the persistence
repository.

Idempotent: existing formats are updated in place (name/engine/config), missing
ones are created. Requires ``DATABASE_URL`` and ``PERSISTENCE_BACKEND=postgres``.

    DATABASE_URL=... PERSISTENCE_BACKEND=postgres \
        backend/.venv/bin/python -m scripts.seed_formats_postgres
"""

from __future__ import annotations

import sys


def seed() -> int:
    from agent_arena.persistence import repositories
    from agent_arena.persistence.session import session_scope
    from agent_arena.seed_formats import ALL_FORMATS

    written = 0
    with session_scope() as session:
        for cfg in ALL_FORMATS:
            fmt_id = cfg["id"]
            existing = repositories.formats.format_get(session, fmt_id)
            if existing is None:
                repositories.formats.format_create(
                    session,
                    id=fmt_id,
                    name=cfg["name"],
                    engine=cfg["engine"],
                    config=cfg,
                )
            else:
                repositories.formats.format_update(
                    session,
                    fmt_id,
                    name=cfg["name"],
                    engine=cfg["engine"],
                    config=cfg,
                )
            written += 1
    return written


def main() -> None:
    from agent_arena.persistence.service import using_postgres

    if not using_postgres():
        print("PERSISTENCE_BACKEND is not postgres; refusing to seed.", file=sys.stderr)
        raise SystemExit(2)
    count = seed()
    print(f"Seeded {count} formats into Postgres.")


if __name__ == "__main__":
    main()
