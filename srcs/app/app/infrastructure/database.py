"""PostgreSQL access via psycopg (raw SQL, no ORM).

Production notes:
- A small connection pool is used instead of a fresh TCP/TLS
  connection per query.
- Connects with a timeout so a dead DB fails fast, not hangs.
- Callers use parameterised queries only (never string formatting
  of user input into SQL).
- No credentials are ever logged; errors carry no connection string.
"""

import logging
import os

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "postgresql://app:app@postgres:5432/audio_pipeline"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


class DatabaseConnection:
    """Pooled DB access: fetch_one / execute_query / is_healthy."""

    def __init__(
        self,
        database_url: str | None = None,
        min_size: int = 1,
        max_size: int = 10,
    ) -> None:
        self.database_url = database_url or get_database_url()
        self._pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=5,
            kwargs={"connect_timeout": 5, "row_factory": dict_row},
            open=False,
        )

    def open(self) -> None:
        if not self._pool.closed:
            return
        self._pool.open(wait=True)
        logger.info("Database connection pool opened (max_size=10)")

    def close(self) -> None:
        if not self._pool.closed:
            self._pool.close()
            logger.info("Database connection pool closed")

    def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        if self._pool.closed:
            self.open()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()

    def execute_query(self, query: str, params: tuple = ()) -> None:
        if self._pool.closed:
            self.open()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()

    # Backwards-friendly alias used internally.
    execute = execute_query

    def is_healthy(self) -> bool:
        try:
            if self._pool.closed:
                self.open()
            self.fetch_one("SELECT 1")
            return True
        except psycopg.Error:
            logger.warning("Database health check failed", exc_info=True)
            return False


# Shared instance. Pool is opened by the app lifespan (main.py),
# not at import time, so importing this module never touches the DB.
db = DatabaseConnection()
