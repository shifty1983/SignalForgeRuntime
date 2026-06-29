from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """
    Return the project root directory.

    Can be overridden with:
    - TRADING_PROJECT_ROOT
    - SIGNALFORGE_PROJECT_ROOT
    """
    override = os.getenv("TRADING_PROJECT_ROOT") or os.getenv("SIGNALFORGE_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    # src/common/paths.py -> src/common -> src -> project root
    return Path(__file__).resolve().parents[2]


def config_dir() -> Path:
    """
    Return the config directory.
    """
    override = os.getenv("TRADING_CONFIG_DIR") or os.getenv("SIGNALFORGE_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()

    return project_root() / "config"


def data_dir() -> Path:
    """
    Return the data directory.
    """
    override = os.getenv("TRADING_DATA_DIR") or os.getenv("SIGNALFORGE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    return project_root() / "data"


def raw_dir() -> Path:
    """
    Return the raw data directory.
    """
    return data_dir() / "raw"


def processed_dir() -> Path:
    """
    Return the processed data directory.
    """
    return data_dir() / "processed"


def metadata_dir() -> Path:
    """
    Return the metadata directory.
    """
    return data_dir() / "metadata"


def logs_dir() -> Path:
    """
    Return the logs directory.
    """
    return project_root() / "logs"


def reports_dir() -> Path:
    """
    Return the reports directory.
    """
    return project_root() / "reports"


def artifacts_dir() -> Path:
    """
    Return the artifacts directory.
    """
    return project_root() / "artifacts"


def cache_dir() -> Path:
    """
    Return the cache directory.
    """
    return project_root() / ".cache"


def catalog_dir() -> Path:
    """
    Return the metadata catalog directory.
    """
    return metadata_dir() / "catalog"


def raw_market_dir() -> Path:
    """
    Return the raw market data directory.
    """
    return raw_dir() / "market"


def raw_options_dir() -> Path:
    """
    Return the raw options data directory.
    """
    return raw_dir() / "options"


def raw_macro_dir() -> Path:
    """
    Return the raw macro data directory.
    """
    return raw_dir() / "macro"


def raw_fundamentals_dir() -> Path:
    """
    Return the raw fundamentals data directory.
    """
    return raw_dir() / "fundamentals"


def raw_sentiment_dir() -> Path:
    """
    Return the raw sentiment data directory.
    """
    return raw_dir() / "sentiment"


def ensure_dir(path: str | Path) -> Path:
    """
    Create a directory if it does not exist and return it as a Path.
    """
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent(path: str | Path) -> Path:
    """
    Create the parent directory for a file path and return the file path.
    """
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resolve_path(path: str | Path, *, base_dir: str | Path | None = None) -> Path:
    """
    Resolve a path relative to the project root or a provided base directory.

    Absolute paths are returned resolved.
    Relative paths are resolved against base_dir or project_root().
    """
    path = Path(path).expanduser()

    if path.is_absolute():
        return path.resolve()

    base = Path(base_dir).expanduser().resolve() if base_dir else project_root()
    return (base / path).resolve()

def ensure_project_dirs() -> None:
    """
    Ensure all core project directories exist.
    """
    directories = [
        data_dir(),
        raw_dir(),
        processed_dir(),
        metadata_dir(),
        catalog_dir(),
        logs_dir(),
        reports_dir(),
        artifacts_dir(),
        cache_dir(),
        raw_market_dir(),
        raw_macro_dir(),
        raw_options_dir(),
        raw_fundamentals_dir(),
        raw_sentiment_dir(),
    ]

    for directory in directories:
        ensure_dir(directory)
