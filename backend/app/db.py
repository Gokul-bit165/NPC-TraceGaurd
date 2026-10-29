"""Database setup. SQLite for the demo, any SQLAlchemy URL (MySQL / PostgreSQL) for deployment."""
from __future__ import annotations

import os
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("TRACEGUARD_DB", "sqlite:///./traceguard.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def get_engine_kwargs(url: str) -> dict:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL / MySQL connection pool settings for multi-worker deployment
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = int(os.environ.get("TRACEGUARD_DB_POOL_SIZE", "15"))
        kwargs["max_overflow"] = int(os.environ.get("TRACEGUARD_DB_MAX_OVERFLOW", "25"))
        kwargs["pool_recycle"] = int(os.environ.get("TRACEGUARD_DB_POOL_RECYCLE", "1800"))
    return kwargs

_kwargs = get_engine_kwargs(DATABASE_URL)
engine = create_engine(DATABASE_URL, future=True, **_kwargs)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):  # faster writes and concurrent readers for the demo database
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(engine)


def reset_db() -> None:
    from . import models  # noqa: F401
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from .engine.counter import reset_cross_user_counter
    reset_cross_user_counter()
