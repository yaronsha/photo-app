"""Session helpers — factory + auto-committing context manager."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from .engine import get_engine


def SessionLocal() -> Session:
    """Return a new Session bound to the current engine.

    Uses a function (not a module-level sessionmaker) so the engine can
    change between tests via `dispose_engines()`.
    """
    return Session(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Context manager: commit on clean exit, rollback on exception."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
