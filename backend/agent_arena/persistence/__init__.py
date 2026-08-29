"""Agent Arena PostgreSQL persistence layer (Neon).

Coexists with the Appwrite implementation (agent_arena/db.py) during the
migration. Nothing in the runtime switches to these models/repositories yet;
this package is the Phase 1 foundation plus the repository API surface.
"""

from .engine import database_url, engine, redacted_host
from .session import SessionLocal, session_scope

__all__ = [
    "database_url",
    "engine",
    "redacted_host",
    "SessionLocal",
    "session_scope",
]
