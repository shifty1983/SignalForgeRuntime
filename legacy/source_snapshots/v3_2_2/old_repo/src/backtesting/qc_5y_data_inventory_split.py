from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


OPTION_CONTRACT_RE = re.compile(
    r"^[A-Z0-9.\-]{1,12}\s+\d{6}[CP]\d{8}$"
)


CORE_GROUPS = [
    "market_price",
    "option_behavior",
    "contract_outcome",
    "metadata",
    "unknown",
]


def _empty_group() -> dict[str, Any]:
    return {
        "file_count": 0,
        "row_count": 0,
        "size_bytes": 0,
        "date_min": None,
        "date_max": None,
        "market_price_symbols": set(),
        "option_underlying_symbols": set(),
        "option_contract_symbols": set(),
        "contract_outcome_underlying_symbols": set(),
        "contract_outcome_option_contract_symbols": set(),
        "metadata_files": [],
        "files": [],
    }


def _classify_file(file_item: dict[str, Any]) -> str:
    path = str(file_item.get("path", "")).lower()
    fields = {str(field).lower() for field in file_item.get("fields", [])}

    if "market_price_behavior_input" in path:
        return "market_price"

    if "option_behavior_input" in path and "manifest" not in path:
        return "option_behavior"

    if "contract_outcome_evidence" in path:
        return "contract_outcome"

    if "manifest" in path or "summary" in path:
        return "metadata"

    if {"open", "high", "low", "close", "volume", "symbol"}.issubset(fields):
        return "market_price"

    if "underlying_symbol" in fields and "option_symbol" in fields:
        return "option_behavior"

    if "option_symbol" in fields and "underlying_forward_return" in fields:
        return "contract_outcome"

    return "unknown"


def _is_option_contract(symbol: str) -> bool:
    return bool(OPTION_CONTRACT_RE.match(symbol.strip().upper()))


def _split_symbols(symbols: list[str]) -> tuple[set[str], set[str]]:
    underlyings: set[str] = set()
    option_contracts: set[str] = set()

    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()

        if not symbol:
            continue

        if _is_option_contract(symbol):
            option_contracts.add(symbol)
        else:
            underlyings.add(symbol)

    return underlyings, option_contracts


def _update_date_range(group: dict[str, Any], date_min: str | None, date_max: str | None) -> None:
    if date_min and (group["date_min"] is None or date_min < group["date_min"]):
        group["date_min"] = date_min

    if date_max and (group["date_max"] is None or date_max > group["date_max"]):
        group["date_max"] = date_max


def _compact_group(group: dict[str, Any], *, include_symbols: bool) -> dict[str, Any]:
    compact = {
        "file_count": group["file_count"],
        "row_count": group["row_count"],
        "size_bytes": group["size_bytes"],
        "date_min": group["date_min"],
        "date_max": group["date_max"],
        "market_price_symbol_count": len(group["market_price_symbols"]),
        "option_underlying_symbol_count": len(group["option_underlying_symbols"]),
        "option_contract_symbol_count": len(group["option_contract_symbols"]),
        "contract_outcome_underlying_symbol_count": len(group["contract_outcome_underlying_symbols"]),
        "contract_outcome_option_contract_symbol_count": len(group["contract_outcome_option_contract_symbols"]),
        "metadata_files": sorted(group["metadata_files"]),
        "files": group["files"],
    }

    if include_symbols:
        compact.update({
            "market_price_symbols": sorted(group["market_price_symbols"]),
            "option_underlying_symbols": sorted(group["option_underlying_symbols"]),
            "option_contract_symbols": sorted(group["option_contract_symbols"]),
            "contract_outcome_underlying_symbols": sorted(group["contract_outcome_underlying_symbols"]),
            "contract_outcome_option_contract_symbols": sorted(group["contract_outcome_option_contract_symbols"]),
        })
    else:
        compact.update({
            "market_price_symbol_sample": sorted(group["market_price_symbols"])[:25],
            "option_underlying_symbol_sample": sorted(group["option_underlying_symbols"])[:25],
            "option_contract_symbol_sample": sorted(group["option_contract_symbols"])[:25],
            "contract_outcome_underlying_symbol_sample": sorted(group["contract_outcome_underlying_symbols"])[:25],
            "contract_outcome_option_contract_symbol_sample": sorted(group["contract_outcome_option_contract_symbols"])[:25],
        })

    return compact


def _build_cross_checks(groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    market_symbols = groups["market_price"]["market_price_symbols"]
    option_underlyings = groups["option_behavior"]["option_underlying_symbols"]
    outcome_underlyings = groups["contract_outcome"]["contract_outcome_underlying_symbols"]

    return {
        "market_symbols_without_option_behavior_count": len(market_symbols - option_underlyings),
        "market_symbols_without_option_behavior_sample": sorted(market_symbols - option_underlyings)[:25],
        "option_underlyings_without_market_price_count": len(option_underlyings - market_symbols),
        "option_underlyings_without_market_price_sample": sorted(option_underlyings - market_symbols)[:25],
        "option_underlyings_without_contract_outcomes_count": len(option_underlyings - outcome_underlyings),
        "option_underlyings_without_contract_outcomes_sample": sorted(option_underlyings - outcome_underlyings)[:25],
        "contract_outcome_underlyings_without_option_behavior_count": len(outcome_underlyings - option_underlyings),
        "contract_outcome_underlyings_without_option_behavior_sample": sorted(outcome_underlyings - option_underlyings)[:25],
    }


def _derive_status(groups: dict[str, dict[str, Any]], source_warnings: list[str]) -> tuple[str, bool, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = list(source_warnings)

    if groups["market_price"]["row_count"] == 0:
        blockers.append("missing_market_price_behavior_input")

    if groups["option_behavior"]["row_count"] == 0:
        blockers.append("missing_option_behavior_input")

    if groups["contract_outcome"]["row_count"] == 0:
        blockers.append("missing_contract_outcome_evidence")

    if groups["market_price"]["market_price_symbols"] and groups["option_behavior"]["option_underlying_symbols"]:
        missing_options = (
            groups["market_price"]["market_price_symbols"]
            - groups["option_behavior"]["option_underlying_symbols"]
        )

        if missing_options:
            warnings.append("some_market_symbols_missing_option_behavior")

    if groups["option_behavior"]["option_underlying_symbols"] and groups["contract_outcome"]["contract_outcome_underlying_symbols"]:
        missing_outcomes = (
            groups["option_behavior"]["option_underlying_symbols"]
            - groups["contract_outcome"]["contract_outcome_underlying_symbols"]
        )

        if missing_outcomes:
            warnings.append("some_option_underlyings_missing_contract_outcomes")

    if blockers:
        return "blocked", False, blockers, warnings

    if warnings:
        return "needs_review", False, blockers, sorted(set(warnings))

    return "ready", True, blockers, warnings


def build_qc_5y_data_inventory_split(
    *,
    inventory_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    inventory_path = Path(inventory_path)
    output_dir = Path(output_dir)

    if not inventory_path.exists():
        raise FileNotFoundError(f"inventory_path does not exist: {inventory_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    source_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    groups = {
        group_name: _empty_group()
        for group_name in CORE_GROUPS
    }

    for file_item in source_inventory.get("files", []):
        category = _classify_file(file_item)
        group = groups[category]

        path = str(file_item.get("path", ""))
        row_count = int(file_item.get("row_count", 0) or 0)
        size_bytes = int(file_item.get("size_bytes", 0) or 0)
        symbols = [str(symbol) for symbol in file_item.get("symbols", [])]

        underlyings, option_contracts = _split_symbols(symbols)

        group["file_count"] += 1
        group["row_count"] += row_count
        group["size_bytes"] += size_bytes
        _update_date_range(group, file_item.get("date_min"), file_item.get("date_max"))

        file_summary = {
            "path": path,
            "row_count": row_count,
            "size_bytes": size_bytes,
            "date_min": file_item.get("date_min"),
            "date_max": file_item.get("date_max"),
            "parse_status": file_item.get("parse_status"),
            "symbol_count": len(symbols),
            "underlying_like_symbol_count": len(underlyings),
            "option_contract_symbol_count": len(option_contracts),
        }

        group["files"].append(file_summary)

        if category == "market_price":
            group["market_price_symbols"].update(underlyings)

        elif category == "option_behavior":
            group["option_underlying_symbols"].update(underlyings)
            group["option_contract_symbols"].update(option_contracts)

        elif category == "contract_outcome":
            group["contract_outcome_underlying_symbols"].update(underlyings)
            group["contract_outcome_option_contract_symbols"].update(option_contracts)

        elif category == "metadata":
            group["metadata_files"].append(path)

    cross_checks = _build_cross_checks(groups)

    status, is_ready, blockers, warnings = _derive_status(
        groups,
        source_inventory.get("warnings", []),
    )

    artifact = {
        "adapter_type": "qc_5y_data_inventory_split_builder",
        "artifact_type": "signalforge_qc_5y_data_inventory_split",
        "contract": "qc_5y_data_inventory_split",
        "source_inventory_artifact_type": source_inventory.get("artifact_type"),
        "source_inventory_path": str(inventory_path),
        "source_root": source_inventory.get("source_root"),
        "replay_start": source_inventory.get("replay_start"),
        "replay_end": source_inventory.get("replay_end"),
        "status": status,
        "is_ready": is_ready,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warnings": warnings,
        "explicit_exclusions": source_inventory.get("explicit_exclusions", []),
        "groups": {
            group_name: _compact_group(group, include_symbols=True)
            for group_name, group in groups.items()
        },
        "cross_checks": cross_checks,
    }

    summary = {
        "adapter_type": artifact["adapter_type"],
        "artifact_type": artifact["artifact_type"],
        "contract": artifact["contract"],
        "source_inventory_artifact_type": artifact["source_inventory_artifact_type"],
        "source_inventory_path": artifact["source_inventory_path"],
        "source_root": artifact["source_root"],
        "replay_start": artifact["replay_start"],
        "replay_end": artifact["replay_end"],
        "status": artifact["status"],
        "is_ready": artifact["is_ready"],
        "blocker_count": artifact["blocker_count"],
        "blockers": artifact["blockers"],
        "warnings": artifact["warnings"],
        "explicit_exclusions": artifact["explicit_exclusions"],
        "groups": {
            group_name: _compact_group(group, include_symbols=False)
            for group_name, group in groups.items()
        },
        "cross_checks": cross_checks,
    }

    split_path = output_dir / "signalforge_qc_5y_data_inventory_split.json"
    summary_path = output_dir / "signalforge_qc_5y_data_inventory_split_summary.json"

    split_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return artifact