from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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
