from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"path does not exist: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object at {path}")

    return data


def _normalize_symbol(raw: Any) -> str:
    return str(raw).strip().upper()


def _symbol_set(values: Any) -> set[str]:
    if not values:
        return set()

    if not isinstance(values, list):
        return set()

    return {
        _normalize_symbol(value)
        for value in values
        if _normalize_symbol(value)
    }


def _sorted(values: set[str]) -> list[str]:
    return sorted(values)


def _sample(values: set[str], limit: int = 50) -> list[str]:
    return sorted(values)[:limit]


def _policy_set(policy: dict[str, Any], key: str) -> set[str]:
    return _symbol_set(policy.get(key, []))


def _get_group(split_inventory: dict[str, Any], group_name: str) -> dict[str, Any]:
    groups = split_inventory.get("groups", {})

    if not isinstance(groups, dict):
        return {}

    group = groups.get(group_name, {})

    if not isinstance(group, dict):
        return {}

    return group


def _get_group_symbol_set(
    split_inventory: dict[str, Any],
    group_name: str,
    symbol_key: str,
) -> set[str]:
    group = _get_group(split_inventory, group_name)
    return _symbol_set(group.get(symbol_key, []))


def _get_group_count(
    split_inventory: dict[str, Any],
    group_name: str,
    count_key: str,
) -> int:
    group = _get_group(split_inventory, group_name)

    try:
        return int(group.get(count_key, 0) or 0)
    except Exception:
        return 0


def _has_full_symbol_lists(split_inventory: dict[str, Any]) -> bool:
    market = _get_group(split_inventory, "market_price")
    option = _get_group(split_inventory, "option_behavior")
    outcome = _get_group(split_inventory, "contract_outcome")

    required = [
        (market, "market_price_symbols"),
        (option, "option_underlying_symbols"),
        (outcome, "contract_outcome_underlying_symbols"),
    ]

    return all(key in group and isinstance(group.get(key), list) for group, key in required)


def _build_status(blockers: list[str]) -> tuple[str, bool]:
    if blockers:
        return "blocked", False

    return "ready", True


def build_qc_5y_data_inventory_gate(
    *,
    split_inventory_path: str | Path,
    policy_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    split_inventory_path = Path(split_inventory_path)
    policy_path = Path(policy_path)
    output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    split_inventory = _read_json(split_inventory_path)
    policy = _read_json(policy_path)

    blockers: list[str] = []
    warnings: list[str] = []

    if split_inventory.get("artifact_type") != "signalforge_qc_5y_data_inventory_split":
        blockers.append("invalid_split_inventory_artifact_type")

    if policy.get("artifact_type") != "signalforge_qc_5y_data_inventory_symbol_policy":
        blockers.append("invalid_symbol_policy_artifact_type")

    if not _has_full_symbol_lists(split_inventory):
        blockers.append("split_inventory_missing_full_symbol_lists")

    market_symbols = _get_group_symbol_set(
        split_inventory,
        "market_price",
        "market_price_symbols",
    )

    option_underlyings = _get_group_symbol_set(
        split_inventory,
        "option_behavior",
        "option_underlying_symbols",
    )

    contract_outcome_underlyings = _get_group_symbol_set(
        split_inventory,
        "contract_outcome",
        "contract_outcome_underlying_symbols",
    )

    tradable_option_symbols = _policy_set(policy, "tradable_option_symbols")
    context_only_symbols = _policy_set(policy, "context_only_symbols")
    accepted_missing_option_behavior_symbols = _policy_set(
        policy,
        "accepted_missing_option_behavior_symbols",
    )
    accepted_missing_contract_outcome_symbols = _policy_set(
        policy,
        "accepted_missing_contract_outcome_symbols",
    )
    accepted_source_warnings = set(policy.get("accepted_source_warnings", []) or [])

    source_warnings = set(split_inventory.get("warnings", []) or [])
    unaccepted_source_warnings = source_warnings - accepted_source_warnings

    policy_conflicts = {
        "tradable_and_context_only": tradable_option_symbols & context_only_symbols,
        "tradable_and_accepted_missing_option_behavior": (
            tradable_option_symbols & accepted_missing_option_behavior_symbols
        ),
        "tradable_and_accepted_missing_contract_outcome": (
            tradable_option_symbols & accepted_missing_contract_outcome_symbols
        ),
    }

    if policy_conflicts["tradable_and_context_only"]:
        blockers.append("symbols_cannot_be_both_tradable_and_context_only")

    if policy_conflicts["tradable_and_accepted_missing_option_behavior"]:
        blockers.append("tradable_symbols_cannot_accept_missing_option_behavior")

    if policy_conflicts["tradable_and_accepted_missing_contract_outcome"]:
        blockers.append("tradable_symbols_cannot_accept_missing_contract_outcomes")

    if unaccepted_source_warnings:
        blockers.append("unaccepted_source_inventory_warnings")

    market_symbols_missing_option_behavior = market_symbols - option_underlyings
    option_underlyings_missing_contract_outcomes = (
        option_underlyings - contract_outcome_underlyings
    )

    tradable_missing_market_price = tradable_option_symbols - market_symbols
    tradable_missing_option_behavior = tradable_option_symbols - option_underlyings
    tradable_missing_contract_outcomes = (
        tradable_option_symbols - contract_outcome_underlyings
    )

    if tradable_missing_market_price:
        blockers.append("tradable_symbols_missing_market_price")

    if tradable_missing_option_behavior:
        blockers.append("tradable_symbols_missing_option_behavior")

    if tradable_missing_contract_outcomes:
        blockers.append("tradable_symbols_missing_contract_outcomes")

    accepted_missing_option_behavior = (
        market_symbols_missing_option_behavior
        & (context_only_symbols | accepted_missing_option_behavior_symbols)
    )

    accepted_missing_contract_outcomes = (
        option_underlyings_missing_contract_outcomes
        & (context_only_symbols | accepted_missing_contract_outcome_symbols)
    )

    unclassified_market_symbols_missing_option_behavior = (
        market_symbols_missing_option_behavior
        - tradable_option_symbols
        - context_only_symbols
        - accepted_missing_option_behavior_symbols
    )

    unclassified_option_underlyings_missing_contract_outcomes = (
        option_underlyings_missing_contract_outcomes
        - tradable_option_symbols
        - context_only_symbols
        - accepted_missing_contract_outcome_symbols
    )

    if unclassified_market_symbols_missing_option_behavior:
        blockers.append("unclassified_market_symbols_missing_option_behavior")

    if unclassified_option_underlyings_missing_contract_outcomes:
        blockers.append("unclassified_option_underlyings_missing_contract_outcomes")

    unknown_file_count = _get_group_count(split_inventory, "unknown", "file_count")
    unknown_row_count = _get_group_count(split_inventory, "unknown", "row_count")

    if unknown_file_count > 0 or unknown_row_count > 0:
        blockers.append("unknown_inventory_group_contains_files_or_rows")

    status, is_ready = _build_status(blockers)

    gate_result = {
        "adapter_type": "qc_5y_data_inventory_gate_builder",
        "artifact_type": "signalforge_qc_5y_data_inventory_gate",
        "contract": "qc_5y_data_inventory_gate",
        "schema_version": "signalforge_qc_5y_data_inventory_gate.v1",
        "source_split_inventory_artifact_type": split_inventory.get("artifact_type"),
        "source_split_inventory_path": str(split_inventory_path),
        "source_symbol_policy_artifact_type": policy.get("artifact_type"),
        "source_symbol_policy_path": str(policy_path),
        "source_root": split_inventory.get("source_root"),
        "replay_start": split_inventory.get("replay_start"),
        "replay_end": split_inventory.get("replay_end"),
        "status": status,
        "is_ready": is_ready,
        "blocker_count": len(sorted(set(blockers))),
        "blockers": sorted(set(blockers)),
        "warnings": warnings,
        "explicit_exclusions": split_inventory.get("explicit_exclusions", []),
        "source_inventory_warnings": sorted(source_warnings),
        "accepted_source_warnings": sorted(source_warnings & accepted_source_warnings),
        "unaccepted_source_warnings": sorted(unaccepted_source_warnings),
        "policy_summary": {
            "tradable_option_symbol_count": len(tradable_option_symbols),
            "context_only_symbol_count": len(context_only_symbols),
            "accepted_missing_option_behavior_symbol_count": len(
                accepted_missing_option_behavior_symbols
            ),
            "accepted_missing_contract_outcome_symbol_count": len(
                accepted_missing_contract_outcome_symbols
            ),
            "accepted_source_warning_count": len(accepted_source_warnings),
            "tradable_option_symbols": _sorted(tradable_option_symbols),
            "context_only_symbols": _sorted(context_only_symbols),
            "accepted_missing_option_behavior_symbols": _sorted(
                accepted_missing_option_behavior_symbols
            ),
            "accepted_missing_contract_outcome_symbols": _sorted(
                accepted_missing_contract_outcome_symbols
            ),
        },
        "source_coverage": {
            "market_price_symbol_count": len(market_symbols),
            "option_underlying_symbol_count": len(option_underlyings),
            "contract_outcome_underlying_symbol_count": len(contract_outcome_underlyings),
            "market_price_symbols_sample": _sample(market_symbols),
            "option_underlying_symbols_sample": _sample(option_underlyings),
            "contract_outcome_underlying_symbols_sample": _sample(
                contract_outcome_underlyings
            ),
        },
        "required_coverage_failures": {
            "tradable_missing_market_price_count": len(tradable_missing_market_price),
            "tradable_missing_market_price_symbols": _sorted(
                tradable_missing_market_price
            ),
            "tradable_missing_option_behavior_count": len(
                tradable_missing_option_behavior
            ),
            "tradable_missing_option_behavior_symbols": _sorted(
                tradable_missing_option_behavior
            ),
            "tradable_missing_contract_outcomes_count": len(
                tradable_missing_contract_outcomes
            ),
            "tradable_missing_contract_outcomes_symbols": _sorted(
                tradable_missing_contract_outcomes
            ),
        },
        "gap_classification": {
            "market_symbols_missing_option_behavior_count": len(
                market_symbols_missing_option_behavior
            ),
            "market_symbols_missing_option_behavior_symbols": _sorted(
                market_symbols_missing_option_behavior
            ),
            "accepted_missing_option_behavior_count": len(
                accepted_missing_option_behavior
            ),
            "accepted_missing_option_behavior_symbols": _sorted(
                accepted_missing_option_behavior
            ),
            "unclassified_market_symbols_missing_option_behavior_count": len(
                unclassified_market_symbols_missing_option_behavior
            ),
            "unclassified_market_symbols_missing_option_behavior_symbols": _sorted(
                unclassified_market_symbols_missing_option_behavior
            ),
            "option_underlyings_missing_contract_outcomes_count": len(
                option_underlyings_missing_contract_outcomes
            ),
            "option_underlyings_missing_contract_outcomes_symbols": _sorted(
                option_underlyings_missing_contract_outcomes
            ),
            "accepted_missing_contract_outcomes_count": len(
                accepted_missing_contract_outcomes
            ),
            "accepted_missing_contract_outcomes_symbols": _sorted(
                accepted_missing_contract_outcomes
            ),
            "unclassified_option_underlyings_missing_contract_outcomes_count": len(
                unclassified_option_underlyings_missing_contract_outcomes
            ),
            "unclassified_option_underlyings_missing_contract_outcomes_symbols": _sorted(
                unclassified_option_underlyings_missing_contract_outcomes
            ),
        },
        "policy_conflicts": {
            "tradable_and_context_only_count": len(
                policy_conflicts["tradable_and_context_only"]
            ),
            "tradable_and_context_only_symbols": _sorted(
                policy_conflicts["tradable_and_context_only"]
            ),
            "tradable_and_accepted_missing_option_behavior_count": len(
                policy_conflicts["tradable_and_accepted_missing_option_behavior"]
            ),
            "tradable_and_accepted_missing_option_behavior_symbols": _sorted(
                policy_conflicts["tradable_and_accepted_missing_option_behavior"]
            ),
            "tradable_and_accepted_missing_contract_outcome_count": len(
                policy_conflicts["tradable_and_accepted_missing_contract_outcome"]
            ),
            "tradable_and_accepted_missing_contract_outcome_symbols": _sorted(
                policy_conflicts["tradable_and_accepted_missing_contract_outcome"]
            ),
        },
    }

    summary = {
        "adapter_type": gate_result["adapter_type"],
        "artifact_type": gate_result["artifact_type"],
        "contract": gate_result["contract"],
        "schema_version": gate_result["schema_version"],
        "source_split_inventory_path": gate_result["source_split_inventory_path"],
        "source_symbol_policy_path": gate_result["source_symbol_policy_path"],
        "source_root": gate_result["source_root"],
        "replay_start": gate_result["replay_start"],
        "replay_end": gate_result["replay_end"],
        "status": gate_result["status"],
        "is_ready": gate_result["is_ready"],
        "blocker_count": gate_result["blocker_count"],
        "blockers": gate_result["blockers"],
        "source_inventory_warnings": gate_result["source_inventory_warnings"],
        "accepted_source_warnings": gate_result["accepted_source_warnings"],
        "unaccepted_source_warnings": gate_result["unaccepted_source_warnings"],
        "policy_summary": {
            "tradable_option_symbol_count": gate_result["policy_summary"][
                "tradable_option_symbol_count"
            ],
            "context_only_symbol_count": gate_result["policy_summary"][
                "context_only_symbol_count"
            ],
            "accepted_missing_option_behavior_symbol_count": gate_result[
                "policy_summary"
            ]["accepted_missing_option_behavior_symbol_count"],
            "accepted_missing_contract_outcome_symbol_count": gate_result[
                "policy_summary"
            ]["accepted_missing_contract_outcome_symbol_count"],
        },
        "source_coverage": gate_result["source_coverage"],
        "required_coverage_failures": gate_result["required_coverage_failures"],
        "gap_classification": gate_result["gap_classification"],
        "policy_conflicts": gate_result["policy_conflicts"],
        "explicit_exclusions": gate_result["explicit_exclusions"],
    }

    gate_path = output_dir / "signalforge_qc_5y_data_inventory_gate.json"
    summary_path = output_dir / "signalforge_qc_5y_data_inventory_gate_summary.json"

    gate_path.write_text(
        json.dumps(gate_result, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return gate_result