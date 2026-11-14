from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(database_url: str, **kwargs: Any) -> Engine:
    """Create an engine with per-database safety settings. Used by the app AND by Alembic.

    SQLite needs: its folder to exist, cross-thread use allowed (FastAPI runs sync routes in a
    thread pool), and foreign keys switched ON (off by default, which would silently disable
    ON DELETE CASCADE).
    """
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15}, **kwargs)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(url, pool_pre_ping=True, **kwargs)


@lru_cache
def get_engine() -> Engine:
    return build_engine(get_settings().database_url)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
