"""Base strategy execution map validation for SignalForge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL_FIELDS = {
    "adapter_type",
    "artifact_type",
    "contract",
    "version",
    "strategies",
}

REQUIRED_STRATEGY_FIELDS = {
    "strategy",
    "enabled",
    "directional_bias",
    "position_type",
    "entry",
    "liquidity",
    "greeks",
    "risk",
    "entry_price",
    "exit",
    "defense",
    "skip_conditions",
}

REQUIRED_LIQUIDITY_FIELDS = {
    "require_bid_ask",
    "max_bid_ask_spread_pct",
    "min_open_interest",
    "min_volume",
}

REQUIRED_GREEK_FIELDS = {
    "required_for_entry",
    "missing_greeks_policy",
    "primary_greek",
}

REQUIRED_RISK_FIELDS = {
    "max_risk_per_trade_pct",
    "position_size_multiplier",
}

REQUIRED_ENTRY_PRICE_FIELDS = {
    "rule",
    "slippage_buffer_pct",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_numeric_range(
    errors: list[str],
    strategy: str,
    section_name: str,
    section: dict[str, Any],
    min_key: str,
    max_key: str,
) -> None:
    if min_key not in section or max_key not in section:
        return

    min_value = section[min_key]
    max_value = section[max_key]

    if not _is_number(min_value) or not _is_number(max_value):
        errors.append(f"{strategy}.{section_name}.{min_key}/{max_key}: values must be numeric")
        return

    if min_value > max_value:
        errors.append(
            f"{strategy}.{section_name}.{min_key}/{max_key}: min greater than max "
            f"({min_value} > {max_value})"
        )


def _check_pct(
    errors: list[str],
    strategy: str,
    section_name: str,
    section: dict[str, Any],
    key: str,
    *,
    allow_zero: bool = True,
) -> None:
    if key not in section:
        return

    value = section[key]
    if not _is_number(value):
        errors.append(f"{strategy}.{section_name}.{key}: must be numeric")
        return

    lower_bound = 0 if allow_zero else 0.0000001
    if value < lower_bound or value > 1:
        errors.append(f"{strategy}.{section_name}.{key}: expected percentage between 0 and 1")


def validate_base_strategy_execution_map(config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    missing_top = sorted(REQUIRED_TOP_LEVEL_FIELDS - set(config))
    for field in missing_top:
        errors.append(f"missing_top_level_field_{field}")

    strategies = config.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        errors.append("strategies_must_be_non_empty_list")
        strategies = []

    seen: set[str] = set()
    enabled_count = 0
    strategy_names: list[str] = []

    for index, row in enumerate(strategies):
        if not isinstance(row, dict):
            errors.append(f"strategies[{index}]: row must be object")
            continue

        strategy = str(row.get("strategy") or f"strategy_index_{index}")
        strategy_names.append(strategy)

        if strategy in seen:
            errors.append(f"duplicate_strategy_{strategy}")
        seen.add(strategy)

        if row.get("enabled") is True:
            enabled_count += 1

        missing = sorted(REQUIRED_STRATEGY_FIELDS - set(row))
        for field in missing:
            errors.append(f"{strategy}: missing_strategy_field_{field}")

        entry = row.get("entry") or {}
        liquidity = row.get("liquidity") or {}
        greeks = row.get("greeks") or {}
        risk = row.get("risk") or {}
        entry_price = row.get("entry_price") or {}
        exit_rules = row.get("exit") or {}
        defense = row.get("defense") or {}
        skip_conditions = row.get("skip_conditions") or []

        if not isinstance(entry, dict):
            errors.append(f"{strategy}.entry: must be object")
            entry = {}

        if not isinstance(liquidity, dict):
            errors.append(f"{strategy}.liquidity: must be object")
            liquidity = {}

        if not isinstance(greeks, dict):
            errors.append(f"{strategy}.greeks: must be object")
            greeks = {}

        if not isinstance(risk, dict):
            errors.append(f"{strategy}.risk: must be object")
            risk = {}

        if not isinstance(entry_price, dict):
            errors.append(f"{strategy}.entry_price: must be object")
            entry_price = {}

        if not isinstance(exit_rules, dict):
            errors.append(f"{strategy}.exit: must be object")
            exit_rules = {}

        if not isinstance(defense, dict):
            errors.append(f"{strategy}.defense: must be object")
            defense = {}

        if not isinstance(skip_conditions, list) or not skip_conditions:
            errors.append(f"{strategy}.skip_conditions: must be non-empty list")

        for field in sorted(REQUIRED_LIQUIDITY_FIELDS - set(liquidity)):
            errors.append(f"{strategy}.liquidity: missing_{field}")

        for field in sorted(REQUIRED_GREEK_FIELDS - set(greeks)):
            errors.append(f"{strategy}.greeks: missing_{field}")

        for field in sorted(REQUIRED_RISK_FIELDS - set(risk)):
            errors.append(f"{strategy}.risk: missing_{field}")

        for field in sorted(REQUIRED_ENTRY_PRICE_FIELDS - set(entry_price)):
            errors.append(f"{strategy}.entry_price: missing_{field}")

        _check_numeric_range(errors, strategy, "entry", entry, "dte_min", "dte_max")
        _check_numeric_range(errors, strategy, "entry", entry, "target_delta_min", "target_delta_max")
        _check_numeric_range(errors, strategy, "entry", entry, "long_leg_delta_min", "long_leg_delta_max")
        _check_numeric_range(errors, strategy, "entry", entry, "short_leg_delta_min", "short_leg_delta_max")
        _check_numeric_range(errors, strategy, "entry", entry, "short_put_delta_min", "short_put_delta_max")
        _check_numeric_range(errors, strategy, "entry", entry, "short_call_delta_min", "short_call_delta_max")
        _check_numeric_range(errors, strategy, "entry", entry, "spread_width_min", "spread_width_max")
        _check_numeric_range(errors, strategy, "entry", entry, "wing_width_min", "wing_width_max")

        _check_pct(errors, strategy, "liquidity", liquidity, "max_bid_ask_spread_pct", allow_zero=False)
        _check_pct(errors, strategy, "risk", risk, "max_risk_per_trade_pct", allow_zero=False)
        _check_pct(errors, strategy, "risk", risk, "position_size_multiplier", allow_zero=True)
        _check_pct(errors, strategy, "entry_price", entry_price, "slippage_buffer_pct", allow_zero=True)

        for pct_key in [
            "minimum_credit_pct_of_width",
            "max_debit_pct_of_width",
        ]:
            _check_pct(errors, strategy, "entry", entry, pct_key, allow_zero=False)

        for pct_key in [
            "profit_take_pct_of_credit",
            "profit_take_pct_of_debit",
            "profit_take_pct_of_max_profit",
            "loss_stop_pct_of_debit",
        ]:
            _check_pct(errors, strategy, "exit", exit_rules, pct_key, allow_zero=False)

        for greek_key in [
            "target_delta_min",
            "target_delta_max",
            "long_leg_delta_min",
            "long_leg_delta_max",
            "short_leg_delta_min",
            "short_leg_delta_max",
            "short_put_delta_min",
            "short_put_delta_max",
            "short_call_delta_min",
            "short_call_delta_max",
            "long_leg_delta_max",
        ]:
            if greek_key in entry:
                _check_pct(errors, strategy, "entry", entry, greek_key, allow_zero=True)

        if "dte_min" in entry and "dte_max" in entry:
            if entry["dte_min"] < 0:
                errors.append(f"{strategy}.entry.dte_min: cannot be negative")

        if liquidity.get("require_bid_ask") is not True:
            warnings.append(f"{strategy}.liquidity.require_bid_ask is not true")

        if greeks.get("missing_greeks_policy") not in {
            "reject_contract",
            "reject_contract_or_use_proxy_backtest_only",
            "allow_proxy",
        }:
            errors.append(f"{strategy}.greeks.missing_greeks_policy: invalid value")

    return {
        "adapter_type": "base_strategy_execution_map_validator",
        "artifact_type": "signalforge_base_strategy_execution_map_validation_summary",
        "contract": "base_strategy_execution_map_validation",
        "is_ready": len(errors) == 0,
        "blocker_count": len(errors),
        "blockers": errors,
        "warning_count": len(warnings),
        "warnings": warnings,
        "strategy_count": len(strategy_names),
        "enabled_strategy_count": enabled_count,
        "strategies": strategy_names,
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object")
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
