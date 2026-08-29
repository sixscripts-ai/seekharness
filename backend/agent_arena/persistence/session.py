"""Session management for the PostgreSQL persistence layer.

Sessions are task/request scoped: always obtained inside session_scope() (or
the equivalent FastAPI dependency) so the connection is returned to the pool
after every unit of work. Transactions commit on success and roll back on
exception.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker

from .engine import engine

SessionLocal = sessionmaker(bind=engine(), expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

    Commits on clean exit, rolls back on exception, and always closes the
    session so the connection returns to the pool.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
