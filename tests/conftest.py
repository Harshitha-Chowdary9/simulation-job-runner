"""Test fixtures: a real, ephemeral PostgreSQL for the whole suite.

pgserver starts a throwaway PostgreSQL server in a temp directory (no Docker
needed), so tests exercise the same dialect and locking semantics as
production - including SELECT ... FOR UPDATE SKIP LOCKED, which SQLite
cannot do.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from simrunner.api import create_app
from simrunner.db import Base, make_engine, make_session_factory


@pytest.fixture(scope="session")
def pg_uri(tmp_path_factory):
    pgserver = pytest.importorskip("pgserver")
    srv = pgserver.get_server(str(tmp_path_factory.mktemp("pg")))
    import psycopg2
    conn = psycopg2.connect(srv.get_uri())
    conn.autocommit = True
    conn.cursor().execute("create database simrunner_test")
    conn.close()
    # Same socket host as the server URI, but the test database.
    base = srv.get_uri()  # postgresql://postgres:@/postgres?host=<dir>
    uri = base.replace("/postgres?", "/simrunner_test?")
    assert uri != base
    yield uri
    srv.cleanup()


@pytest.fixture()
def engine(pg_uri):
    eng = make_engine(pg_uri)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return make_session_factory(engine)


@pytest.fixture()
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture()
def client(pg_uri):
    eng = make_engine(pg_uri)
    Base.metadata.drop_all(eng)   # isolate every API test
    Base.metadata.create_all(eng)
    eng.dispose()
    return TestClient(create_app(pg_uri))
