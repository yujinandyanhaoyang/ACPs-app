from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "data"
DEFAULT_RAW_DATA_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DATA_ROOT = PROJECT_ROOT / "data" / "processed"

# Keep config loading centralized so scripts and tests resolve the same raw-data root.
load_dotenv(PROJECT_ROOT / ".env")


def get_raw_data_root() -> Path:
    configured_dataset_root = os.getenv("DATASET_ROOT", "").strip()
    if configured_dataset_root:
        return Path(configured_dataset_root).expanduser() / "raw"

    configured_root = os.getenv("RAW_DATA_ROOT", "").strip()
    if configured_root:
        return Path(configured_root).expanduser()
    return DEFAULT_RAW_DATA_ROOT


def get_raw_data_path(*parts: str) -> Path:
    return get_raw_data_root().joinpath(*parts)


def get_processed_data_root() -> Path:
    configured_dataset_root = os.getenv("DATASET_ROOT", "").strip()
    if configured_dataset_root:
        return Path(configured_dataset_root).expanduser() / "processed"

    configured_root = os.getenv("PROCESSED_DATA_ROOT", "").strip()
    if configured_root:
        return Path(configured_root).expanduser()
    return DEFAULT_PROCESSED_DATA_ROOT


def get_processed_data_path(*parts: str) -> Path:
    return get_processed_data_root().joinpath(*parts)