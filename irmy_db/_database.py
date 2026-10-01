import asyncio
from contextlib import asynccontextmanager
from logging import Logger
from typing import AsyncGenerator

from prometheus_client import Gauge, Histogram
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import QueuePool
import time


_pool_size = Gauge("db_pool_size", "Connection pool size")
_pool_checked_in = Gauge("db_pool_checkedin", "Checked in connections")
_pool_checked_out = Gauge("db_pool_checkedout", "Checked out connections")
_pool_overflow = Gauge("db_pool_overflow", "Pool overflow connections")

_query_duration = Histogram(
    "db_query_duration_seconds",
    "DB query duration",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)


class InitializeDB:
    def __init__(self, connection_string: str, postgres_schema: str, logger: Logger,
        pool: int = 3, pool_overflow: int = 12, enable_metrics: bool = True
    ):
        self._logger = logger
        self._enable_metrics = enable_metrics
        self._logger.info("Initializing database connection...")

        self._engine = create_async_engine(
            connection_string,
            pool_size=pool,
            max_overflow=pool_overflow,
            connect_args={"server_settings": {"search_path": postgres_schema}},
            pool_pre_ping=True,
        )
        self._async_session_local = async_sessionmaker(bind=self._engine, expire_on_commit=False)
        self._disposed = False

        if self._enable_metrics:
            self._setup_metrics()
            self._logger.info("SQLAlchemy Prometheus metrics enabled.")

    def _setup_metrics(self) -> None:
        sync_engine = self._engine.sync_engine

        def _update_pool_metrics() -> None:
            pool: QueuePool = sync_engine.pool  # type: ignore[assignment]
            _pool_size.set(pool.size())
            _pool_checked_in.set(pool.checkedin())
            _pool_checked_out.set(pool.checkedout())
            _pool_overflow.set(pool.overflow())

        @event.listens_for(sync_engine, "connect")
        def on_connect(dbapi_conn, connection_record):
            _update_pool_metrics()

        @event.listens_for(sync_engine, "checkout")
        def on_checkout(dbapi_conn, connection_record, connection_proxy):
            _update_pool_metrics()

        @event.listens_for(sync_engine, "checkin")
        def on_checkin(dbapi_conn, connection_record):
            _update_pool_metrics()

        @event.listens_for(sync_engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info["query_start_time"] = time.perf_counter()

        @event.listens_for(sync_engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            start = conn.info.get("query_start_time")
            if start is None:
                return
            duration = time.perf_counter() - start
            stripped = statement.strip()
            if stripped.startswith("/*"):
                stripped = stripped.split("*/", 1)[-1].strip()
            operation = stripped.split()[0].lower() if stripped else "unknown"
            _query_duration.labels(operation=operation).observe(duration)

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._async_session_local() as session:
            yield session

    async def disconnect_from_db(self) -> None:
        self._disposed = True
        await self._engine.dispose()

    async def get_health(self, timeout: float = 5.0) -> bool:
        """True if the database answers ``SELECT 1`` within ``timeout`` seconds."""
        if self._disposed:
            return False
        try:
            async with asyncio.timeout(timeout):
                async with self._engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            return True
        except TimeoutError:
            self._logger.error(f"Database healthcheck timed out after {timeout}s")
            return False
        except Exception as e:
            self._logger.error(f"Error during healthcheck of database: {e}")
            return False