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

class _LazySessionMaker:
    """Lazy sessionmaker wrapper that delays engine initialization until first session access.

    This prevents module import from failing during CI test collection or tool discovery
    when DATABASE_URL is not yet populated.
    """

    def __init__(self):
        self._maker: sessionmaker[Session] | None = None

    def _get_maker(self) -> sessionmaker[Session]:
        if self._maker is None:
            self._maker = sessionmaker(
                bind=engine(), expire_on_commit=False, autoflush=False
            )
        return self._maker

    def __call__(self, **kwargs) -> Session:
        return self._get_maker()(**kwargs)

    def configure(self, **kwargs):
        return self._get_maker().configure(**kwargs)


SessionLocal = _LazySessionMaker()


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
