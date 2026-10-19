"""Database engine and session handling (SQLAlchemy 2.0, PostgreSQL)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    # pool_pre_ping drops dead connections instead of failing on first use.
    return create_engine(database_url, pool_pre_ping=True, future=True)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
