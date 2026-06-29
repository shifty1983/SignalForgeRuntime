from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any


DATE_FIELDS = [
    # Prefer the same P/L recognition date used by Phase 6 equity reconstruction.
    "portfolio_realization_date",
    "realization_date",
    "outcome_availability_date",
    "selected_outcome_availability_date",
    "portfolio_realization_dt",
    # Fallbacks below are retained only for older ledgers.
    "decision_date",
    "trade_date",
    "date",
    "asof_date",
    "entry_date",
    "exit_date",
]

SYMBOL_FIELDS = [
    "symbol",
    "underlying",
    "ticker",
    "asset",
]

STRATEGY_FIELDS = [
    "selected_strategy",
    "strategy",
    "strategy_name",
    "strategy_id",
]

PNL_FIELDS = [
    "realized_pnl_dollars",
    "trade_pnl_dollars",
    "pnl_dollars",
    "trade_pnl",
    "pnl",
    "realized_pnl",
    "profit_loss",
    "portfolio_pnl",
    "net_pnl",
]

RETURN_FIELDS = [
    "realized_return",
    "trade_return",
    "selected_return",
    "strategy_return",
    "strategy_adjusted_return",
    "selected_strategy_adjusted_return",
    "return",
]

RISK_AMOUNT_FIELDS = [
    "position_risk_dollars",
    "max_trade_risk_dollars",
    "risk_budget_dollars",
    "risk_amount",
    "trade_risk_amount",
    "max_trade_risk",
    "position_risk",
    "capital_at_risk",
]

EQUITY_BEFORE_FIELDS = [
    "equity_before_trade",
    "equity_before",
    "portfolio_equity_before",
    "starting_equity",
    "capital_before",
]

EQUITY_AFTER_FIELDS = [
    "equity_after_trade",
    "equity_after",
    "portfolio_equity_after",
    "ending_equity",
    "capital_after",
]

SPREAD_PCT_FIELDS = [
    "spread_pct",
    "bid_ask_spread_pct",
    "option_spread_pct",
    "entry_spread_pct",
    "quote_spread_pct",
    "spread_width_pct",
    "entry_bid_ask_spread_pct",
    "exit_bid_ask_spread_pct",
    "strategy_spread_pct",
    "round_trip_spread_pct",
]

SPREAD_DOLLAR_FIELDS = [
    "round_trip_spread_cost_dollars",
    "bid_ask_spread_dollars",
    "spread_width_dollars",
    "entry_spread_dollars",
    "exit_spread_dollars",
    "option_spread_dollars",
    "quote_spread_dollars",
    "strategy_spread_dollars",
]

# Fields in RAW_TOTAL_SPREAD_COST_FIELDS are interpreted as already-realized
# trade-level dollar costs. Other spread-dollar fields are interpreted as
# option premium/quote widths and are scaled by contracts * option multiplier.
RAW_TOTAL_SPREAD_COST_FIELDS = {
    "round_trip_spread_cost_dollars",
}

PREMIUM_SPREAD_DOLLAR_FIELDS = {
    "bid_ask_spread_dollars",
    "spread_width_dollars",
    "entry_spread_dollars",
    "exit_spread_dollars",
    "option_spread_dollars",
    "quote_spread_dollars",
    "strategy_spread_dollars",
}

BID_FIELDS = [
    "bid",
    "bid_price",
    "entry_bid",
    "exit_bid",
    "leg_bid",
    "quote_bid",
]

ASK_FIELDS = [
    "ask",
    "ask_price",
    "entry_ask",
    "exit_ask",
    "leg_ask",
    "quote_ask",
]

CONTRACT_COUNT_FIELDS = [
    "contract_count",
    "contracts",
    "quantity",
    "option_contract_count",
    "contract_quantity",
    "fallback_contract_count",
]

LEG_COUNT_BY_STRATEGY = {
    "long_call": 1,
    "long_put": 1,
    "bull_call_debit_spread": 2,
    "bear_put_debit_spread": 2,
    "call_credit_spread": 2,
    "put_credit_spread": 2,
    "calendar_spread": 2,
    "diagonal_spread": 2,
    "iron_condor": 4,
    "iron_butterfly": 4,
}


def read_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")

    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig") as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue

                try:
                    value = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

                if not isinstance(value, dict):
                    raise ValueError(f"JSONL line {line_number} is not an object.")

                rows.append(value)

        return rows

    with path.open("r", encoding="utf-8-sig") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object or list of objects.")

    candidate_keys = [
        "rows",
        "trades",
        "trade_rows",
        "selected_trades",
        "equity_rows",
        "equity_curve",
        "position_sizing_rows",
        "portfolio_rows",
    ]

    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]

    raise ValueError(
        "Could not find trade rows in JSON file. Expected JSONL, a list, "
        "or one of these keys: "
        + ", ".join(candidate_keys)
    )


def first_present(row: dict[str, Any], fields: list[str]) -> tuple[str | None, Any]:
    for field in fields:
        if field in row and row[field] is not None:
            return field, row[field]
    return None, None


def iter_nested_key_values(value: Any, fields: set[str], path: str = "row") -> list[tuple[str, Any]]:
    """Return every nested value whose key matches one of fields.

    Phase 6 now carries execution realism data through nested payloads such as
    execution_realism_payload, selected_legs, entry_legs, and exit_legs. The
    original Phase 7 implementation only inspected top-level normalized fields,
    which made quote-aware scenarios silently fall back to proxy costs.
    """

    matches: list[tuple[str, Any]] = []

    if isinstance(value, dict):
        for key, nested_value in value.items():
            child_path = f"{path}.{key}"
            if key in fields and nested_value is not None:
                matches.append((child_path, nested_value))
            matches.extend(iter_nested_key_values(nested_value, fields, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(iter_nested_key_values(item, fields, f"{path}[{index}]"))

    return matches


def nested_numeric_values(row: dict[str, Any], fields: list[str]) -> list[tuple[str, float]]:
    output: list[tuple[str, float]] = []
    for path, value in iter_nested_key_values(row, set(fields)):
        parsed = to_float(value)
        if parsed is not None and math.isfinite(parsed):
            output.append((path, parsed))
    return output


def iter_nested_dicts(value: Any, path: str = "row") -> list[tuple[str, dict[str, Any]]]:
    output: list[tuple[str, dict[str, Any]]] = []

    if isinstance(value, dict):
        output.append((path, value))
        for key, nested_value in value.items():
            output.extend(iter_nested_dicts(nested_value, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            output.extend(iter_nested_dicts(item, f"{path}[{index}]"))

    return output


def derive_bid_ask_spread_pct(row: dict[str, Any]) -> tuple[float | None, str | None]:
    """Derive a conservative spread percent from nested bid/ask pairs.

    If several leg-level bid/ask pairs are present, use the max leg spread
    percentage. That makes execution_skip_wide_spreads conservative without
    inventing a portfolio-level quote from leg quotes.
    """

    derived: list[tuple[str, float]] = []

    for path, payload in iter_nested_dicts(row):
        bid_values = [to_float(payload.get(field)) for field in BID_FIELDS if field in payload]
        ask_values = [to_float(payload.get(field)) for field in ASK_FIELDS if field in payload]
        bid_values = [value for value in bid_values if value is not None]
        ask_values = [value for value in ask_values if value is not None]

        if not bid_values or not ask_values:
            continue

        bid = max(bid_values)
        ask = min(ask_values)

        if bid < 0 or ask < 0 or ask < bid:
            continue

        mid = (bid + ask) / 2.0
        if mid <= 0:
            continue

        derived.append((f"{path}.derived_bid_ask_spread_pct", (ask - bid) / mid))

    if not derived:
        return None, None

    source, value = max(derived, key=lambda item: item[1])
    return value, source


def to_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        parsed = float(value)
        if math.isnan(parsed) or math.isinf(parsed):
            return None
        return parsed

    if isinstance(value, str):
        cleaned = (
            value.strip()
            .replace("$", "")
            .replace(",", "")
            .replace("%", "")
        )

        if cleaned == "":
            return None

        try:
            parsed = float(cleaned)
        except ValueError:
            return None

        if "%" in value:
            return parsed / 100.0

        return parsed

    return None


def parse_year(value: Any) -> str:
    if value is None:
        return "unknown"

    text = str(value)

    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return str(datetime.strptime(text[:10], fmt).year)
        except ValueError:
            pass

    return "unknown"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[int(position)]

    lower_value = ordered[lower]
    upper_value = ordered[upper]
    weight = position - lower

    return lower_value + ((upper_value - lower_value) * weight)


def normalize_trade_rows(
    raw_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    field_usage: dict[str, int] = defaultdict(int)

    skipped_non_sized_count = 0
    skipped_missing_pnl_count = 0
    observed_spread_count = 0
    observed_spread_dollars_count = 0
    observed_contract_count_count = 0

    for sequence_index, row in enumerate(raw_rows):
        sizing_state = row.get("sizing_state")

        # Phase 7 should stress only actual portfolio-sized trades.
        # This prevents skipped rows with realized_return from being converted
        # into synthetic P/L.
        if sizing_state is not None and sizing_state != "sized":
            skipped_non_sized_count += 1
            continue

        date_field, date_value = first_present(row, DATE_FIELDS)
        symbol_field, symbol_value = first_present(row, SYMBOL_FIELDS)
        strategy_field, strategy_value = first_present(row, STRATEGY_FIELDS)

        pnl_field, pnl_value = first_present(row, PNL_FIELDS)
        return_field, return_value = first_present(row, RETURN_FIELDS)
        risk_field, risk_value = first_present(row, RISK_AMOUNT_FIELDS)
        equity_before_field, equity_before_value = first_present(row, EQUITY_BEFORE_FIELDS)
        equity_after_field, equity_after_value = first_present(row, EQUITY_AFTER_FIELDS)

        pnl = to_float(pnl_value)
        trade_return = to_float(return_value)
        risk_amount = to_float(risk_value)
        equity_before = to_float(equity_before_value)
        equity_after = to_float(equity_after_value)

        pnl_source = pnl_field

        if pnl is None and equity_before is not None and equity_after is not None:
            pnl = equity_after - equity_before
            pnl_source = "derived_from_equity_before_after"

        if pnl is None and trade_return is not None and risk_amount is not None:
            pnl = trade_return * risk_amount
            pnl_source = "derived_from_return_times_risk_amount"

        if pnl is None:
            skipped_missing_pnl_count += 1
            continue

        spread_pct, spread_pct_source = extract_spread_pct(row)
        spread_dollars, spread_dollars_source = extract_spread_dollars(row)
        contract_count, contract_count_source = extract_observed_contract_count(row)

        if date_field:
            field_usage[f"date:{date_field}"] += 1
        if symbol_field:
            field_usage[f"symbol:{symbol_field}"] += 1
        if strategy_field:
            field_usage[f"strategy:{strategy_field}"] += 1
        if pnl_source:
            field_usage[f"pnl:{pnl_source}"] += 1
        if return_field:
            field_usage[f"return:{return_field}"] += 1
        if risk_field:
            field_usage[f"risk_amount:{risk_field}"] += 1
        if equity_before_field:
            field_usage[f"equity_before:{equity_before_field}"] += 1
        if equity_after_field:
            field_usage[f"equity_after:{equity_after_field}"] += 1
        if spread_pct_source:
            observed_spread_count += 1
            field_usage[f"spread_pct:{spread_pct_source}"] += 1
        if spread_dollars_source:
            observed_spread_dollars_count += 1
            field_usage[f"spread_dollars:{spread_dollars_source}"] += 1
        if contract_count_source:
            observed_contract_count_count += 1
            field_usage[f"contract_count:{contract_count_source}"] += 1

        normalized.append(
            {
                "sequence_index": sequence_index,
                "date": str(date_value) if date_value is not None else None,
                "year": parse_year(date_value),
                "symbol": str(symbol_value) if symbol_value is not None else "unknown",
                "strategy": str(strategy_value) if strategy_value is not None else "unknown",
                "base_pnl": pnl,
                "base_return": trade_return,
                "risk_amount": risk_amount,
                "equity_before": equity_before,
                "equity_after": equity_after,
                "spread_pct": spread_pct,
                "spread_pct_source": spread_pct_source,
                "spread_dollars": spread_dollars,
                "spread_dollars_source": spread_dollars_source,
                "contract_count": contract_count,
                "contract_count_source": contract_count_source,
                "has_quote_native_execution_fields": bool(
                    spread_pct_source or spread_dollars_source
                ),
            }
        )

    diagnostics = {
        "raw_row_count": len(raw_rows),
        "normalized_trade_count": len(normalized),
        "skipped_non_sized_count": skipped_non_sized_count,
        "skipped_missing_pnl_count": skipped_missing_pnl_count,
        "observed_spread_count": observed_spread_count,
        "observed_spread_dollars_count": observed_spread_dollars_count,
        "observed_contract_count_count": observed_contract_count_count,
        "field_usage": dict(sorted(field_usage.items())),
    }

    return normalized, diagnostics


def sum_by(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)

    for row in rows:
        totals[str(row.get(key, "unknown"))] += float(row["base_pnl"])

    return dict(totals)


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)

    for row in rows:
        totals[str(row.get(key, "unknown"))] += 1

    return dict(totals)

def get_strategy_leg_count(strategy: str | None) -> int:
    if not strategy:
        return 1

    return LEG_COUNT_BY_STRATEGY.get(str(strategy), 1)


def extract_spread_pct(row: dict[str, Any]) -> tuple[float | None, str | None]:
    field, value = first_present(row, SPREAD_PCT_FIELDS)
    parsed = to_float(value)

    if parsed is not None:
        return parsed, field

    nested_values = [
        (path, value)
        for path, value in nested_numeric_values(row, SPREAD_PCT_FIELDS)
        if value >= 0
    ]
    if nested_values:
        # Use the max nested spread pct as a conservative per-trade stress input.
        source, spread_pct = max(nested_values, key=lambda item: item[1])
        return spread_pct, source

    derived_pct, derived_source = derive_bid_ask_spread_pct(row)
    if derived_pct is not None:
        return derived_pct, derived_source

    return None, None


def extract_spread_dollars(row: dict[str, Any]) -> tuple[float | None, str | None]:
    field, value = first_present(row, SPREAD_DOLLAR_FIELDS)
    parsed = to_float(value)

    if parsed is not None:
        return parsed, field

    nested_values = [
        (path, value)
        for path, value in nested_numeric_values(row, SPREAD_DOLLAR_FIELDS)
        if value >= 0
    ]
    if nested_values:
        # Dollar costs are additive across legs if multiple leg-level values exist.
        return sum(value for _, value in nested_values), "nested_sum:" + ",".join(
            sorted({path for path, _ in nested_values})[:8]
        )

    return None, None


def extract_observed_contract_count(row: dict[str, Any]) -> tuple[float | None, str | None]:
    field, value = first_present(row, CONTRACT_COUNT_FIELDS)
    parsed = to_float(value)

    if parsed is not None and parsed > 0:
        return parsed, field or "contract_count_field"

    nested_values = [
        (path, value)
        for path, value in nested_numeric_values(row, CONTRACT_COUNT_FIELDS)
        if value > 0
    ]
    if nested_values:
        # Use the max to avoid summing the same quantity repeated across legs/payload copies.
        source, contract_count = max(nested_values, key=lambda item: item[1])
        return contract_count, source

    return None, None


def get_spread_pct(row: dict[str, Any]) -> tuple[float | None, str | None]:
    parsed = to_float(row.get("spread_pct"))
    if parsed is not None:
        return parsed, str(row.get("spread_pct_source") or "spread_pct")

    return extract_spread_pct(row)


def get_spread_dollars(row: dict[str, Any]) -> tuple[float | None, str | None]:
    parsed = to_float(row.get("spread_dollars"))
    if parsed is not None:
        return parsed, str(row.get("spread_dollars_source") or "spread_dollars")

    return extract_spread_dollars(row)


def get_contract_count(row: dict[str, Any], fallback_contracts_per_trade: float) -> tuple[float, str]:
    parsed = to_float(row.get("contract_count"))
    if parsed is not None and parsed > 0:
        return parsed, str(row.get("contract_count_source") or "contract_count")

    observed, source = extract_observed_contract_count(row)
    if observed is not None and observed > 0:
        return observed, source or "contract_count_field"

    return fallback_contracts_per_trade, "fallback_contracts_per_trade"


def spread_dollar_source_cost_mode(source: str | None) -> str:
    source_text = str(source or "")

    for field in RAW_TOTAL_SPREAD_COST_FIELDS:
        if field in source_text:
            return "raw_trade_level_dollars"

    for field in PREMIUM_SPREAD_DOLLAR_FIELDS:
        if field in source_text:
            return "premium_quote_width_times_contract_multiplier"

    # Conservative default for ambiguous carried-forward spread-dollar fields.
    # Option quote spreads are usually premium-width values, not full trade P/L dollars.
    return "premium_quote_width_times_contract_multiplier"


def spread_dollar_cost_to_trade_dollars(
    *,
    spread_dollars: float,
    spread_dollars_source: str | None,
    contracts: float,
    option_contract_multiplier: float,
) -> tuple[float, str]:
    mode = spread_dollar_source_cost_mode(spread_dollars_source)

    if mode == "raw_trade_level_dollars":
        return spread_dollars, mode

    return spread_dollars * contracts * option_contract_multiplier, mode


def get_execution_cost_dollars(
    row: dict[str, Any],
    fill_stress_multiplier: float,
    default_round_trip_spread_cost_pct_of_risk: float,
    contracts_per_trade_fallback: float,
    option_contract_multiplier: float,
) -> tuple[float, str, dict[str, Any]]:
    risk_amount = to_float(row.get("risk_amount")) or 0.0
    contracts, contract_count_source = get_contract_count(
        row=row,
        fallback_contracts_per_trade=contracts_per_trade_fallback,
    )

    spread_dollars, spread_dollars_source = get_spread_dollars(row)
    spread_pct, spread_pct_source = get_spread_pct(row)

    if spread_dollars is not None:
        trade_level_spread_cost, spread_dollar_mode = spread_dollar_cost_to_trade_dollars(
            spread_dollars=spread_dollars,
            spread_dollars_source=spread_dollars_source,
            contracts=contracts,
            option_contract_multiplier=option_contract_multiplier,
        )
        cost = trade_level_spread_cost * fill_stress_multiplier
        source = f"{spread_dollars_source}:{spread_dollar_mode}_x_{fill_stress_multiplier}"
        return cost, source, {
            "cost_source_type": "quote_native_spread_dollars",
            "spread_dollars": spread_dollars,
            "spread_dollars_source": spread_dollars_source,
            "spread_dollar_cost_mode": spread_dollar_mode,
            "contract_count": contracts,
            "contract_count_source": contract_count_source,
            "option_contract_multiplier": option_contract_multiplier,
            "trade_level_spread_cost_before_multiplier": trade_level_spread_cost,
            "fill_stress_multiplier": fill_stress_multiplier,
            "cost_dollars": cost,
        }

    if spread_pct is not None:
        trade_level_spread_cost = risk_amount * spread_pct
        cost = trade_level_spread_cost * fill_stress_multiplier
        source = f"{spread_pct_source}_x_risk_x_{fill_stress_multiplier}"
        return cost, source, {
            "cost_source_type": "quote_native_spread_pct",
            "spread_pct": spread_pct,
            "spread_pct_source": spread_pct_source,
            "risk_amount": risk_amount,
            "trade_level_spread_cost_before_multiplier": trade_level_spread_cost,
            "fill_stress_multiplier": fill_stress_multiplier,
            "cost_dollars": cost,
        }

    cost = risk_amount * default_round_trip_spread_cost_pct_of_risk * fill_stress_multiplier
    source = f"default_round_trip_spread_cost_pct_of_risk_x_{fill_stress_multiplier}"
    return cost, source, {
        "cost_source_type": "fallback_pct_of_risk",
        "risk_amount": risk_amount,
        "default_round_trip_spread_cost_pct_of_risk": default_round_trip_spread_cost_pct_of_risk,
        "fill_stress_multiplier": fill_stress_multiplier,
        "cost_dollars": cost,
    }


def get_commission_and_fee_dollars(
    row: dict[str, Any],
    commission_per_contract: float,
    regulatory_fee_per_contract: float,
    clearing_fee_per_contract: float,
    activity_fee_per_contract: float,
    contracts_per_trade_fallback: float,
    round_trip_sides: float,
) -> tuple[float, dict[str, Any]]:
    strategy = row.get("strategy")
    leg_count = get_strategy_leg_count(strategy)

    contracts, contract_count_source = get_contract_count(
        row=row,
        fallback_contracts_per_trade=contracts_per_trade_fallback,
    )

    total_contract_units = contracts * leg_count * round_trip_sides

    per_contract_cost = (
        commission_per_contract
        + regulatory_fee_per_contract
        + clearing_fee_per_contract
        + activity_fee_per_contract
    )

    total_cost = total_contract_units * per_contract_cost

    return total_cost, {
        "strategy": strategy,
        "leg_count": leg_count,
        "contracts": contracts,
        "contract_count_source": contract_count_source,
        "round_trip_sides": round_trip_sides,
        "per_contract_cost": per_contract_cost,
        "commission_per_contract": commission_per_contract,
        "regulatory_fee_per_contract": regulatory_fee_per_contract,
        "clearing_fee_per_contract": clearing_fee_per_contract,
        "activity_fee_per_contract": activity_fee_per_contract,
        "total_contract_units": total_contract_units,
    }

def top_keys_by_positive_contribution(
    rows: list[dict[str, Any]],
    key: str,
    limit: int,
) -> list[str]:
    totals: dict[str, float] = defaultdict(float)

    for row in rows:
        pnl = float(row["base_pnl"])
        if pnl > 0:
            totals[str(row.get(key, "unknown"))] += pnl

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [name for name, _ in ranked[:limit]]


def build_scenario_rows(
    trades: list[dict[str, Any]],
    scenario_name: str,
    default_round_trip_spread_cost_pct_of_risk: float,
    allowed_spread_pct: float,
    commission_per_contract: float,
    regulatory_fee_per_contract: float,
    clearing_fee_per_contract: float,
    activity_fee_per_contract: float,
    contracts_per_trade_fallback: float,
    round_trip_sides: float,
    option_contract_multiplier: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [dict(trade) for trade in trades]
    details: dict[str, Any] = {}

    if scenario_name == "baseline":
        return rows, details

    if scenario_name.startswith("risk_scale_"):
        scale = float(scenario_name.replace("risk_scale_", ""))

        for row in rows:
            row["base_pnl"] = float(row["base_pnl"]) * scale

        details["risk_scale"] = scale
        return rows, details

    if scenario_name.startswith("win_haircut_"):
        haircut = float(scenario_name.replace("win_haircut_", ""))

        for row in rows:
            pnl = float(row["base_pnl"])
            if pnl > 0:
                row["base_pnl"] = pnl * (1.0 - haircut)

        details["win_haircut"] = haircut
        return rows, details

    if scenario_name.startswith("loss_inflation_"):
        inflation = float(scenario_name.replace("loss_inflation_", ""))

        for row in rows:
            pnl = float(row["base_pnl"])
            if pnl < 0:
                row["base_pnl"] = pnl * (1.0 + inflation)

        details["loss_inflation"] = inflation
        return rows, details

    if scenario_name.startswith("combined_adverse_"):
        stress = float(scenario_name.replace("combined_adverse_", ""))

        for row in rows:
            pnl = float(row["base_pnl"])
            if pnl > 0:
                row["base_pnl"] = pnl * (1.0 - stress)
            elif pnl < 0:
                row["base_pnl"] = pnl * (1.0 + stress)

        details["win_haircut"] = stress
        details["loss_inflation"] = stress
        return rows, details

    if scenario_name.startswith("cap_winners_p"):
        p = float(scenario_name.replace("cap_winners_p", "")) / 100.0
        positive_pnls = [
            float(row["base_pnl"])
            for row in rows
            if float(row["base_pnl"]) > 0
        ]

        cap = percentile(positive_pnls, p)

        for row in rows:
            pnl = float(row["base_pnl"])
            if pnl > cap:
                row["base_pnl"] = cap

        details["winner_cap_percentile"] = p
        details["winner_cap_pnl"] = cap
        return rows, details

    if scenario_name.startswith("remove_top_winners_"):
        suffix = scenario_name.replace("remove_top_winners_", "")

        winners = [
            (index, float(row["base_pnl"]))
            for index, row in enumerate(rows)
            if float(row["base_pnl"]) > 0
        ]
        winners = sorted(winners, key=lambda item: item[1], reverse=True)

        if suffix.endswith("pct"):
            pct = float(suffix.replace("pct", "")) / 100.0
            remove_count = max(1, math.ceil(len(winners) * pct)) if winners else 0
        else:
            remove_count = int(suffix)

        remove_indexes = {index for index, _ in winners[:remove_count]}
        filtered = [
            row
            for index, row in enumerate(rows)
            if index not in remove_indexes
        ]

        details["removed_trade_count"] = len(remove_indexes)
        details["removed_reason"] = "top_winners"
        return filtered, details

    if scenario_name in {"exclude_best_year", "exclude_worst_year"}:
        year_totals = sum_by(rows, "year")

        if not year_totals:
            return rows, details

        if scenario_name == "exclude_best_year":
            target_year = max(year_totals.items(), key=lambda item: item[1])[0]
        else:
            target_year = min(year_totals.items(), key=lambda item: item[1])[0]

        filtered = [
            row
            for row in rows
            if str(row.get("year")) != str(target_year)
        ]

        details["excluded_year"] = target_year
        details["excluded_year_pnl"] = year_totals[target_year]
        return filtered, details

    if scenario_name == "remove_top_symbol":
        symbols = top_keys_by_positive_contribution(rows, "symbol", 1)
        filtered = [row for row in rows if row["symbol"] not in symbols]
        details["removed_symbols"] = symbols
        return filtered, details

    if scenario_name == "remove_top5_symbols":
        symbols = top_keys_by_positive_contribution(rows, "symbol", 5)
        filtered = [row for row in rows if row["symbol"] not in symbols]
        details["removed_symbols"] = symbols
        return filtered, details

    if scenario_name == "remove_top_strategy":
        strategies = top_keys_by_positive_contribution(rows, "strategy", 1)
        filtered = [row for row in rows if row["strategy"] not in strategies]
        details["removed_strategies"] = strategies
        return filtered, details

    if scenario_name == "remove_top3_strategies":
        strategies = top_keys_by_positive_contribution(rows, "strategy", 3)
        filtered = [row for row in rows if row["strategy"] not in strategies]
        details["removed_strategies"] = strategies
        return filtered, details

    if scenario_name.startswith("execution_worse_fills_"):
        multiplier = float(scenario_name.replace("execution_worse_fills_", ""))

        total_execution_cost = 0.0
        cost_sources: dict[str, int] = defaultdict(int)
        cost_source_type_counts: dict[str, int] = defaultdict(int)
        spread_dollar_cost_mode_counts: dict[str, int] = defaultdict(int)

        for row in rows:
            cost, source, cost_details = get_execution_cost_dollars(
                row=row,
                fill_stress_multiplier=multiplier,
                default_round_trip_spread_cost_pct_of_risk=default_round_trip_spread_cost_pct_of_risk,
                contracts_per_trade_fallback=contracts_per_trade_fallback,
                option_contract_multiplier=option_contract_multiplier,
            )

            row["base_pnl"] = float(row["base_pnl"]) - cost
            total_execution_cost += cost
            cost_sources[source] += 1
            cost_source_type_counts[str(cost_details.get("cost_source_type"))] += 1
            if cost_details.get("spread_dollar_cost_mode"):
                spread_dollar_cost_mode_counts[str(cost_details["spread_dollar_cost_mode"])] += 1

        details["execution_stress_type"] = "worse_fills"
        details["fill_stress_multiplier"] = multiplier
        details["default_round_trip_spread_cost_pct_of_risk"] = default_round_trip_spread_cost_pct_of_risk
        details["option_contract_multiplier"] = option_contract_multiplier
        details["total_execution_cost_dollars"] = total_execution_cost
        details["cost_sources"] = dict(sorted(cost_sources.items()))
        details["cost_source_type_counts"] = dict(sorted(cost_source_type_counts.items()))
        details["spread_dollar_cost_mode_counts"] = dict(sorted(spread_dollar_cost_mode_counts.items()))
        return rows, details

    if scenario_name == "execution_no_mid_bid_ask_conservative":
        total_execution_cost = 0.0
        cost_sources: dict[str, int] = defaultdict(int)
        cost_source_type_counts: dict[str, int] = defaultdict(int)
        spread_dollar_cost_mode_counts: dict[str, int] = defaultdict(int)

        for row in rows:
            cost, source, cost_details = get_execution_cost_dollars(
                row=row,
                fill_stress_multiplier=1.0,
                default_round_trip_spread_cost_pct_of_risk=default_round_trip_spread_cost_pct_of_risk,
                contracts_per_trade_fallback=contracts_per_trade_fallback,
                option_contract_multiplier=option_contract_multiplier,
            )

            row["base_pnl"] = float(row["base_pnl"]) - cost
            total_execution_cost += cost
            cost_sources[source] += 1
            cost_source_type_counts[str(cost_details.get("cost_source_type"))] += 1
            if cost_details.get("spread_dollar_cost_mode"):
                spread_dollar_cost_mode_counts[str(cost_details["spread_dollar_cost_mode"])] += 1

        details["execution_stress_type"] = "no_mid_bid_ask_conservative"
        details["default_round_trip_spread_cost_pct_of_risk"] = default_round_trip_spread_cost_pct_of_risk
        details["option_contract_multiplier"] = option_contract_multiplier
        details["total_execution_cost_dollars"] = total_execution_cost
        details["cost_sources"] = dict(sorted(cost_sources.items()))
        details["cost_source_type_counts"] = dict(sorted(cost_source_type_counts.items()))
        details["spread_dollar_cost_mode_counts"] = dict(sorted(spread_dollar_cost_mode_counts.items()))
        return rows, details

    if scenario_name == "execution_skip_wide_spreads":
        filtered: list[dict[str, Any]] = []
        skipped_count = 0
        missing_spread_count = 0
        observed_spread_count = 0
        spread_source_counts: dict[str, int] = defaultdict(int)

        for row in rows:
            spread_pct, spread_source = get_spread_pct(row)

            if spread_pct is None:
                missing_spread_count += 1
                filtered.append(row)
                continue

            observed_spread_count += 1
            spread_source_counts[str(spread_source)] += 1

            if spread_pct > allowed_spread_pct:
                skipped_count += 1
                continue

            filtered.append(row)

        details["execution_stress_type"] = "skip_wide_spreads"
        details["allowed_spread_pct"] = allowed_spread_pct
        details["skipped_trade_count"] = skipped_count
        details["missing_spread_count"] = missing_spread_count
        details["observed_spread_count"] = observed_spread_count
        details["spread_source_counts"] = dict(sorted(spread_source_counts.items()))
        return filtered, details

    if scenario_name == "execution_ibkr_like_commissions_and_fees":
        total_fee_cost = 0.0
        total_contract_units = 0.0
        contract_count_sources: dict[str, int] = defaultdict(int)

        for row in rows:
            fee_cost, fee_details = get_commission_and_fee_dollars(
                row=row,
                commission_per_contract=commission_per_contract,
                regulatory_fee_per_contract=regulatory_fee_per_contract,
                clearing_fee_per_contract=clearing_fee_per_contract,
                activity_fee_per_contract=activity_fee_per_contract,
                contracts_per_trade_fallback=contracts_per_trade_fallback,
                round_trip_sides=round_trip_sides,
            )

            row["base_pnl"] = float(row["base_pnl"]) - fee_cost
            total_fee_cost += fee_cost
            total_contract_units += fee_details["total_contract_units"]
            contract_count_sources[fee_details["contract_count_source"]] += 1

        details["execution_stress_type"] = "ibkr_like_commissions_and_fees"
        details["commission_per_contract"] = commission_per_contract
        details["regulatory_fee_per_contract"] = regulatory_fee_per_contract
        details["clearing_fee_per_contract"] = clearing_fee_per_contract
        details["activity_fee_per_contract"] = activity_fee_per_contract
        details["contracts_per_trade_fallback"] = contracts_per_trade_fallback
        details["round_trip_sides"] = round_trip_sides
        details["total_fee_cost_dollars"] = total_fee_cost
        details["total_contract_units"] = total_contract_units
        details["contract_count_sources"] = dict(sorted(contract_count_sources.items()))
        return rows, details

    if scenario_name in {
        "execution_live_realism_spread10_no_mid_fees",
        "execution_live_realism_spread05_no_mid_fees",
    }:
        allowed_live_spread_pct = (
            0.10
            if scenario_name == "execution_live_realism_spread10_no_mid_fees"
            else 0.05
        )

        filtered_rows: list[dict[str, Any]] = []
        skipped_count = 0
        missing_spread_count = 0
        observed_spread_count = 0
        spread_source_counts: dict[str, int] = defaultdict(int)
        cost_sources: dict[str, int] = defaultdict(int)
        cost_source_type_counts: dict[str, int] = defaultdict(int)
        spread_dollar_cost_mode_counts: dict[str, int] = defaultdict(int)
        contract_count_sources: dict[str, int] = defaultdict(int)
        total_execution_cost = 0.0
        total_fee_cost = 0.0
        total_contract_units = 0.0

        for row in rows:
            spread_pct, spread_source = get_spread_pct(row)

            if spread_pct is None:
                missing_spread_count += 1
            else:
                observed_spread_count += 1
                spread_source_counts[str(spread_source)] += 1
                if spread_pct > allowed_live_spread_pct:
                    skipped_count += 1
                    continue

            execution_cost, execution_source, execution_details = get_execution_cost_dollars(
                row=row,
                fill_stress_multiplier=1.0,
                default_round_trip_spread_cost_pct_of_risk=default_round_trip_spread_cost_pct_of_risk,
                contracts_per_trade_fallback=contracts_per_trade_fallback,
                option_contract_multiplier=option_contract_multiplier,
            )
            fee_cost, fee_details = get_commission_and_fee_dollars(
                row=row,
                commission_per_contract=commission_per_contract,
                regulatory_fee_per_contract=regulatory_fee_per_contract,
                clearing_fee_per_contract=clearing_fee_per_contract,
                activity_fee_per_contract=activity_fee_per_contract,
                contracts_per_trade_fallback=contracts_per_trade_fallback,
                round_trip_sides=round_trip_sides,
            )

            stressed_row = dict(row)
            stressed_row["base_pnl"] = float(stressed_row["base_pnl"]) - execution_cost - fee_cost
            filtered_rows.append(stressed_row)

            total_execution_cost += execution_cost
            total_fee_cost += fee_cost
            total_contract_units += fee_details["total_contract_units"]
            cost_sources[execution_source] += 1
            cost_source_type_counts[str(execution_details.get("cost_source_type"))] += 1
            if execution_details.get("spread_dollar_cost_mode"):
                spread_dollar_cost_mode_counts[str(execution_details["spread_dollar_cost_mode"])] += 1
            contract_count_sources[fee_details["contract_count_source"]] += 1

        details["execution_stress_type"] = "combined_live_realism_spread_gate_no_mid_fees"
        details["allowed_spread_pct"] = allowed_live_spread_pct
        details["skipped_trade_count"] = skipped_count
        details["missing_spread_count"] = missing_spread_count
        details["observed_spread_count"] = observed_spread_count
        details["spread_source_counts"] = dict(sorted(spread_source_counts.items()))
        details["fill_stress_multiplier"] = 1.0
        details["default_round_trip_spread_cost_pct_of_risk"] = default_round_trip_spread_cost_pct_of_risk
        details["option_contract_multiplier"] = option_contract_multiplier
        details["commission_per_contract"] = commission_per_contract
        details["regulatory_fee_per_contract"] = regulatory_fee_per_contract
        details["clearing_fee_per_contract"] = clearing_fee_per_contract
        details["activity_fee_per_contract"] = activity_fee_per_contract
        details["contracts_per_trade_fallback"] = contracts_per_trade_fallback
        details["round_trip_sides"] = round_trip_sides
        details["total_execution_cost_dollars"] = total_execution_cost
        details["total_fee_cost_dollars"] = total_fee_cost
        details["total_combined_execution_and_fee_cost_dollars"] = total_execution_cost + total_fee_cost
        details["total_contract_units"] = total_contract_units
        details["cost_sources"] = dict(sorted(cost_sources.items()))
        details["cost_source_type_counts"] = dict(sorted(cost_source_type_counts.items()))
        details["spread_dollar_cost_mode_counts"] = dict(sorted(spread_dollar_cost_mode_counts.items()))
        details["contract_count_sources"] = dict(sorted(contract_count_sources.items()))
        return filtered_rows, details

    raise ValueError(f"Unsupported scenario: {scenario_name}")


def calculate_metrics(
    rows: list[dict[str, Any]],
    starting_capital: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    equity = starting_capital
    peak = starting_capital
    max_drawdown = 0.0
    max_drawdown_pct = 0.0

    equity_rows: list[dict[str, Any]] = []
    pnls: list[float] = []
    trade_returns: list[float] = []

    for new_sequence_index, row in enumerate(rows):
        pnl = float(row["base_pnl"])

        equity_before = equity
        equity_after = equity_before + pnl

        peak = max(peak, equity_after)

        drawdown = equity_after - peak
        drawdown_pct = drawdown / peak if peak else 0.0

        max_drawdown = min(max_drawdown, drawdown)
        max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)

        trade_return_on_equity = pnl / equity_before if equity_before else 0.0

        pnls.append(pnl)
        trade_returns.append(trade_return_on_equity)

        equity_rows.append(
            {
                "sequence_index": new_sequence_index,
                "source_sequence_index": row["sequence_index"],
                "date": row["date"],
                "year": row["year"],
                "symbol": row["symbol"],
                "strategy": row["strategy"],
                "pnl": pnl,
                "equity_before": equity_before,
                "equity_after": equity_after,
                "trade_return_on_equity": trade_return_on_equity,
                "drawdown": drawdown,
                "drawdown_pct": drawdown_pct,
            }
        )

        equity = equity_after

    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]

    total_pnl = sum(pnls)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    downside_returns = [x for x in trade_returns if x < 0]

    if len(trade_returns) >= 2 and stdev(trade_returns) != 0:
        sharpe_like = mean(trade_returns) / stdev(trade_returns) * math.sqrt(len(trade_returns))
    else:
        sharpe_like = None

    if len(downside_returns) >= 2 and stdev(downside_returns) != 0:
        sortino_like = mean(trade_returns) / stdev(downside_returns) * math.sqrt(len(trade_returns))
    else:
        sortino_like = None

    metrics = {
        "starting_capital": starting_capital,
        "ending_capital": equity,
        "total_pnl": total_pnl,
        "total_return": total_pnl / starting_capital if starting_capital else None,
        "trade_count": len(rows),
        "winning_trade_count": len(wins),
        "losing_trade_count": len(losses),
        "win_rate": len(wins) / len(rows) if rows else None,
        "average_pnl": mean(pnls) if pnls else None,
        "median_pnl": median(pnls) if pnls else None,
        "average_win": mean(wins) if wins else None,
        "average_loss": mean(losses) if losses else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "trade_return_sharpe_like": sharpe_like,
        "trade_return_sortino_like": sortino_like,
    }

    return metrics, equity_rows


def concentration_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_pnl = sum(float(row["base_pnl"]) for row in rows)
    total_positive_pnl = sum(
        float(row["base_pnl"])
        for row in rows
        if float(row["base_pnl"]) > 0
    )

    def ranked(key: str) -> list[dict[str, Any]]:
        pnl_totals = sum_by(rows, key)
        counts = count_by(rows, key)

        output = []

        for name, pnl in pnl_totals.items():
            positive_contribution_pct = (
                pnl / total_positive_pnl
                if total_positive_pnl and pnl > 0
                else 0.0
            )
            total_pnl_pct = pnl / total_pnl if total_pnl else None

            output.append(
                {
                    key: name,
                    "trade_count": counts.get(name, 0),
                    "pnl": pnl,
                    "total_pnl_pct": total_pnl_pct,
                    "positive_contribution_pct": positive_contribution_pct,
                }
            )

        return sorted(output, key=lambda item: item["pnl"], reverse=True)

    return {
        "total_pnl": total_pnl,
        "total_positive_pnl": total_positive_pnl,
        "top_symbols": ranked("symbol")[:25],
        "top_strategies": ranked("strategy")[:25],
        "years": ranked("year"),
    }


def robustness_verdict(
    baseline_metrics: dict[str, Any],
    scenario_metrics: list[dict[str, Any]],
    baseline_concentration: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    baseline_total_return = baseline_metrics.get("total_return")

    if baseline_total_return is None or baseline_total_return <= 0:
        blockers.append("baseline_total_return_not_positive")

    mild_stress_names = {
        "win_haircut_0.1",
        "loss_inflation_0.1",
        "combined_adverse_0.1",
        "cap_winners_p95",
        "remove_top_winners_1",
    }

    scenario_by_name = {
        row["scenario_name"]: row
        for row in scenario_metrics
    }

    for name in mild_stress_names:
        scenario = scenario_by_name.get(name)
        if not scenario:
            continue

        total_return = scenario.get("total_return")
        if total_return is not None and total_return <= 0:
            warnings.append(f"mild_stress_non_positive_return:{name}")

    top_symbols = baseline_concentration.get("top_symbols", [])
    if top_symbols:
        top_symbol_pct = top_symbols[0].get("positive_contribution_pct") or 0.0
        if top_symbol_pct >= 0.50:
            warnings.append("top_symbol_exceeds_50pct_positive_contribution")

    top_strategies = baseline_concentration.get("top_strategies", [])
    if top_strategies:
        top_strategy_pct = top_strategies[0].get("positive_contribution_pct") or 0.0
        if top_strategy_pct >= 0.50:
            warnings.append("top_strategy_exceeds_50pct_positive_contribution")

    if blockers:
        return "blocked", blockers, warnings

    if warnings:
        return "needs_review", blockers, warnings

    return "pass", blockers, warnings


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def build_portfolio_robustness_stress_validation(
    trade_ledger: Path,
    output_dir: Path,
    starting_capital: float,
    selected_trade_sequence_summary: Path | None = None,
    position_sizing_summary: Path | None = None,
    equity_reconstruction_summary: Path | None = None,
    metrics_report: Path | None = None,
    default_round_trip_spread_cost_pct_of_risk: float = 0.02,
    allowed_spread_pct: float = 0.25,
    commission_per_contract: float = 0.65,
    regulatory_fee_per_contract: float = 0.02295,
    clearing_fee_per_contract: float = 0.025,
    activity_fee_per_contract: float = 0.00329,
    contracts_per_trade_fallback: float = 1.0,
    round_trip_sides: float = 2.0,
    option_contract_multiplier: float = 100.0,
) -> dict[str, Any]:
    raw_rows = read_json_or_jsonl(trade_ledger)
    trades, input_diagnostics = normalize_trade_rows(raw_rows)

    scenario_names = [
        "baseline",
        "risk_scale_0.5",
        "risk_scale_0.75",
        "risk_scale_1.25",
        "win_haircut_0.1",
        "win_haircut_0.2",
        "win_haircut_0.25",
        "loss_inflation_0.1",
        "loss_inflation_0.2",
        "loss_inflation_0.25",
        "combined_adverse_0.1",
        "combined_adverse_0.2",
        "cap_winners_p95",
        "cap_winners_p90",
        "remove_top_winners_1",
        "remove_top_winners_5",
        "remove_top_winners_1pct",
        "remove_top_winners_5pct",
        "exclude_best_year",
        "exclude_worst_year",
        "remove_top_symbol",
        "remove_top5_symbols",
        "remove_top_strategy",
        "remove_top3_strategies",
        "execution_worse_fills_0.25",
        "execution_worse_fills_0.5",
        "execution_worse_fills_1.0",
        "execution_no_mid_bid_ask_conservative",
        "execution_skip_wide_spreads",
        "execution_ibkr_like_commissions_and_fees",
        "execution_live_realism_spread10_no_mid_fees",
        "execution_live_realism_spread05_no_mid_fees",
    ]

    scenario_rows: list[dict[str, Any]] = []
    all_equity_rows: list[dict[str, Any]] = []

    baseline_metrics: dict[str, Any] | None = None
    baseline_concentration: dict[str, Any] | None = None

    for scenario_name in scenario_names:
        stressed_rows, scenario_details = build_scenario_rows(
            trades=trades,
            scenario_name=scenario_name,
            default_round_trip_spread_cost_pct_of_risk=default_round_trip_spread_cost_pct_of_risk,
            allowed_spread_pct=allowed_spread_pct,
            commission_per_contract=commission_per_contract,
            regulatory_fee_per_contract=regulatory_fee_per_contract,
            clearing_fee_per_contract=clearing_fee_per_contract,
            activity_fee_per_contract=activity_fee_per_contract,
            contracts_per_trade_fallback=contracts_per_trade_fallback,
            round_trip_sides=round_trip_sides,
            option_contract_multiplier=option_contract_multiplier,
        )
        metrics, equity_rows = calculate_metrics(stressed_rows, starting_capital)
        scenario_concentration = concentration_summary(stressed_rows)

        scenario_record = {
            "scenario_name": scenario_name,
            "scenario_details": scenario_details,
            **metrics,
            "top_symbol": (
                scenario_concentration["top_symbols"][0]["symbol"]
                if scenario_concentration["top_symbols"]
                else None
            ),
            "top_symbol_positive_contribution_pct": (
                scenario_concentration["top_symbols"][0]["positive_contribution_pct"]
                if scenario_concentration["top_symbols"]
                else None
            ),
            "top_strategy": (
                scenario_concentration["top_strategies"][0]["strategy"]
                if scenario_concentration["top_strategies"]
                else None
            ),
            "top_strategy_positive_contribution_pct": (
                scenario_concentration["top_strategies"][0]["positive_contribution_pct"]
                if scenario_concentration["top_strategies"]
                else None
            ),
        }

        scenario_rows.append(scenario_record)

        for equity_row in equity_rows:
            all_equity_rows.append(
                {
                    "scenario_name": scenario_name,
                    **equity_row,
                }
            )

        if scenario_name == "baseline":
            baseline_metrics = metrics
            baseline_concentration = scenario_concentration

    assert baseline_metrics is not None
    assert baseline_concentration is not None

    verdict, blockers, warnings = robustness_verdict(
        baseline_metrics=baseline_metrics,
        scenario_metrics=scenario_rows,
        baseline_concentration=baseline_concentration,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "signalforge_portfolio_robustness_stress_validation_summary.json"
    scenarios_path = output_dir / "signalforge_portfolio_robustness_stress_validation_scenarios.jsonl"
    equity_curves_path = output_dir / "signalforge_portfolio_robustness_stress_validation_equity_curves.jsonl"
    concentration_path = output_dir / "signalforge_portfolio_robustness_stress_validation_concentration.json"

    provenance = {
        "trade_ledger": str(trade_ledger),
        "selected_trade_sequence_summary": (
            str(selected_trade_sequence_summary)
            if selected_trade_sequence_summary
            else None
        ),
        "position_sizing_summary": (
            str(position_sizing_summary)
            if position_sizing_summary
            else None
        ),
        "equity_reconstruction_summary": (
            str(equity_reconstruction_summary)
            if equity_reconstruction_summary
            else None
        ),
        "metrics_report": str(metrics_report) if metrics_report else None,
    }

    summary = {
        "adapter_type": "portfolio_robustness_stress_validation_builder",
        "artifact_type": "signalforge_portfolio_robustness_stress_validation",
        "contract": "portfolio_robustness_stress_validation",
        "is_ready": verdict != "blocked",
        "readiness_state": verdict,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "provenance": provenance,
        "input_diagnostics": input_diagnostics,
        "starting_capital": starting_capital,
        "execution_stress_assumptions": {
            "default_round_trip_spread_cost_pct_of_risk": default_round_trip_spread_cost_pct_of_risk,
            "allowed_spread_pct": allowed_spread_pct,
            "commission_per_contract": commission_per_contract,
            "regulatory_fee_per_contract": regulatory_fee_per_contract,
            "clearing_fee_per_contract": clearing_fee_per_contract,
            "activity_fee_per_contract": activity_fee_per_contract,
            "contracts_per_trade_fallback": contracts_per_trade_fallback,
            "round_trip_sides": round_trip_sides,
            "option_contract_multiplier": option_contract_multiplier,
            "spread_dollar_cost_model": "round_trip_spread_cost_dollars is raw; bid_ask/spread/quote dollar fields are treated as premium widths and scaled by contracts * option_contract_multiplier",
            "notes": [
                "Spread scenarios use explicit spread fields when available.",
                "If spread fields are missing, worse-fill scenarios use default_round_trip_spread_cost_pct_of_risk as a proxy.",
                "Wide-spread skip scenario only skips trades with observable spread_pct fields.",
                "Commission and fee scenario uses contract count fields when available; otherwise uses contracts_per_trade_fallback and inferred strategy leg count.",
                "Combined live-realism scenarios apply a spread gate, no-mid conservative spread cost, and IBKR-like commissions/fees together.",
            ],
        },
        "scenario_count": len(scenario_rows),
        "baseline_metrics": baseline_metrics,
        "baseline_concentration": baseline_concentration,
        "paths": {
            "summary_path": str(summary_path),
            "scenarios_path": str(scenarios_path),
            "equity_curves_path": str(equity_curves_path),
            "concentration_path": str(concentration_path),
        },
        "explicit_exclusions": [
            "broker_api_calls",
            "order_routing",
            "order_submission",
            "fills",
            "live_execution",
            "trade_reselection",
            "expectancy_rebuild",
            "strategy_optimization",
            "parameter_tuning",
            "full_broker_fill_simulation",
            "order_book_queue_modeling",
            "market_impact_modeling",
        ],
    }

    write_json(summary_path, summary)
    write_jsonl(scenarios_path, scenario_rows)
    write_jsonl(equity_curves_path, all_equity_rows)
    write_json(concentration_path, baseline_concentration)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Phase 7 portfolio robustness / stress validation artifacts."
    )

    parser.add_argument(
        "--trade-ledger",
        required=True,
        help="Trade-level Phase 6 portfolio ledger JSON or JSONL.",
    )
    parser.add_argument(
        "--starting-capital",
        type=float,
        required=True,
        help="Starting capital used for stress equity reconstruction.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output artifact directory.",
    )
    parser.add_argument(
        "--selected-trade-sequence-summary",
        default=None,
    )
    parser.add_argument(
        "--position-sizing-summary",
        default=None,
    )
    parser.add_argument(
        "--equity-reconstruction-summary",
        default=None,
    )
    parser.add_argument(
        "--metrics-report",
        default=None,
    )
    parser.add_argument(
        "--default-round-trip-spread-cost-pct-of-risk",
        type=float,
        default=0.02,
        help="Fallback round-trip spread/fill cost as pct of position risk when quote spread fields are unavailable.",
    )
    parser.add_argument(
        "--allowed-spread-pct",
        type=float,
        default=0.25,
        help="Spread threshold for execution_skip_wide_spreads when spread pct fields exist.",
    )
    parser.add_argument(
        "--commission-per-contract",
        type=float,
        default=0.65,
        help="Commission per option contract used in execution fee stress.",
    )
    parser.add_argument(
        "--regulatory-fee-per-contract",
        type=float,
        default=0.02295,
        help="Regulatory-style fee per option contract used in execution fee stress.",
    )
    parser.add_argument(
        "--clearing-fee-per-contract",
        type=float,
        default=0.025,
        help="Clearing-style fee per option contract used in execution fee stress.",
    )
    parser.add_argument(
        "--activity-fee-per-contract",
        type=float,
        default=0.00329,
        help="Activity / transaction-style fee per option contract used in execution fee stress.",
    )
    parser.add_argument(
        "--contracts-per-trade-fallback",
        type=float,
        default=1.0,
        help="Fallback contracts per trade when contract count is unavailable.",
    )
    parser.add_argument(
        "--round-trip-sides",
        type=float,
        default=2.0,
        help="Open + close sides multiplier for round-trip fee modeling.",
    )
    parser.add_argument(
        "--option-contract-multiplier",
        type=float,
        default=100.0,
        help="Multiplier used to convert option premium-width spread dollars into trade dollars. Default: 100.",
    )
    parser.add_argument(
        "--fail-on-blocker",
        action="store_true",
    )

    args = parser.parse_args()

    summary = build_portfolio_robustness_stress_validation(
        trade_ledger=Path(args.trade_ledger),
        output_dir=Path(args.output_dir),
        starting_capital=args.starting_capital,
        selected_trade_sequence_summary=(
            Path(args.selected_trade_sequence_summary)
            if args.selected_trade_sequence_summary
            else None
        ),
        position_sizing_summary=(
            Path(args.position_sizing_summary)
            if args.position_sizing_summary
            else None
        ),
        equity_reconstruction_summary=(
            Path(args.equity_reconstruction_summary)
            if args.equity_reconstruction_summary
            else None
        ),
        metrics_report=Path(args.metrics_report) if args.metrics_report else None,
        default_round_trip_spread_cost_pct_of_risk=args.default_round_trip_spread_cost_pct_of_risk,
        allowed_spread_pct=args.allowed_spread_pct,
        commission_per_contract=args.commission_per_contract,
        regulatory_fee_per_contract=args.regulatory_fee_per_contract,
        clearing_fee_per_contract=args.clearing_fee_per_contract,
        activity_fee_per_contract=args.activity_fee_per_contract,
        contracts_per_trade_fallback=args.contracts_per_trade_fallback,
        round_trip_sides=args.round_trip_sides,
        option_contract_multiplier=args.option_contract_multiplier,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.fail_on_blocker and summary.get("blocker_count", 0) > 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())