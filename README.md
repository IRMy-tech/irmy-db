# irmy-db

Async PostgreSQL access for IRMy Python services: a SQLAlchemy 2 async engine
(asyncpg) with a session factory, schema selection via `search_path`, a real
database healthcheck and Prometheus metrics for the connection pool and query
durations.

```bash
pip install irmy-db
```

Requires Python 3.12+. The import package is `irmy_db`.

## Usage

```python
import logging

from sqlalchemy import text
from irmy_db import InitializeDB

logger = logging.getLogger("my-service")

db = InitializeDB(
    connection_string="postgresql+asyncpg://user:password@localhost:5432/irmy",
    postgres_schema="public",
    logger=logger,
)


async def do_something():
    async with db.get_session() as session:
        await session.execute(text("SELECT 1"))


async def healthcheck() -> bool:
    # Runs SELECT 1 against the database, False on error or after 5 seconds.
    return await db.get_health(timeout=5.0)


async def shutdown():
    # Do not forget to close the connection pool.
    await db.disconnect_from_db()
```

`InitializeDB` arguments:

| Argument | Default | Description |
|---|---|---|
| `connection_string` | — | SQLAlchemy async URL (`postgresql+asyncpg://…`) |
| `postgres_schema` | — | Schema set as `search_path` for every connection |
| `logger` | — | `logging.Logger` |
| `pool` | `3` | Pool size |
| `pool_overflow` | `12` | Connections allowed above the pool size |
| `enable_metrics` | `True` | Register Prometheus pool and query metrics |

## Metrics

| Metric | Type | Description |
|---|---|---|
| `db_pool_size` | Gauge | Connection pool size |
| `db_pool_checkedin` | Gauge | Checked-in (idle) connections |
| `db_pool_checkedout` | Gauge | Checked-out (in use) connections |
| `db_pool_overflow` | Gauge | Overflow connections |
| `db_query_duration_seconds` | Histogram, label `operation` | Query duration by SQL verb (`select`, `insert`, …) |

The pool gauges are process-wide: use one `InitializeDB` per process.
