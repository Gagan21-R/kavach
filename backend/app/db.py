from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import BACKEND_DIR, get_settings


class UTCDateTime(TypeDecorator):
    """Stores UTC, always returns timezone-aware datetimes (SQLite drops tzinfo otherwise)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> str:
    """Render and Heroku hand out postgres:// URLs; SQLAlchemy needs the psycopg 3 driver named explicitly.
    A relative SQLite path means backend/, so the server, Alembic and scripts share one file from any folder."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    path = url.removeprefix("sqlite:///") if url.startswith("sqlite:///") else None
    if path and path != ":memory:" and not Path(path).is_absolute():
        return "sqlite:///" + (BACKEND_DIR / path).resolve().as_posix()
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    kwargs = {"pool_pre_ping": True} if url.startswith("postgresql") else {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
