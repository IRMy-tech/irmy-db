import asyncio
import logging
from contextlib import asynccontextmanager

import pytest

from irmy_db import InitializeDB

_LOGGER = logging.getLogger("irmy-db-test")


@pytest.fixture
def db():
    # Nothing connects until a query runs, so no database is needed to construct it.
    return InitializeDB(
        connection_string="postgresql+asyncpg://u:p@127.0.0.1:1/irmy",
        postgres_schema="public",
        logger=_LOGGER,
        enable_metrics=False,
    )


class _FakeConnection:
    def __init__(self, delay: float = 0.0, error: Exception | None = None):
        self._delay = delay
        self._error = error
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error


class _FakeEngine:
    def __init__(self, connection: _FakeConnection):
        self._connection = connection

    @asynccontextmanager
    async def connect(self):
        yield self._connection


async def test_health_runs_select_1(db):
    connection = _FakeConnection()
    db._engine = _FakeEngine(connection)
    assert await db.get_health() is True
    assert connection.statements == ["SELECT 1"]


async def test_health_false_on_database_error(db):
    db._engine = _FakeEngine(_FakeConnection(error=OSError("connection refused")))
    assert await db.get_health() is False


async def test_health_false_on_timeout(db):
    db._engine = _FakeEngine(_FakeConnection(delay=1.0))
    assert await db.get_health(timeout=0.05) is False


async def test_health_false_when_unreachable(db):
    assert await db.get_health(timeout=2.0) is False


async def test_health_false_after_disconnect(db):
    await db.disconnect_from_db()
    assert await db.get_health() is False
