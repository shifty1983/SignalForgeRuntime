from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl

try:
    from src.common.paths import raw_macro_dir
except Exception:  # pragma: no cover - local fallback for standalone execution
    def raw_macro_dir() -> Path:  # type: ignore[no-redef]
        return Path("data/raw/macro")

try:
    from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
except Exception:  # pragma: no cover - local fallback for standalone execution
    EXPLICIT_EXCLUSIONS: list[str] = [
        "broker_api_calls",
        "order_routing",
        "order_submission",
        "fills",
        "live_execution",
        "slippage_modeling",
        "automatic_close_orders",
        "automatic_roll_orders",
        "automatic_defense_orders",
        "automatic_strategy_changes",
        "automatic_parameter_changes",
        "automatic_pause_actions",
    ]


FRED_SERIES_IMPORT_SCHEMA_VERSION = "signalforge_fred_series_import.v1"
CLI_SUMMARY_SCHEMA_VERSION = "signalforge_fred_series_import_cli.v1"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

_SERIES_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,40}$")
_ID_KEYS = (
    "series_id",
    "fred_series_id",
    "fred_id",
    "id",
    "series",
)
_NAME_KEYS = ("name", "label", "title", "description")
_ROLE_KEYS = ("role", "metric", "column", "field", "target_column", "regime_component")
_GROUP_KEYS = ("group", "category", "component", "bucket")


@dataclass(frozen=True)
class SeriesConfig:
    series_id: str
    config_key: str
    series_group: str | None = None
    series_name: str | None = None
    series_role: str | None = None
    source_path: str | None = None
    raw_config: dict[str, Any] = field(default_factory=dict)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    start_date = _parse_required_date(args.start_date, "--start-date")
    end_date = _parse_required_date(args.end_date, "--end-date")
    warmup_start_date = _parse_optional_date(args.warmup_start_date, "--warmup-start-date")
    fetch_start_date = warmup_start_date or start_date

    if fetch_start_date > end_date:
        raise SystemExit("fetch start date cannot be after end date")
    if start_date > end_date:
        raise SystemExit("--start-date cannot be after --end-date")

    config_path = Path(args.config)
    output_dir = Path(args.output_dir) if args.output_dir else raw_macro_dir() / args.source_name
    artifact_dir = Path(args.artifact_dir)

    api_key = args.api_key or os.environ.get(args.api_key_env, "")
    if not api_key:
        raise SystemExit(
            f"FRED API key is required. Set {args.api_key_env} or pass --api-key."
        )

    config = _read_yaml(config_path)
    series_configs = _extract_series_configs(config)
    if not series_configs:
        raise SystemExit(f"No FRED series ids found in config: {config_path}")

    unique_series = _dedupe_series(series_configs)

    if args.replace_output:
        _remove_existing_parquet_files(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, Any]] = []
    series_results: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []
    blocker_items: list[dict[str, Any]] = []

    for index, item in enumerate(unique_series, start=1):
        try:
            observations = _fetch_observations(
                api_key=api_key,
                series_id=item.series_id,
                observation_start=fetch_start_date,
                observation_end=end_date,
                timeout_seconds=args.timeout_seconds,
                max_retries=args.max_retries,
            )
        except Exception as error:  # noqa: BLE001 - capture into artifact instead of crashing mid-batch
            blocker_items.append(
                {
                    "series_id": item.series_id,
                    "config_key": item.config_key,
                    "reason": str(error),
                }
            )
            series_results.append(
                _series_result(
                    item,
                    status="blocked",
                    row_count=0,
                    path=None,
                    first_date=None,
                    last_date=None,
                    warning=None,
                )
            )
            continue

        rows = [_normalize_observation(item, obs, start_date, end_date, fetch_start_date) for obs in observations]
        rows = [row for row in rows if row is not None]

        if not rows:
            warning = "FRED returned no usable observations in requested window"
            warning_items.append(
                {
                    "series_id": item.series_id,
                    "config_key": item.config_key,
                    "reason": warning,
                }
            )
            series_results.append(
                _series_result(
                    item,
                    status="needs_review",
                    row_count=0,
                    path=None,
                    first_date=None,
                    last_date=None,
                    warning=warning,
                )
            )
        else:
            path = output_dir / f"{_safe_file_stem(item.series_id)}.parquet"
            _write_series_parquet(path, rows)
            all_rows.extend(rows)
            series_results.append(
                _series_result(
                    item,
                    status="ready",
                    row_count=len(rows),
                    path=path,
                    first_date=min(row["date"] for row in rows),
                    last_date=max(row["date"] for row in rows),
                    warning=None,
                )
            )

        if args.sleep_seconds and index < len(unique_series):
            time.sleep(args.sleep_seconds)

    result_status = _status(all_rows=all_rows, blocker_items=blocker_items, warning_items=warning_items)
    result_path = artifact_dir / "signalforge_fred_series_import.json"
    summary_path = artifact_dir / "signalforge_fred_series_import_summary.json"

    result = {
        "artifact_type": "signalforge_fred_series_import",
        "schema_version": FRED_SERIES_IMPORT_SCHEMA_VERSION,
        "status": result_status,
        "is_ready": result_status in {"ready", "needs_review"} and bool(all_rows),
        "requires_manual_approval": True,
        "config_path": str(config_path),
        "source_name": args.source_name,
        "source": "fred",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "warmup_start_date": warmup_start_date.isoformat() if warmup_start_date else None,
        "fetch_start_date": fetch_start_date.isoformat(),
        "output_dir": str(output_dir),
        "artifact_dir": str(artifact_dir),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "series_requested_count": len(series_configs),
        "unique_series_count": len(unique_series),
        "series_success_count": sum(1 for item in series_results if item["status"] == "ready"),
        "series_needs_review_count": sum(1 for item in series_results if item["status"] == "needs_review"),
        "series_blocked_count": sum(1 for item in series_results if item["status"] == "blocked"),
        "macro_row_count": len(all_rows),
        "first_observation_date": min((row["date"] for row in all_rows), default=None),
        "last_observation_date": max((row["date"] for row in all_rows), default=None),
        "series_results": series_results,
        "warning_items": warning_items,
        "blocker_items": blocker_items,
        "macro_rows": all_rows,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    summary = _summary(result=result, result_path=result_path, summary_path=summary_path)

    _write_json(result_path, result)
    _write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if result_status == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import local FRED macro series from a regime_fred_series.yaml config. "
            "This command writes normalized local parquet files and a stable import "
            "artifact. It does not call brokers, route orders, submit orders, model fills, "
            "perform live execution, model slippage, or create automatic strategy/parameter actions."
        )
    )
    parser.add_argument("--config", default="config/regime_fred_series.yaml", help="YAML file listing FRED series ids.")
    parser.add_argument("--start-date", required=True, help="Backtest/reporting start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Backtest/reporting end date, YYYY-MM-DD.")
    parser.add_argument(
        "--warmup-start-date",
        help="Optional earlier fetch start date for lookback warmup, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for normalized macro parquet files. Defaults to data/raw/macro/<source-name>.",
    )
    parser.add_argument("--source-name", default="fred", help="Macro source folder name under data/raw/macro.")
    parser.add_argument("--artifact-dir", default="artifacts/fred_series_import", help="Stable artifact output directory.")
    parser.add_argument("--api-key", help="FRED API key. Prefer using --api-key-env instead.")
    parser.add_argument("--api-key-env", default="FRED_API_KEY", help="Environment variable containing the FRED API key.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP timeout per FRED request.")
    parser.add_argument("--max-retries", type=int, default=3, help="Retry attempts for transient FRED failures.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Optional pause between series requests.")
    parser.add_argument(
        "--replace-output",
        action="store_true",
        help="Delete existing parquet files under output-dir before writing this import.",
    )
    return parser


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Config file does not exist: {path}")

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as error:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml") from error

    with path.open(encoding="utf-8-sig") as file:
        value = yaml.safe_load(file)

    if value is None:
        raise SystemExit(f"Config file is empty: {path}")
    return value


def _extract_series_configs(config: Any) -> list[SeriesConfig]:
    output: list[SeriesConfig] = []

    def walk(value: Any, path: list[str]) -> None:
        if isinstance(value, Mapping):
            direct = _series_config_from_mapping(value, path)
            if direct is not None:
                output.append(direct)
                return

            for key, child in value.items():
                child_path = [*path, str(key)]
                if isinstance(child, str) and _looks_like_series_id(child):
                    output.append(
                        SeriesConfig(
                            series_id=child.strip().upper(),
                            config_key=str(key),
                            series_group=_path_group(path),
                            series_name=str(key),
                            series_role=str(key),
                            source_path=".".join(child_path),
                            raw_config={"key": str(key), "series_id": child},
                        )
                    )
                else:
                    walk(child, child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, [*path, str(index)])
        elif isinstance(value, str) and _looks_like_series_id(value):
            key = path[-1] if path else value
            output.append(
                SeriesConfig(
                    series_id=value.strip().upper(),
                    config_key=key,
                    series_group=_path_group(path[:-1]),
                    series_name=key,
                    series_role=key,
                    source_path=".".join(path),
                    raw_config={"series_id": value},
                )
            )

    walk(config, [])
    return output


def _series_config_from_mapping(value: Mapping[str, Any], path: list[str]) -> SeriesConfig | None:
    series_id = None
    for key in _ID_KEYS:
        maybe = value.get(key)
        if isinstance(maybe, str) and _looks_like_series_id(maybe):
            series_id = maybe.strip().upper()
            break

    if not series_id:
        return None

    config_key = _first_text(value, ("key", "config_key", "name", "label", "metric", "column"))
    if not config_key:
        config_key = path[-1] if path else series_id

    return SeriesConfig(
        series_id=series_id,
        config_key=config_key,
        series_group=_first_text(value, _GROUP_KEYS) or _path_group(path[:-1]),
        series_name=_first_text(value, _NAME_KEYS) or config_key,
        series_role=_first_text(value, _ROLE_KEYS) or config_key,
        source_path=".".join(path),
        raw_config={str(key): _json_safe(item) for key, item in value.items()},
    )


def _looks_like_series_id(value: str) -> bool:
    text = value.strip().upper()
    return bool(_SERIES_ID_PATTERN.fullmatch(text))


def _path_group(path: Sequence[str]) -> str | None:
    meaningful = [part for part in path if not part.isdigit() and part not in {"series", "fred_series", "regime_series"}]
    return meaningful[-1] if meaningful else None


def _first_text(value: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        item = value.get(key)
        if item is None:
            continue
        text = str(item).strip()
        if text:
            return text
    return None


def _dedupe_series(series_configs: Sequence[SeriesConfig]) -> list[SeriesConfig]:
    by_series: dict[str, SeriesConfig] = {}
    for item in series_configs:
        by_series.setdefault(item.series_id, item)
    return [by_series[key] for key in sorted(by_series)]


def _fetch_observations(
    *,
    api_key: str,
    series_id: str,
    observation_start: date,
    observation_end: date,
    timeout_seconds: float,
    max_retries: int,
) -> list[dict[str, Any]]:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start.isoformat(),
        "observation_end": observation_end.isoformat(),
        "sort_order": "asc",
    }
    url = f"{FRED_OBSERVATIONS_URL}?{urllib.parse.urlencode(params)}"

    last_error: Exception | None = None
    attempts = max(1, max_retries)
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "SignalForge/FREDSeriesImport"})
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))

            observations = payload.get("observations")
            if not isinstance(observations, list):
                error_message = payload.get("error_message") or payload.get("error_code") or payload
                raise RuntimeError(f"FRED observations response missing observations for {series_id}: {error_message}")
            return [item for item in observations if isinstance(item, dict)]
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == attempts:
                detail = error.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"FRED HTTP {error.code} for {series_id}: {detail}") from error
        except Exception as error:  # noqa: BLE001 - retry transient local/network failures
            last_error = error
            if attempt == attempts:
                raise RuntimeError(f"FRED request failed for {series_id}: {error}") from error

        time.sleep(min(2 ** (attempt - 1), 8))

    raise RuntimeError(f"FRED request failed for {series_id}: {last_error}")


def _normalize_observation(
    item: SeriesConfig,
    observation: Mapping[str, Any],
    start_date: date,
    end_date: date,
    fetch_start_date: date,
) -> dict[str, Any] | None:
    obs_date = _parse_optional_date(observation.get("date"), "observation.date")
    if obs_date is None:
        return None

    raw_value = observation.get("value")
    value = _parse_float(raw_value)

    return {
        "artifact_type": "signalforge_fred_macro_row",
        "source": "fred",
        "series_id": item.series_id,
        "fred_series_id": item.series_id,
        "series_key": item.config_key,
        "series_group": item.series_group,
        "series_name": item.series_name,
        "series_role": item.series_role,
        "date": obs_date.isoformat(),
        "value": value,
        "raw_value": None if raw_value is None else str(raw_value),
        "realtime_start": observation.get("realtime_start"),
        "realtime_end": observation.get("realtime_end"),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "fetch_start_date": fetch_start_date.isoformat(),
        "is_warmup_row": obs_date < start_date,
        "config_source_path": item.source_path,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }


def _parse_float(value: Any) -> float | None:
    if value in {None, "", ".", "NaN", "nan"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_series_parquet(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame([dict(row) for row in rows], infer_schema_length=None)
    df.write_parquet(path)


def _remove_existing_parquet_files(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for path in output_dir.rglob("*.parquet"):
        path.unlink()


def _series_result(
    item: SeriesConfig,
    *,
    status: str,
    row_count: int,
    path: Path | None,
    first_date: str | None,
    last_date: str | None,
    warning: str | None,
) -> dict[str, Any]:
    return {
        "series_id": item.series_id,
        "config_key": item.config_key,
        "series_group": item.series_group,
        "series_name": item.series_name,
        "series_role": item.series_role,
        "status": status,
        "row_count": row_count,
        "first_observation_date": first_date,
        "last_observation_date": last_date,
        "parquet_path": str(path) if path else None,
        "warning": warning,
    }


def _status(*, all_rows: Sequence[Mapping[str, Any]], blocker_items: Sequence[Mapping[str, Any]], warning_items: Sequence[Mapping[str, Any]]) -> str:
    if not all_rows:
        return "blocked"
    if blocker_items or warning_items:
        return "needs_review"
    return "ready"


def _summary(*, result: Mapping[str, Any], result_path: Path, summary_path: Path) -> dict[str, Any]:
    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_fred_series_import_cli",
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "config_path": result.get("config_path"),
        "source": result.get("source"),
        "source_name": result.get("source_name"),
        "start_date": result.get("start_date"),
        "end_date": result.get("end_date"),
        "warmup_start_date": result.get("warmup_start_date"),
        "fetch_start_date": result.get("fetch_start_date"),
        "output_dir": result.get("output_dir"),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "series_requested_count": result.get("series_requested_count", 0),
        "unique_series_count": result.get("unique_series_count", 0),
        "series_success_count": result.get("series_success_count", 0),
        "series_needs_review_count": result.get("series_needs_review_count", 0),
        "series_blocked_count": result.get("series_blocked_count", 0),
        "macro_row_count": result.get("macro_row_count", 0),
        "first_observation_date": result.get("first_observation_date"),
        "last_observation_date": result.get("last_observation_date"),
        "warning_count": len(result.get("warning_items", [])),
        "blocker_count": len(result.get("blocker_items", [])),
        "next_step": "fred_regime_pipeline_cli",
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _parse_required_date(value: Any, name: str) -> date:
    parsed = _parse_optional_date(value, name)
    if parsed is None:
        raise SystemExit(f"{name} must be a valid YYYY-MM-DD date")
    return parsed


def _parse_optional_date(value: Any, name: str) -> date | None:
    if value in {None, ""}:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as error:
        raise SystemExit(f"{name} must be a valid YYYY-MM-DD date: {value}") from error


def _safe_file_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
