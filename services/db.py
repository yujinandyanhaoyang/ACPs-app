from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_PATH = _PROJECT_ROOT / "data" / "recommendation_runtime.db"
_DEFAULT_DB_URL = f"sqlite:///{_DEFAULT_SQLITE_PATH}"
_DEFAULT_MIGRATIONS_DIR = _PROJECT_ROOT / "migrations"


class DatabaseConfigError(ValueError):
    pass


class UnsupportedDatabaseBackendError(NotImplementedError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_database_url() -> str:
    return str(os.getenv("RECSYS_DB_URL") or os.getenv("DATABASE_URL") or _DEFAULT_DB_URL).strip()


def _sqlite_path_from_url(db_url: str) -> Path:
    if db_url.startswith("sqlite:///"):
        raw = db_url.replace("sqlite:///", "", 1)
        return Path(raw)
    if db_url.startswith("sqlite://"):
        raw = db_url.replace("sqlite://", "", 1)
        return Path(raw)
    if "://" not in db_url:
        return Path(db_url)
    raise UnsupportedDatabaseBackendError(
        "Only sqlite backends are runnable in this local implementation. "
        "Use RECSYS_DB_URL=sqlite:///... for runtime, while postgres URLs are reserved for future adapter wiring."
    )


def get_sqlite_path(db_url: Optional[str] = None) -> Path:
    url = db_url or resolve_database_url()
    return _sqlite_path_from_url(url)


def connect_sqlite(db_url: Optional[str] = None) -> sqlite3.Connection:
    sqlite_path = get_sqlite_path(db_url)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(db_url: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    conn = connect_sqlite(db_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _already_applied(conn: sqlite3.Connection, version: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ? LIMIT 1",
        (version,),
    ).fetchone()
    return row is not None


def run_migrations(
    db_url: Optional[str] = None,
    migrations_dir: Optional[Path] = None,
) -> list[str]:
    mig_dir = migrations_dir or _DEFAULT_MIGRATIONS_DIR
    mig_dir.mkdir(parents=True, exist_ok=True)

    sql_files = sorted(path for path in mig_dir.glob("*.sql") if path.is_file())
    applied: list[str] = []

    with transaction(db_url) as conn:
        _ensure_migration_table(conn)
        for sql_file in sql_files:
            version = sql_file.name
            if _already_applied(conn, version):
                continue
            sql = sql_file.read_text(encoding="utf-8")
            if not sql.strip():
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, utc_now()),
            )
            applied.append(version)

    return applied


if __name__ == "__main__":
    versions = run_migrations()
    if versions:
        print("Applied migrations:")
        for version in versions:
            print(f"- {version}")
    else:
        print("No pending migrations.")
