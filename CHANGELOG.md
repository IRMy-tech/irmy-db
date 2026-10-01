# Changelog
## 1.0.0
Initial release.

* `InitializeDB` — SQLAlchemy 2 async engine (asyncpg) with a session factory
  (`get_session()`), schema selection through `search_path` and pool settings.
* `get_health()` — async healthcheck that runs `SELECT 1` against the database
  with a timeout.
* Prometheus metrics for the connection pool and query durations.
