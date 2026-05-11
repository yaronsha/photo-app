"""Lazy engine factory and SQLite-specific PRAGMA wiring.

Engines are cached by URL in a module-level dict so tests can swap config
between cases via `dispose_engines()`. The default URL is derived from
`get_settings().db_path`, but `DATABASE_URL` env var (read by Settings)
overrides it — which is how an in-memory engine (sqlite:///:memory:) or
a Postgres engine can be selected later.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from ..config import get_settings

_engines: dict[str, Engine] = {}


def _default_url() -> str:
    """Resolve the database URL.

    Precedence: explicit `DATABASE_URL` env var > sqlite from
    `Settings.db_path`.  Reading the env each call keeps the override
    cheap; the engine itself is still cached by URL below.
    """
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{settings.db_path}"


def get_engine(url: str | None = None) -> Engine:
    if url is None:
        url = _default_url()
    cached = _engines.get(url)
    if cached is not None:
        return cached

    if url.startswith("sqlite"):
        connect_args: dict = {"check_same_thread": False, "timeout": 30}
    else:
        connect_args = {}

    engine = create_engine(url, connect_args=connect_args)
    _engines[url] = engine
    return engine


def dispose_engines() -> None:
    """Close + drop all cached engines.  Tests use this between cases."""
    for engine in list(_engines.values()):
        try:
            engine.dispose()
        except Exception:
            pass
    _engines.clear()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: D401
    """Apply WAL + FK PRAGMAs only for sqlite connections.

    We sniff the dbapi class' module rather than touching the engine
    (which isn't directly accessible inside a connect-event listener that
    is registered against the abstract `Engine` class).
    """
    mod = type(dbapi_connection).__module__ or ""
    if not mod.startswith("sqlite3") and not mod.startswith("pysqlite"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
