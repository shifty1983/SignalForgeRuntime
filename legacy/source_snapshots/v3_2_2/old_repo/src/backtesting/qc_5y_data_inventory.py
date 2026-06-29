from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXPLICIT_EXCLUSIONS = [
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


SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".csv"}


DATE_KEY_PRIORITY = [
    "trade_date",
    "date",
    "time",
    "timestamp",
    "datetime",
    "end_time",
    "slice_time",
    "bar_time",
]


SYMBOL_KEY_HINTS = {
    "symbol",
    "ticker",
    "underlying",
    "underlying_symbol",
    "canonical_symbol",
    "contract_symbol",
    "asset",
}


DATE_RE = re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})")
COMPACT_DATE_RE = re.compile(r"^\d{8}$")


@dataclass
class FileInventory:
    path: str
    extension: str
    size_bytes: int
    modified_utc: str
    parse_status: str
    row_count: int = 0
    symbols: set[str] = field(default_factory=set)
    date_min: str | None = None
    date_max: str | None = None
    fields: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "modified_utc": self.modified_utc,
            "parse_status": self.parse_status,
            "row_count": self.row_count,
            "symbols": sorted(self.symbols),
            "symbol_count": len(self.symbols),
            "date_min": self.date_min,
            "date_max": self.date_max,
            "fields": sorted(self.fields),
            "warnings": self.warnings,
        }


def _iso_modified_utc(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()


def _flatten_dict(row: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    for key, value in row.items():
        new_key = f"{prefix}.{key}" if prefix else str(key)

        if isinstance(value, dict):
            flattened.update(_flatten_dict(value, new_key))
        else:
            flattened[new_key] = value

    return flattened


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        raw = str(int(value))

        if COMPACT_DATE_RE.match(raw):
            return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

        # epoch seconds or milliseconds
        try:
            if len(raw) >= 13:
                dt = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
                return dt.date().isoformat()
            if len(raw) == 10:
                dt = datetime.fromtimestamp(int(value), tz=timezone.utc)
                return dt.date().isoformat()
        except Exception:
            return None

    text = str(value).strip()

    match = DATE_RE.search(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    if COMPACT_DATE_RE.match(text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"

    return None


def _extract_row_date(row: dict[str, Any]) -> str | None:
    flat = _flatten_dict(row)

    lower_map = {key.lower(): key for key in flat.keys()}

    for priority_key in DATE_KEY_PRIORITY:
        if priority_key in lower_map:
            value = flat[lower_map[priority_key]]
            parsed = _parse_date(value)
            if parsed:
                return parsed

    for lower_key, original_key in lower_map.items():
        if "expiry" in lower_key or "expiration" in lower_key:
            continue

        if "date" in lower_key or "time" in lower_key or "timestamp" in lower_key:
            parsed = _parse_date(flat[original_key])
            if parsed:
                return parsed

    return None


def _normalize_symbol(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, (int, float, bool)):
        return None

    text = str(value).strip()

    if not text:
        return None

    if _parse_date(text):
        return None

    if len(text) > 80:
        return None

    return text.upper()


def _extract_symbols(row: dict[str, Any]) -> set[str]:
    flat = _flatten_dict(row)
    symbols: set[str] = set()

    for key, value in flat.items():
        lower_key = key.lower().split(".")[-1]

        if lower_key in SYMBOL_KEY_HINTS or lower_key.endswith("_symbol"):
            if isinstance(value, list):
                for item in value:
                    symbol = _normalize_symbol(item)
                    if symbol:
                        symbols.add(symbol)
            else:
                symbol = _normalize_symbol(value)
                if symbol:
                    symbols.add(symbol)

    return symbols


def _update_date_range(inventory: FileInventory, date_value: str | None) -> None:
    if not date_value:
        return

    if inventory.date_min is None or date_value < inventory.date_min:
        inventory.date_min = date_value

    if inventory.date_max is None or date_value > inventory.date_max:
        inventory.date_max = date_value


def _inspect_row(inventory: FileInventory, row: Any) -> None:
    if not isinstance(row, dict):
        return

    inventory.row_count += 1

    flat = _flatten_dict(row)
    inventory.fields.update(flat.keys())
    inventory.symbols.update(_extract_symbols(row))
    _update_date_range(inventory, _extract_row_date(row))


def _iter_json_rows(data: Any) -> Iterable[Any]:
    if isinstance(data, list):
        yield from data
        return

    if isinstance(data, dict):
        preferred_keys = [
            "rows",
            "records",
            "data",
            "history",
            "prices",
            "bars",
            "snapshots",
            "option_rows",
            "contract_outcome_snapshots",
            "candidate_rows",
        ]

        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, list):
                yield from value
                return

        list_values = [value for value in data.values() if isinstance(value, list)]
        dict_list_values = [
            value for value in list_values
            if value and all(isinstance(item, dict) for item in value[:10])
        ]

        if dict_list_values:
            largest = max(dict_list_values, key=len)
            yield from largest
            return

        yield data


def _scan_csv(path: Path, inventory: FileInventory) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            _inspect_row(inventory, row)


def _scan_jsonl(path: Path, inventory: FileInventory) -> None:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                inventory.warnings.append(f"invalid_jsonl_line:{line_number}")
                continue

            _inspect_row(inventory, row)


def _scan_json(path: Path, inventory: FileInventory) -> None:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)

    for row in _iter_json_rows(data):
        _inspect_row(inventory, row)


def scan_qc_data_file(path: Path, source_root: Path) -> FileInventory:
    relative_path = path.relative_to(source_root).as_posix()
    extension = path.suffix.lower()

    inventory = FileInventory(
        path=relative_path,
        extension=extension,
        size_bytes=path.stat().st_size,
        modified_utc=_iso_modified_utc(path),
        parse_status="skipped" if extension not in SUPPORTED_EXTENSIONS else "parsed",
    )

    if extension not in SUPPORTED_EXTENSIONS:
        inventory.warnings.append("unsupported_extension")
        return inventory

    try:
        if extension == ".csv":
            _scan_csv(path, inventory)
        elif extension == ".jsonl":
            _scan_jsonl(path, inventory)
        elif extension == ".json":
            _scan_json(path, inventory)
    except Exception as exc:
        inventory.parse_status = "error"
        inventory.warnings.append(f"parse_error:{type(exc).__name__}:{exc}")

    if inventory.parse_status == "parsed" and inventory.row_count == 0:
        inventory.warnings.append("no_rows_detected")

    return inventory


def _read_expected_symbols(expected_symbols: list[str] | None) -> set[str]:
    if not expected_symbols:
        return set()

    return {
        symbol.strip().upper()
        for symbol in expected_symbols
        if symbol and symbol.strip()
    }


def _derive_readiness(
    *,
    supported_file_count: int,
    parsed_file_count: int,
    error_file_count: int,
    total_rows: int,
    discovered_symbols: set[str],
    expected_symbols: set[str],
    date_min: str | None,
    date_max: str | None,
    replay_start: str | None,
    replay_end: str | None,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if supported_file_count == 0:
        blockers.append("no_supported_qc_data_files_found")

    if parsed_file_count == 0:
        blockers.append("no_parsed_qc_data_files_found")

    if total_rows == 0:
        blockers.append("no_rows_detected")

    if error_file_count > 0:
        warnings.append("one_or_more_files_failed_to_parse")

    if not discovered_symbols:
        warnings.append("no_symbols_detected")

    if not date_min or not date_max:
        warnings.append("no_trade_date_range_detected")

    if replay_start and date_min and date_min > replay_start:
        warnings.append("inventory_starts_after_requested_replay_start")

    if replay_end and date_max and date_max < replay_end:
        warnings.append("inventory_ends_before_requested_replay_end")

    missing_expected = sorted(expected_symbols - discovered_symbols)
    if missing_expected:
        warnings.append("missing_expected_symbols:" + ",".join(missing_expected))

    if blockers:
        return "blocked", blockers, warnings

    if warnings:
        return "needs_review", blockers, warnings

    return "ready", blockers, warnings


def build_qc_5y_data_inventory(
    *,
    source_root: str | Path,
    output_dir: str | Path,
    replay_start: str | None = None,
    replay_end: str | None = None,
    expected_symbols: list[str] | None = None,
) -> dict[str, Any]:
    source_root_path = Path(source_root)
    output_dir_path = Path(output_dir)

    if not source_root_path.exists():
        raise FileNotFoundError(f"source_root does not exist: {source_root_path}")

    output_dir_path.mkdir(parents=True, exist_ok=True)

    file_inventories: list[FileInventory] = []

    for path in sorted(source_root_path.rglob("*")):
        if path.is_file():
            file_inventories.append(scan_qc_data_file(path, source_root_path))

    supported_files = [
        item for item in file_inventories
        if item.extension in SUPPORTED_EXTENSIONS
    ]
    parsed_files = [
        item for item in supported_files
        if item.parse_status == "parsed"
    ]
    error_files = [
        item for item in supported_files
        if item.parse_status == "error"
    ]

    discovered_symbols: set[str] = set()
    date_min: str | None = None
    date_max: str | None = None
    total_rows = 0
    total_bytes = 0
    by_extension: dict[str, int] = {}

    for item in file_inventories:
        total_bytes += item.size_bytes
        by_extension[item.extension or "<none>"] = by_extension.get(item.extension or "<none>", 0) + 1
        total_rows += item.row_count
        discovered_symbols.update(item.symbols)

        if item.date_min and (date_min is None or item.date_min < date_min):
            date_min = item.date_min

        if item.date_max and (date_max is None or item.date_max > date_max):
            date_max = item.date_max

    expected_symbol_set = _read_expected_symbols(expected_symbols)

    readiness_state, blockers, warnings = _derive_readiness(
        supported_file_count=len(supported_files),
        parsed_file_count=len(parsed_files),
        error_file_count=len(error_files),
        total_rows=total_rows,
        discovered_symbols=discovered_symbols,
        expected_symbols=expected_symbol_set,
        date_min=date_min,
        date_max=date_max,
        replay_start=replay_start,
        replay_end=replay_end,
    )

    artifact = {
        "adapter_type": "qc_5y_data_inventory_builder",
        "artifact_type": "signalforge_qc_5y_data_inventory",
        "contract": "qc_5y_data_inventory",
        "is_ready": readiness_state == "ready",
        "readiness_state": readiness_state,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warnings": warnings,
        "replay_start": replay_start,
        "replay_end": replay_end,
        "source_root": str(source_root_path),
        "output_dir": str(output_dir_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "file_summary": {
            "file_count": len(file_inventories),
            "supported_file_count": len(supported_files),
            "parsed_file_count": len(parsed_files),
            "error_file_count": len(error_files),
            "skipped_file_count": len(file_inventories) - len(supported_files),
            "total_bytes": total_bytes,
            "by_extension": dict(sorted(by_extension.items())),
            "total_rows": total_rows,
        },
        "coverage_summary": {
            "date_min": date_min,
            "date_max": date_max,
            "discovered_symbol_count": len(discovered_symbols),
            "discovered_symbols": sorted(discovered_symbols),
            "expected_symbol_count": len(expected_symbol_set),
            "expected_symbols": sorted(expected_symbol_set),
            "missing_expected_symbols": sorted(expected_symbol_set - discovered_symbols),
        },
        "files": [item.to_dict() for item in file_inventories],
    }

    inventory_path = output_dir_path / "signalforge_qc_5y_data_inventory.json"
    summary_path = output_dir_path / "signalforge_qc_5y_data_inventory_summary.json"

    inventory_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = {
        key: artifact[key]
        for key in [
            "adapter_type",
            "artifact_type",
            "contract",
            "is_ready",
            "readiness_state",
            "blocker_count",
            "blockers",
            "warnings",
            "replay_start",
            "replay_end",
            "source_root",
            "file_summary",
            "coverage_summary",
            "explicit_exclusions",
        ]
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return artifact