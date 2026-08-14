from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Iterator, Mapping, Protocol, Sequence, runtime_checkable

RowLike = Mapping[str, Any]


@runtime_checkable
class CursorLike(Protocol):
    rowcount: int

    def fetchone(self) -> Any | None: ...
    def fetchall(self) -> list[Any]: ...
    def __iter__(self) -> Iterator[Any]: ...


@runtime_checkable
class ConnectionLike(Protocol):
    backend: str

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> CursorLike: ...
    def executemany(self, sql: str, parameters: Any) -> CursorLike: ...
    def copy_rows(self, table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> int: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


class ErrorCategory(str, Enum):
    TRANSIENT = "transient_lock_or_serialization"
    CONNECTION_LOSS = "connection_loss"
    CONSTRAINT = "constraint_error"
    PERMANENT = "permanent_sql_error"


def classify_database_error(error: BaseException) -> ErrorCategory:
    if isinstance(error, sqlite3.IntegrityError):
        return ErrorCategory.CONSTRAINT
    if isinstance(error, sqlite3.OperationalError):
        message = str(error).lower()
        if "locked" in message or "busy" in message:
            return ErrorCategory.TRANSIENT
        if "closed" in message or "unable to open" in message:
            return ErrorCategory.CONNECTION_LOSS
        return ErrorCategory.PERMANENT
    sqlstate = getattr(error, "sqlstate", None)
    if sqlstate in {"40001", "40P01", "55P03"}:
        return ErrorCategory.TRANSIENT
    if isinstance(sqlstate, str) and sqlstate.startswith("08"):
        return ErrorCategory.CONNECTION_LOSS
    if isinstance(sqlstate, str) and sqlstate.startswith("23"):
        return ErrorCategory.CONSTRAINT
    return ErrorCategory.PERMANENT


class HybridRow(Mapping[str, Any]):
    """A DB-API row supporting both mapping keys and integer offsets."""

    def __init__(self, values: Sequence[Any], columns: Sequence[str]):
        self._values = tuple(values)
        self._columns = tuple(columns)
        self._mapping = dict(zip(self._columns, self._values, strict=True))

    def __getitem__(self, key: str | int) -> Any:
        return self._values[key] if isinstance(key, int) else self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._values)


def _postgres_sql(sql: str) -> str:
    """Convert the project's qmark parameters without touching quoted text."""
    output: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            output.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    output.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"'}:
            quote = char
            output.append(char)
        elif char == "?":
            output.append("%s")
        else:
            output.append(char)
        index += 1
    return "".join(output)


class PostgresCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor
        self.rowcount = cursor.rowcount

    def _row(self, row: Sequence[Any] | None) -> HybridRow | None:
        if row is None:
            return None
        columns = [column.name for column in self._cursor.description]
        return HybridRow(row, columns)

    def fetchone(self) -> HybridRow | None:
        return self._row(self._cursor.fetchone())

    def fetchall(self) -> list[HybridRow]:
        return [self._row(row) for row in self._cursor.fetchall()]  # type: ignore[misc]

    def __iter__(self) -> Iterator[HybridRow]:
        for row in self._cursor:
            converted = self._row(row)
            assert converted is not None
            yield converted


class PostgresConnection:
    backend = "postgresql"

    def __init__(self, connection: Any, release: Any, metrics: "DatabaseMetrics"):
        self._connection = connection
        self._release = release
        self.metrics = metrics
        self._closed = False

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> PostgresCursor:
        converted = _postgres_sql(sql)
        cursor = (
            self._connection.execute(converted, parameters)
            if parameters else self._connection.execute(converted)
        )
        return PostgresCursor(cursor)

    def executemany(self, sql: str, parameters: Any) -> PostgresCursor:
        cursor = self._connection.cursor()
        cursor.executemany(_postgres_sql(sql), parameters)
        return PostgresCursor(cursor)

    def copy_rows(self, table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
        identifiers = (table, *columns)
        if any(not identifier.replace("_", "").isalnum() for identifier in identifiers):
            raise ValueError("COPY identifiers must contain only letters, numbers, and underscores")
        copied = 0
        with self._connection.cursor() as cursor:
            statement = f"COPY {table} ({','.join(columns)}) FROM STDIN"
            with cursor.copy(statement) as stream:
                for row in rows:
                    stream.write_row(row)
                    copied += 1
        return copied

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._release(self._connection)

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> None:
        if exc is None:
            self.commit()
        else:
            self.rollback()
        self.close()


class SQLiteConnection:
    backend = "sqlite"

    def __init__(self, connection: sqlite3.Connection, metrics: "DatabaseMetrics"):
        self._connection = connection
        self.metrics = metrics
        self._closed = False

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self._connection.execute(sql, parameters)

    def executemany(self, sql: str, parameters: Any) -> sqlite3.Cursor:
        return self._connection.executemany(sql, parameters)

    def copy_rows(self, table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
        identifiers = (table, *columns)
        if any(not identifier.replace("_", "").isalnum() for identifier in identifiers):
            raise ValueError("bulk-insert identifiers must contain only letters, numbers, and underscores")
        materialized = list(rows)
        placeholders = ",".join("?" for _ in columns)
        self._connection.executemany(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", materialized,
        )
        return len(materialized)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._connection.close()
            self.metrics.release()

    def __enter__(self) -> "SQLiteConnection":
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> None:
        if exc is None:
            self.commit()
        else:
            self.rollback()
        self.close()


@dataclass
class DatabaseMetrics:
    checkout_wait_ms: float = 0.0
    checkouts: int = 0
    retries: int = 0
    transaction_ms: float = 0.0
    connections_in_use: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def checkout(self, waited_ms: float) -> None:
        with self._lock:
            self.checkout_wait_ms += waited_ms
            self.checkouts += 1
            self.connections_in_use += 1

    def release(self) -> None:
        with self._lock:
            self.connections_in_use -= 1

    def transaction(self, elapsed_ms: float) -> None:
        with self._lock:
            self.transaction_ms += elapsed_ms

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            return {
                "pool_wait_milliseconds": round(self.checkout_wait_ms, 3),
                "database_checkouts": self.checkouts,
                "database_retries": self.retries,
                "transaction_milliseconds": round(self.transaction_ms, 3),
                "connections_in_use": self.connections_in_use,
            }


class Database:
    """Small backend boundary; pipeline code continues to use DB-API calls."""

    def __init__(self, config: Any):
        self.backend = config.db_backend
        self.sqlite_path = config.db_path
        self.metrics = DatabaseMetrics()
        self._pool: Any | None = None
        if self.backend == "postgresql":
            try:
                from psycopg_pool import ConnectionPool
            except ImportError as error:  # pragma: no cover - depends on optional service
                raise RuntimeError("PostgreSQL backend requires psycopg and psycopg_pool") from error
            url = config.database_url()
            self._pool = ConnectionPool(
                conninfo=url, min_size=0, max_size=config.db_pool_max,
                timeout=config.db_checkout_timeout, open=True,
            )

    def connect(self) -> ConnectionLike:
        started = time.monotonic()
        if self.backend == "sqlite":
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.sqlite_path, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            self.metrics.checkout((time.monotonic() - started) * 1000)
            return SQLiteConnection(connection, self.metrics)
        assert self._pool is not None
        raw = self._pool.getconn()
        self.metrics.checkout((time.monotonic() - started) * 1000)

        def release(connection: Any) -> None:
            if connection.info.transaction_status.name != "IDLE":
                connection.rollback()
            self.metrics.release()
            self._pool.putconn(connection)

        return PostgresConnection(raw, release, self.metrics)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()

    def migrate(self) -> None:
        if self.backend == "sqlite":
            from .db import initialize
            initialize(self.sqlite_path)
            return
        root = Path(__file__).resolve().parents[2]
        connection = self.connect()
        try:
            exists = connection.execute(
                """SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema='public'"""
            ).fetchone()[0]
            if not exists:
                connection.execute(
                    (root / "migrations/postgresql/0008_schema.sql").read_text(encoding="utf-8")
                )
                connection.execute(
                    (root / "migrations/postgresql/0008_post_load.sql").read_text(encoding="utf-8")
                )
                connection.execute("INSERT INTO schema_meta(version) VALUES (8)")
                connection.commit()
            applied = {row[0] for row in connection.execute("SELECT version FROM schema_meta")}
            for migration in sorted((root / "migrations/postgresql").glob("[0-9][0-9][0-9][0-9]_*.sql")):
                version = int(migration.name.split("_", 1)[0])
                if version <= 8 or version in applied:
                    continue
                connection.execute(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_meta(version) VALUES (?) ON CONFLICT(version) DO NOTHING",
                    (version,),
                )
                connection.commit()
        finally:
            connection.close()


@contextmanager
def transaction(connection: ConnectionLike, *, immediate: bool = False) -> Iterator[ConnectionLike]:
    backend = getattr(connection, "backend", "sqlite")
    started = time.monotonic()
    connection.execute("BEGIN IMMEDIATE" if immediate and backend == "sqlite" else "BEGIN")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        metrics = getattr(connection, "metrics", None)
        if metrics is not None:
            metrics.transaction((time.monotonic() - started) * 1000)
