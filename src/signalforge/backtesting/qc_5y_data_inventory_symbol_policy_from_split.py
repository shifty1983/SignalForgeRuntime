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
    if not isinstance(values, list):
        return set()

    return {
        _normalize_symbol(value)
        for value in values
        if _normalize_symbol(value)
    }


def _get_group(split_inventory: dict[str, Any], group_name: str) -> dict[str, Any]:
    groups = split_inventory.get("groups", {})

    if not isinstance(groups, dict):
        return {}

    group = groups.get(group_name, {})

    if not isinstance(group, dict):
        return {}

    return group


def _get_symbols(
    split_inventory: dict[str, Any],
    group_name: str,
    symbol_key: str,
) -> set[str]:
    group = _get_group(split_inventory, group_name)
    return _symbol_set(group.get(symbol_key, []))


def build_symbol_policy_from_split_inventory(
    *,
    split_inventory_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    split_inventory_path = Path(split_inventory_path)
    output_path = Path(output_path)

    split_inventory = _read_json(split_inventory_path)

    if split_inventory.get("artifact_type") != "signalforge_qc_5y_data_inventory_split":
        raise ValueError("invalid split inventory artifact_type")

    market_symbols = _get_symbols(
        split_inventory,
        "market_price",
        "market_price_symbols",
    )

    option_underlyings = _get_symbols(
        split_inventory,
        "option_behavior",
        "option_underlying_symbols",
    )

    contract_outcome_underlyings = _get_symbols(
        split_inventory,
        "contract_outcome",
        "contract_outcome_underlying_symbols",
    )

    context_only_symbols = market_symbols - option_underlyings

    option_underlyings_missing_contract_outcomes = (
        option_underlyings - contract_outcome_underlyings
    )

    outcome_backed_tradable_symbols = (
        option_underlyings & contract_outcome_underlyings
    )

    policy = {
        "artifact_type": "signalforge_qc_5y_data_inventory_symbol_policy",
        "schema_version": "signalforge_qc_5y_data_inventory_symbol_policy.v1",
        "source_split_inventory_path": str(split_inventory_path),
        "source_split_inventory_artifact_type": split_inventory.get("artifact_type"),
        "source_root": split_inventory.get("source_root"),
        "replay_start": split_inventory.get("replay_start"),
        "replay_end": split_inventory.get("replay_end"),

        # Tradable now means outcome-backed tradable.
        # A symbol must have both option behavior and contract outcome evidence.
        "tradable_option_symbols": sorted(outcome_backed_tradable_symbols),

        # Market symbols with no option behavior are context-only.
        "context_only_symbols": sorted(context_only_symbols),

        # Context-only symbols already cover missing option behavior.
        "accepted_missing_option_behavior_symbols": [],

        # Symbols that have option behavior but no contract outcomes are excluded
        # from tradable until outcomes are rebuilt or intentionally added later.
        "accepted_missing_contract_outcome_symbols": sorted(
            option_underlyings_missing_contract_outcomes
        ),

        "accepted_source_warnings": [
            "inventory_ends_before_requested_replay_end",
            "some_market_symbols_missing_option_behavior",
            "some_option_underlyings_missing_contract_outcomes",
        ],

        "diagnostics": {
            "market_price_symbol_count": len(market_symbols),
            "option_underlying_symbol_count": len(option_underlyings),
            "contract_outcome_underlying_symbol_count": len(
                contract_outcome_underlyings
            ),
            "outcome_backed_tradable_symbol_count": len(
                outcome_backed_tradable_symbols
            ),
            "context_only_symbol_count": len(context_only_symbols),
            "excluded_missing_contract_outcome_count": len(
                option_underlyings_missing_contract_outcomes
            ),
            "excluded_missing_contract_outcome_symbols": sorted(
                option_underlyings_missing_contract_outcomes
            ),
        },

        "notes": {
            "tradable_option_symbols": (
                "Generated from option_behavior.option_underlying_symbols intersected "
                "with contract_outcome.contract_outcome_underlying_symbols. These are "
                "outcome-backed tradable symbols."
            ),
            "context_only_symbols": (
                "Generated from market_price_symbols minus option_underlying_symbols. "
                "These symbols are not eligible for option strategy selection."
            ),
            "accepted_missing_contract_outcome_symbols": (
                "Generated from option_underlying_symbols minus "
                "contract_outcome_underlying_symbols. These symbols have option behavior "
                "but are excluded from tradable because they lack contract outcome evidence."
            ),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(policy, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return policy
