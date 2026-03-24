from __future__ import annotations

from services.db import run_migrations, resolve_database_url, get_sqlite_path


def main() -> int:
    db_url = resolve_database_url()
    versions = run_migrations(db_url=db_url)
    print(f"Database URL: {db_url}")
    try:
        print(f"SQLite path: {get_sqlite_path(db_url)}")
    except Exception:
        pass

    if versions:
        print("Applied migrations:")
        for version in versions:
            print(f"- {version}")
    else:
        print("No pending migrations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
