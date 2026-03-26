from __future__ import annotations

import argparse
import json

from services.user_profile_store import profile_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply local retention policy for recommendation runs and task logs")
    parser.add_argument("--keep-runs-per-user", type=int, default=100)
    parser.add_argument("--keep-logs-per-task", type=int, default=200)
    args = parser.parse_args()

    result = profile_store.prune_retention(
        keep_latest_runs_per_user=max(1, args.keep_runs_per_user),
        keep_latest_logs_per_task=max(1, args.keep_logs_per_task),
    )
    print(json.dumps({"pruned": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
