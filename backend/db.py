"""Database engine, session factory, and the declarative Base.

The same ORM code runs on SQLite (local/tests) and PostgreSQL (docker) — only
DATABASE_URL changes. We chose SQLAlchemy + a URL switch over hardcoding Postgres
so the vertical slice is runnable and testable with no external services; it does
not yet wire pgvector, which the Phase 4 LLM layer will need.
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import DATABASE_URL

# SQLite must allow cross-thread use under FastAPI's threadpool; Postgres ignores this.
_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, future=True
)


class Base(DeclarativeBase):
    """Declarative base for all ORM tables."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
