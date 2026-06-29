from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from dotenv import load_dotenv

from src.common.paths import config_dir, resolve_path
from src.common.paths import project_root


ConfigDict = dict[str, Any]


def load_yaml(path: str | Path, *, required: bool = True) -> ConfigDict:
    """
    Load a YAML file and return a dictionary.

    If required=False and the file does not exist, returns an empty dict.
    """
    resolved_path = resolve_path(path, base_dir=config_dir())

    if not resolved_path.exists():
        if required:
            raise FileNotFoundError(f"YAML config file not found: {resolved_path}")
        return {}

    with resolved_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a dictionary at the top level: {resolved_path}")

    return dict(data)

def load_environment() -> None:
    candidate_paths = [
        project_root() / ".env",
        project_root().parent / ".env",
        Path.cwd() / ".env",
    ]

    for env_path in candidate_paths:
        if env_path.exists():
            load_dotenv(env_path, override=False)


load_environment()


def get_env_var(name: str, required: bool = True) -> str | None:
    value = os.getenv(name)

    if required and not value:
        raise ValueError(f"Missing required environment variable: {name}")

    return value


def get_fred_api_key() -> str:
    value = get_env_var("FRED_API_KEY", required=True)
    assert value is not None
    return value


def get_alpha_vantage_api_key() -> str:
    value = get_env_var("ALPHA_VANTAGE_API_KEY", required=True)
    assert value is not None
    return value


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> ConfigDict:
    """
    Recursively merge two dictionaries.

    Values from override take precedence over base.
    """
    merged: ConfigDict = dict(base)

    for key, override_value in override.items():
        base_value = merged.get(key)

        if isinstance(base_value, Mapping) and isinstance(override_value, Mapping):
            merged[key] = deep_merge(base_value, override_value)
        else:
            merged[key] = override_value

    return merged


def load_config(
    base_file: str | Path = "config.yaml",
    *,
    env: str | None = None,
    required: bool = True,
) -> ConfigDict:
    """
    Load the base config file and optionally merge an environment-specific config.

    Example:
        load_config()
        load_config(env="dev")

    This will load:
        config/config.yaml
        config/config.dev.yaml
    """
    base_config = load_yaml(base_file, required=required)

    selected_env = env or os.getenv("TRADING_ENV") or os.getenv("SIGNALFORGE_ENV")

    if not selected_env:
        return base_config

    base_path = Path(base_file)
    env_file = f"{base_path.stem}.{selected_env}{base_path.suffix}"

    env_config = load_yaml(env_file, required=False)

    return deep_merge(base_config, env_config)


def get_required(config: Mapping[str, Any], dotted_key: str) -> Any:
    """
    Retrieve a required nested config value using dot notation.

    Example:
        get_required(config, "sources.alpha_vantage.api_key_env")
    """
    current: Any = config

    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(f"Missing required config key: {dotted_key}")

        current = current[part]

    return current


def get_optional(
    config: Mapping[str, Any],
    dotted_key: str,
    default: Any = None,
) -> Any:
    """
    Retrieve an optional nested config value using dot notation.

    Example:
        get_optional(config, "storage.compression", default="zstd")
    """
    current: Any = config

    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default

        current = current[part]

    return current


def require_keys(config: Mapping[str, Any], keys: list[str]) -> None:
    """
    Validate that multiple required config keys exist.
    """
    missing: list[str] = []

    for key in keys:
        try:
            get_required(config, key)
        except KeyError:
            missing.append(key)

    if missing:
        formatted = ", ".join(missing)
        raise KeyError(f"Missing required config keys: {formatted}")
    def load_environment() -> None:
        env_path = project_root() / ".env"

        if env_path.exists():
            load_dotenv(env_path)


    load_environment()
