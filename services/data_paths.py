from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DATA_ROOT = PROJECT_ROOT / "data" / "raw"

# Keep config loading centralized so scripts and tests resolve the same raw-data root.
load_dotenv(PROJECT_ROOT / ".env")


def get_raw_data_root() -> Path:
    configured_root = os.getenv("RAW_DATA_ROOT", "").strip()
    if configured_root:
        return Path(configured_root).expanduser()
    return DEFAULT_RAW_DATA_ROOT


def get_raw_data_path(*parts: str) -> Path:
    return get_raw_data_root().joinpath(*parts)