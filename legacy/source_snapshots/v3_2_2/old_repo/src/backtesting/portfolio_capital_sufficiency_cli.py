
"""Capital sufficiency replay for SignalForge portfolio ledgers.

This module replays the already-selected/sized historical trade ledger across a grid of
starting capital levels. It is intentionally conservative and transparent: it does not
reselect trades, rebuild expectancy, optimize strategy choice, or simulate broker fills.

The objective is to identify the minimum deployable capital where the validated edge
remains executable, diversified, and robust after execution friction.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import argparse
import json
import math
import statistics


DEFAULT_CAPITALS = [2500, 5000, 7500, 10000, 12500, 15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000, 150000, 250000]

NUMERIC_NONE = {None, "", "null", "None", "nan", "NaN"}


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in NUMERIC_NONE:
        return default
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    return value


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    value = _to_float(value, None)
    if value is None:
        return default
    return int(value)


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(payload, dict):
                yield payload


def _find_nested(row: Dict[str, Any], keys: Iterable[str]) -> Tuple[Optional[Any], Optional[str]]:
    """Find the first available key at top level or common nested payloads."""
    key_list = list(keys)
    for key in key_list:
        if key in row and row.get(key) not in NUMERIC_NONE:
            return row.get(key), key
    for container_key in ("execution_realism_payload", "selected_execution_realism_payload", "source_row", "selected_source_row"):
        nested = row.get(container_key)
        if isinstance(nested, dict):
            value, source = _find_nested(nested, key_list)
            if value not in NUMERIC_NONE:
                return value, f"{container_key}.{source}"
    return None, None


def _date_key(row: Dict[str, Any]) -> str:
    for key in ("portfolio_realization_date", "outcome_availability_date", "selected_outcome_availability_date", "decision_date", "entry_date"):
        value = row.get(key)
        if value:
            return str(value)
    return "9999-12-31"


def _strategy(row: Dict[str, Any]) -> str:
    return str(row.get("selected_strategy") or row.get("strategy") or row.get("strategy_name") or "unknown")


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("underlying") or row.get("underlying_symbol") or "unknown")


def _year(row: Dict[str, Any]) -> str:
    date = _date_key(row)
    return date[:4] if len(date) >= 4 else "unknown"


def _realized_return(row: Dict[str, Any]) -> Optional[float]:
    value, _ = _find_nested(row, ("realized_return", "strategy_adjusted_return", "selected_strategy_adjusted_return"))
    return _to_float(value)


def _baseline_risk(row: Dict[str, Any]) -> Optional[float]:
    value, _ = _find_nested(row, ("position_risk_dollars", "risk_capital", "selected_risk_capital", "risk_amount"))
    value = _to_float(value)
    if value is None or value <= 0:
        return None
    return value


def _contract_units(row: Dict[str, Any], fallback: float = 1.0) -> Tuple[float, str]:
    # contract_quantity is preferred for sizing granularity. contract_count can be total contract/leg units.
    for key in (
        "contract_quantity",
        "position_contract_quantity",
        "quantity",
        "contracts",
        "contract_count",
        "fallback_contract_count",
    ):
        value, source = _find_nested(row, (key,))
        value = _to_float(value)
        if value is not None and value > 0:
            return value, str(source or key)
    return fallback, "contracts_per_trade_fallback"


def _spread_pct(row: Dict[str, Any]) -> Optional[float]:
    value, _ = _find_nested(row, ("spread_pct", "bid_ask_spread_pct", "entry_spread_pct", "quote_spread_pct"))
    return _to_float(value)


def _spread_dollars(row: Dict[str, Any]) -> Optional[float]:
    value, _ = _find_nested(row, (
        "round_trip_spread_cost_dollars",
        "bid_ask_spread_dollars",
        "spread_width_dollars",
        "spread_dollars",
        "entry_spread_dollars",
        "quote_spread_dollars",
    ))
    return _to_float(value)


def _spread_cost(row: Dict[str, Any], units: float, multiplier: float, fallback_cost_pct_of_risk: float, risk_amount: float) -> Tuple[float, str]:
    value, source = _find_nested(row, ("round_trip_spread_cost_dollars",))
    raw = _to_float(value)
    if raw is not None and raw >= 0:
        return raw, f"{source}:raw_round_trip_cost"

    value, source = _find_nested(row, (
        "bid_ask_spread_dollars",
        "spread_width_dollars",
        "spread_dollars",
        "entry_spread_dollars",
        "quote_spread_dollars",
    ))
    premium_width = _to_float(value)
    if premium_width is not None and premium_width >= 0:
        return premium_width * max(units, 1.0) * multiplier, f"{source}:premium_width_x_contract_units_x_multiplier"

    return risk_amount * fallback_cost_pct_of_risk, "default_round_trip_spread_cost_pct_of_risk"


def _fee_cost(units: float, commission: float, regulatory: float, clearing: float, activity: float, round_trip_sides: float) -> float:
    per_contract_side = commission + regulatory + clearing + activity
    return max(units, 0.0) * per_contract_side * round_trip_sides


def _max_drawdown_pct(equity_values: List[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    max_dd = 0.0
    for equity in equity_values:
        peak = max(peak, equity)
        if peak > 0:
            dd = (equity - peak) / peak
            max_dd = min(max_dd, dd)
    return max_dd


def _profit_factor(pnls: List[float]) -> Optional[float]:
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    if gross_loss == 0:
        return None if gross_profit == 0 else float("inf")
    return gross_profit / gross_loss


def _concentration(pnls_by_key: Dict[str, float], total_positive_pnl: float) -> Dict[str, Any]:
    if not pnls_by_key:
        return {"key": None, "pnl": 0.0, "positive_contribution_pct": 0.0}
    key, pnl = max(pnls_by_key.items(), key=lambda kv: kv[1])
    return {
        "key": key,
        "pnl": pnl,
        "positive_contribution_pct": (max(pnl, 0.0) / total_positive_pnl) if total_positive_pnl > 0 else 0.0,
    }


def _safe_div(n: float, d: float) -> Optional[float]:
    if d == 0:
        return None
    return n / d


@dataclass
class CapitalConfig:
    starting_capital: float
    risk_per_trade_pct: float
    max_trade_risk_dollars: float
    spread_gate_pct: Optional[float]
    option_contract_multiplier: float
    default_round_trip_spread_cost_pct_of_risk: float
    commission_per_contract: float
    regulatory_fee_per_contract: float
    clearing_fee_per_contract: float
    activity_fee_per_contract: float
    round_trip_sides: float
    contracts_per_trade_fallback: float
    max_min_contract_risk_pct_of_equity: float
    min_trade_risk_dollars: float


def replay_capital(rows: List[Dict[str, Any]], config: CapitalConfig) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    equity = config.starting_capital
    equity_curve: List[Dict[str, Any]] = []
    equity_values = [equity]
    pnls: List[float] = []
    realized_returns: List[float] = []
    effective_risk_pcts: List[float] = []
    risk_dollars: List[float] = []
    by_symbol: Dict[str, float] = {}
    by_strategy: Dict[str, float] = {}
    by_year: Dict[str, float] = {}
    source_counts: Dict[str, int] = {}
    spread_cost_source_counts: Dict[str, int] = {}

    attempted_trade_count = 0
    sized_trade_count = 0
    skipped_spread_count = 0
    skipped_insufficient_risk_budget_count = 0
    skipped_min_contract_oversize_count = 0
    skipped_missing_required_fields_count = 0
    skipped_non_positive_equity_count = 0
    min_contract_oversize_accepted_count = 0
    total_execution_cost = 0.0
    total_fee_cost = 0.0
    total_combined_cost = 0.0
    total_contract_units = 0.0

    for index, row in enumerate(sorted(rows, key=lambda r: (_date_key(r), _symbol(r), _strategy(r)))):
        ret = _realized_return(row)
        base_risk = _baseline_risk(row)
        if ret is None or base_risk is None:
            skipped_missing_required_fields_count += 1
            continue
        attempted_trade_count += 1
        if equity <= 0:
            skipped_non_positive_equity_count += 1
            continue
        spread = _spread_pct(row)
        if config.spread_gate_pct is not None and spread is not None and spread > config.spread_gate_pct:
            skipped_spread_count += 1
            continue

        source_units, unit_source = _contract_units(row, config.contracts_per_trade_fallback)
        source_units = max(source_units, config.contracts_per_trade_fallback, 1.0)
        # This is a proxy because the existing historical ledger stores selected contract units,
        # not a broker-native one-lot buying power requirement. It is still useful for capital stress.
        risk_per_contract_unit = base_risk / source_units
        target_risk = min(equity * config.risk_per_trade_pct, config.max_trade_risk_dollars)
        target_risk = max(target_risk, 0.0)
        if target_risk < config.min_trade_risk_dollars:
            skipped_insufficient_risk_budget_count += 1
            continue

        contract_units = math.floor(target_risk / risk_per_contract_unit) if risk_per_contract_unit > 0 else 0
        oversize_accepted = False
        if contract_units < 1:
            one_unit_risk_pct = risk_per_contract_unit / equity if equity > 0 else float("inf")
            if one_unit_risk_pct <= config.max_min_contract_risk_pct_of_equity:
                contract_units = 1
                oversize_accepted = True
                min_contract_oversize_accepted_count += 1
            else:
                skipped_min_contract_oversize_count += 1
                continue

        risk_amount = min(contract_units * risk_per_contract_unit, config.max_trade_risk_dollars, equity)
        if risk_amount <= 0:
            skipped_insufficient_risk_budget_count += 1
            continue

        source_counts[unit_source] = source_counts.get(unit_source, 0) + 1
        execution_cost, spread_source = _spread_cost(
            row,
            units=contract_units,
            multiplier=config.option_contract_multiplier,
            fallback_cost_pct_of_risk=config.default_round_trip_spread_cost_pct_of_risk,
            risk_amount=risk_amount,
        )
        fee_cost = _fee_cost(
            units=contract_units,
            commission=config.commission_per_contract,
            regulatory=config.regulatory_fee_per_contract,
            clearing=config.clearing_fee_per_contract,
            activity=config.activity_fee_per_contract,
            round_trip_sides=config.round_trip_sides,
        )
        pnl_before_costs = risk_amount * ret
        pnl = pnl_before_costs - execution_cost - fee_cost
        equity_before = equity
        equity += pnl
        sized_trade_count += 1
        pnls.append(pnl)
        realized_returns.append(ret)
        risk_dollars.append(risk_amount)
        effective_risk_pcts.append(risk_amount / equity_before if equity_before > 0 else 0.0)
        equity_values.append(equity)
        total_execution_cost += execution_cost
        total_fee_cost += fee_cost
        total_combined_cost += execution_cost + fee_cost
        total_contract_units += contract_units
        spread_cost_source_counts[spread_source] = spread_cost_source_counts.get(spread_source, 0) + 1

        sym = _symbol(row)
        strat = _strategy(row)
        yr = _year(row)
        by_symbol[sym] = by_symbol.get(sym, 0.0) + pnl
        by_strategy[strat] = by_strategy.get(strat, 0.0) + pnl
        by_year[yr] = by_year.get(yr, 0.0) + pnl

        equity_curve.append({
            "capital_scenario": config.starting_capital,
            "row_index": index,
            "date": _date_key(row),
            "symbol": sym,
            "strategy": strat,
            "equity_before_trade": equity_before,
            "equity_after_trade": equity,
            "risk_amount": risk_amount,
            "contract_units": contract_units,
            "risk_per_contract_unit_proxy": risk_per_contract_unit,
            "realized_return": ret,
            "pnl_before_costs": pnl_before_costs,
            "execution_cost_dollars": execution_cost,
            "fee_cost_dollars": fee_cost,
            "pnl_after_costs": pnl,
            "spread_pct": spread,
            "contract_unit_source": unit_source,
            "spread_cost_source": spread_source,
            "minimum_contract_oversize_accepted": oversize_accepted,
        })

    total_pnl = equity - config.starting_capital
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    total_positive_pnl = gross_profit
    pf = _profit_factor(pnls)
    max_dd = _max_drawdown_pct(equity_values)
    win_rate = _safe_div(sum(1 for p in pnls if p > 0), len(pnls)) if pnls else 0.0
    median_effective_risk = statistics.median(effective_risk_pcts) if effective_risk_pcts else 0.0
    max_effective_risk = max(effective_risk_pcts) if effective_risk_pcts else 0.0
    avg_effective_risk = statistics.mean(effective_risk_pcts) if effective_risk_pcts else 0.0

    row = {
        "capital_scenario": config.starting_capital,
        "starting_capital": config.starting_capital,
        "ending_capital": equity,
        "total_pnl": total_pnl,
        "total_return": _safe_div(total_pnl, config.starting_capital),
        "attempted_trade_count": attempted_trade_count,
        "sized_trade_count": sized_trade_count,
        "trade_retention_rate": _safe_div(sized_trade_count, attempted_trade_count) or 0.0,
        "skipped_trade_count": attempted_trade_count - sized_trade_count,
        "skipped_spread_count": skipped_spread_count,
        "skipped_insufficient_risk_budget_count": skipped_insufficient_risk_budget_count,
        "skipped_min_contract_oversize_count": skipped_min_contract_oversize_count,
        "skipped_missing_required_fields_count": skipped_missing_required_fields_count,
        "skipped_non_positive_equity_count": skipped_non_positive_equity_count,
        "minimum_contract_oversize_accepted_count": min_contract_oversize_accepted_count,
        "minimum_contract_oversize_accepted_rate": _safe_div(min_contract_oversize_accepted_count, max(sized_trade_count, 1)) or 0.0,
        "max_drawdown_pct": max_dd,
        "profit_factor": pf,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "average_trade_pnl": statistics.mean(pnls) if pnls else 0.0,
        "median_trade_pnl": statistics.median(pnls) if pnls else 0.0,
        "average_effective_risk_per_trade_pct": avg_effective_risk,
        "median_effective_risk_per_trade_pct": median_effective_risk,
        "max_effective_risk_per_trade_pct": max_effective_risk,
        "average_position_risk_dollars": statistics.mean(risk_dollars) if risk_dollars else 0.0,
        "median_position_risk_dollars": statistics.median(risk_dollars) if risk_dollars else 0.0,
        "max_position_risk_dollars": max(risk_dollars) if risk_dollars else 0.0,
        "total_execution_cost_dollars": total_execution_cost,
        "total_fee_cost_dollars": total_fee_cost,
        "total_combined_execution_and_fee_cost_dollars": total_combined_cost,
        "execution_cost_pct_of_gross_profit": _safe_div(total_combined_cost, gross_profit) or 0.0,
        "total_contract_units": total_contract_units,
        "contract_unit_source_counts": source_counts,
        "spread_cost_source_counts": spread_cost_source_counts,
        "top_symbol_concentration": _concentration(by_symbol, total_positive_pnl),
        "top_strategy_concentration": _concentration(by_strategy, total_positive_pnl),
        "top_year_concentration": _concentration(by_year, total_positive_pnl),
    }
    return row, equity_curve


def _gate_failure(
    gate_name: str,
    actual: Any,
    threshold: Any,
    comparator: str,
    severity: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "gate_name": gate_name,
        "actual": actual,
        "threshold": threshold,
        "comparator": comparator,
        "severity": severity,
        "message": message,
    }


def classify_capital(row: Dict[str, Any], thresholds: Dict[str, float]) -> Dict[str, Any]:
    blockers: List[str] = []
    warnings: List[str] = []
    gate_failures: List[Dict[str, Any]] = []
    gate_warnings: List[Dict[str, Any]] = []

    def add_blocker(name: str, actual: Any, threshold: Any, comparator: str, message: str) -> None:
        blockers.append(name)
        gate_failures.append(_gate_failure(name, actual, threshold, comparator, "blocker", message))

    def add_warning(name: str, actual: Any, threshold: Any, comparator: str, message: str) -> None:
        warnings.append(name)
        gate_warnings.append(_gate_failure(name, actual, threshold, comparator, "warning", message))

    total_pnl = row.get("total_pnl", 0.0)
    profit_factor = row.get("profit_factor")
    max_drawdown_abs = abs(row.get("max_drawdown_pct", 0.0))
    trade_retention = row.get("trade_retention_rate", 0.0)
    oversize_rate = row.get("minimum_contract_oversize_accepted_rate", 0.0)
    max_effective_risk = row.get("max_effective_risk_per_trade_pct", 0.0)
    execution_cost_drag = row.get("execution_cost_pct_of_gross_profit", 0.0)
    top_symbol_pct = row.get("top_symbol_concentration", {}).get("positive_contribution_pct", 0.0)
    top_strategy_pct = row.get("top_strategy_concentration", {}).get("positive_contribution_pct", 0.0)

    if row.get("sized_trade_count", 0) <= 0:
        add_blocker(
            "no_trades_sized",
            row.get("sized_trade_count", 0),
            1,
            ">=",
            "No trades were sized for this capital level.",
        )
    if total_pnl <= 0:
        add_blocker(
            "non_positive_total_pnl",
            total_pnl,
            0.0,
            ">",
            "Capital scenario did not produce positive total P/L.",
        )
    if profit_factor is None or profit_factor < thresholds["minimum_profit_factor"]:
        add_blocker(
            "profit_factor_below_minimum",
            profit_factor,
            thresholds["minimum_profit_factor"],
            ">=",
            "Profit factor is below the minimum viability threshold.",
        )
    if max_drawdown_abs > thresholds["maximum_drawdown_pct_abs"]:
        add_blocker(
            "max_drawdown_above_limit",
            max_drawdown_abs,
            thresholds["maximum_drawdown_pct_abs"],
            "<=",
            "Absolute max drawdown exceeds the viability limit.",
        )
    if trade_retention < thresholds["minimum_trade_retention_rate"]:
        add_blocker(
            "trade_retention_below_minimum",
            trade_retention,
            thresholds["minimum_trade_retention_rate"],
            ">=",
            "Too few candidate trades remain executable at this capital level.",
        )
    if oversize_rate > thresholds["maximum_min_contract_oversize_rate"]:
        add_blocker(
            "minimum_contract_oversize_rate_above_limit",
            oversize_rate,
            thresholds["maximum_min_contract_oversize_rate"],
            "<=",
            "Too many trades require accepting one-contract risk above target sizing.",
        )
    if max_effective_risk > thresholds["maximum_effective_risk_per_trade_pct"]:
        add_blocker(
            "max_effective_risk_per_trade_above_limit",
            max_effective_risk,
            thresholds["maximum_effective_risk_per_trade_pct"],
            "<=",
            "Worst effective risk per trade exceeds the configured one-trade risk cap.",
        )
    if top_symbol_pct > thresholds["maximum_top_symbol_positive_contribution_pct"]:
        add_warning(
            "top_symbol_concentration_above_preferred_limit",
            top_symbol_pct,
            thresholds["maximum_top_symbol_positive_contribution_pct"],
            "<=",
            "Top symbol positive contribution is above the preferred concentration limit.",
        )
    if top_strategy_pct > thresholds["maximum_top_strategy_positive_contribution_pct"]:
        add_warning(
            "top_strategy_concentration_above_preferred_limit",
            top_strategy_pct,
            thresholds["maximum_top_strategy_positive_contribution_pct"],
            "<=",
            "Top strategy positive contribution is above the preferred concentration limit.",
        )
    if execution_cost_drag > thresholds["maximum_execution_cost_pct_of_gross_profit"]:
        add_warning(
            "execution_cost_drag_above_preferred_limit",
            execution_cost_drag,
            thresholds["maximum_execution_cost_pct_of_gross_profit"],
            "<=",
            "Execution and fee costs consume too much gross profit.",
        )

    return {
        "capital_scenario": row.get("capital_scenario"),
        "passes_minimum_viable_gate": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "gate_failures": gate_failures,
        "gate_warnings": gate_warnings,
    }


def build_capital_sufficiency(
    trade_ledger: Path,
    output_dir: Path,
    starting_capitals: List[float],
    risk_per_trade_pct: float,
    max_trade_risk_dollars: float,
    spread_gate_pct: Optional[float],
    option_contract_multiplier: float,
    default_round_trip_spread_cost_pct_of_risk: float,
    commission_per_contract: float,
    regulatory_fee_per_contract: float,
    clearing_fee_per_contract: float,
    activity_fee_per_contract: float,
    round_trip_sides: float,
    contracts_per_trade_fallback: float,
    max_min_contract_risk_pct_of_equity: float,
    min_trade_risk_dollars: float,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_rows = list(_read_jsonl(trade_ledger))
    # Keep rows that look like sized selected trades.
    rows = []
    skipped_non_sized_count = 0
    for row in raw_rows:
        if _realized_return(row) is None or _baseline_risk(row) is None:
            skipped_non_sized_count += 1
            continue
        rows.append(row)

    thresholds = thresholds or {
        "minimum_profit_factor": 1.40,
        "maximum_drawdown_pct_abs": 0.25,
        "minimum_trade_retention_rate": 0.50,
        "maximum_min_contract_oversize_rate": 0.10,
        "maximum_effective_risk_per_trade_pct": max_min_contract_risk_pct_of_equity,
        "maximum_top_symbol_positive_contribution_pct": 0.15,
        "maximum_top_strategy_positive_contribution_pct": 0.50,
        "maximum_execution_cost_pct_of_gross_profit": 0.25,
    }

    scenario_rows: List[Dict[str, Any]] = []
    equity_curve_rows: List[Dict[str, Any]] = []
    gate_rows: List[Dict[str, Any]] = []

    for capital in sorted(starting_capitals):
        cfg = CapitalConfig(
            starting_capital=float(capital),
            risk_per_trade_pct=risk_per_trade_pct,
            max_trade_risk_dollars=max_trade_risk_dollars,
            spread_gate_pct=spread_gate_pct,
            option_contract_multiplier=option_contract_multiplier,
            default_round_trip_spread_cost_pct_of_risk=default_round_trip_spread_cost_pct_of_risk,
            commission_per_contract=commission_per_contract,
            regulatory_fee_per_contract=regulatory_fee_per_contract,
            clearing_fee_per_contract=clearing_fee_per_contract,
            activity_fee_per_contract=activity_fee_per_contract,
            round_trip_sides=round_trip_sides,
            contracts_per_trade_fallback=contracts_per_trade_fallback,
            max_min_contract_risk_pct_of_equity=max_min_contract_risk_pct_of_equity,
            min_trade_risk_dollars=min_trade_risk_dollars,
        )
        scenario, curve = replay_capital(rows, cfg)
        gate = classify_capital(scenario, thresholds)
        scenario["passes_minimum_viable_gate"] = gate["passes_minimum_viable_gate"]
        scenario["capital_gate_status"] = "pass" if gate["passes_minimum_viable_gate"] else "blocked"
        scenario["capital_gate_blockers"] = gate["blockers"]
        scenario["capital_gate_warnings"] = gate["warnings"]
        scenario["failure_reasons"] = gate["blockers"]
        scenario["warning_reasons"] = gate["warnings"]
        scenario["gate_failures"] = gate["gate_failures"]
        scenario["gate_warnings"] = gate["gate_warnings"]
        scenario["top_symbol_positive_contribution_pct"] = scenario.get("top_symbol_concentration", {}).get("positive_contribution_pct", 0.0)
        scenario["top_strategy_positive_contribution_pct"] = scenario.get("top_strategy_concentration", {}).get("positive_contribution_pct", 0.0)
        scenario["top_year_positive_contribution_pct"] = scenario.get("top_year_concentration", {}).get("positive_contribution_pct", 0.0)
        scenario_rows.append(scenario)
        gate_rows.append(gate)
        equity_curve_rows.extend(curve)

    passing = [r for r in scenario_rows if r["passes_minimum_viable_gate"]]
    profitable = [r for r in scenario_rows if r.get("total_pnl", 0.0) > 0]
    absolute_min = min((r["capital_scenario"] for r in profitable), default=None)
    minimum_viable = min((r["capital_scenario"] for r in passing), default=None)
    # Recommended: first passing capital with at least 70% trade retention and <= 2.5% max effective risk.
    recommended_candidates = [
        r for r in passing
        if r.get("trade_retention_rate", 0.0) >= 0.70 and r.get("max_effective_risk_per_trade_pct", 1.0) <= 0.025
    ]
    recommended = min((r["capital_scenario"] for r in recommended_candidates), default=minimum_viable)

    readiness_state = "pass" if minimum_viable is not None else "needs_review"
    blockers = [] if minimum_viable is not None else ["no_capital_scenario_passed_minimum_viable_gate"]
    warnings = []
    if absolute_min != minimum_viable:
        warnings.append("absolute_minimum_capital_differs_from_minimum_viable_capital")
    if recommended != minimum_viable:
        warnings.append("recommended_capital_is_above_minimum_viable_capital")

    gate_failure_counts: Dict[str, int] = {}
    gate_warning_counts: Dict[str, int] = {}
    for gate in gate_rows:
        for blocker in gate.get("blockers", []):
            gate_failure_counts[blocker] = gate_failure_counts.get(blocker, 0) + 1
        for warning in gate.get("warnings", []):
            gate_warning_counts[warning] = gate_warning_counts.get(warning, 0) + 1

    summary = {
        "adapter_type": "portfolio_capital_sufficiency_builder",
        "artifact_type": "signalforge_portfolio_capital_sufficiency",
        "contract": "portfolio_capital_sufficiency",
        "is_ready": True,
        "readiness_state": readiness_state,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "input_diagnostics": {
            "raw_row_count": len(raw_rows),
            "sized_trade_candidate_count": len(rows),
            "skipped_non_sized_or_missing_required_fields_count": skipped_non_sized_count,
        },
        "capital_answers": {
            "absolute_minimum_profitable_capital": absolute_min,
            "minimum_viable_deployment_capital": minimum_viable,
            "recommended_starting_capital": recommended,
            "capital_answer_policy": "absolute_minimum_is_lowest_profitable; minimum_viable_passes_quality_gates; recommended_adds_trade_retention_and_risk_buffer",
        },
        "gate_failure_counts": gate_failure_counts,
        "gate_warning_counts": gate_warning_counts,
        "scenario_count": len(scenario_rows),
        "starting_capitals": sorted(starting_capitals),
        "replay_policy": {
            "risk_per_trade_pct": risk_per_trade_pct,
            "max_trade_risk_dollars": max_trade_risk_dollars,
            "spread_gate_pct": spread_gate_pct,
            "execution_cost_model": "quote_native_no_mid_spread_cost_plus_ibkr_like_fees",
            "option_contract_multiplier": option_contract_multiplier,
            "default_round_trip_spread_cost_pct_of_risk": default_round_trip_spread_cost_pct_of_risk,
            "commission_per_contract": commission_per_contract,
            "regulatory_fee_per_contract": regulatory_fee_per_contract,
            "clearing_fee_per_contract": clearing_fee_per_contract,
            "activity_fee_per_contract": activity_fee_per_contract,
            "round_trip_sides": round_trip_sides,
            "contracts_per_trade_fallback": contracts_per_trade_fallback,
            "max_min_contract_risk_pct_of_equity": max_min_contract_risk_pct_of_equity,
            "min_trade_risk_dollars": min_trade_risk_dollars,
            "reselection_allowed": False,
            "expectancy_rebuild_allowed": False,
            "broker_fill_simulation_allowed": False,
            "minimum_contract_risk_model": "proxy_from_historical_position_risk_dollars_divided_by_contract_units",
        },
        "thresholds": thresholds,
        "explicit_exclusions": [
            "strategy_reselection",
            "expectancy_rebuild",
            "entry_rule_optimization",
            "exit_rule_optimization",
            "defensive_adjustment_simulation",
            "broker_order_routing",
            "full_margin_model",
            "portfolio_margin",
            "intraday_order_book_queue_modeling",
        ],
        "paths": {
            "summary_path": str(output_dir / "signalforge_portfolio_capital_sufficiency_summary.json"),
            "scenarios_path": str(output_dir / "signalforge_portfolio_capital_sufficiency_scenarios.jsonl"),
            "equity_curves_path": str(output_dir / "signalforge_portfolio_capital_sufficiency_equity_curves.jsonl"),
            "thresholds_path": str(output_dir / "signalforge_portfolio_capital_sufficiency_thresholds.json"),
        },
    }

    _write_json(output_dir / "signalforge_portfolio_capital_sufficiency_summary.json", summary)
    _write_jsonl(output_dir / "signalforge_portfolio_capital_sufficiency_scenarios.jsonl", scenario_rows)
    _write_jsonl(output_dir / "signalforge_portfolio_capital_sufficiency_equity_curves.jsonl", equity_curve_rows)
    _write_json(output_dir / "signalforge_portfolio_capital_sufficiency_thresholds.json", thresholds)
    return summary


def _parse_capitals(text: str) -> List[float]:
    if not text:
        return DEFAULT_CAPITALS
    values = []
    for part in text.split(","):
        part = part.strip().replace("$", "").replace("_", "")
        if not part:
            continue
        values.append(float(part))
    return values


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build SignalForge portfolio capital sufficiency scenarios.")
    parser.add_argument("--trade-ledger", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--starting-capitals", default=",".join(str(x) for x in DEFAULT_CAPITALS))
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--max-trade-risk-dollars", type=float, default=1000.0)
    parser.add_argument("--spread-gate-pct", type=float, default=0.10)
    parser.add_argument("--option-contract-multiplier", type=float, default=100.0)
    parser.add_argument("--default-round-trip-spread-cost-pct-of-risk", type=float, default=0.02)
    parser.add_argument("--commission-per-contract", type=float, default=0.65)
    parser.add_argument("--regulatory-fee-per-contract", type=float, default=0.02295)
    parser.add_argument("--clearing-fee-per-contract", type=float, default=0.025)
    parser.add_argument("--activity-fee-per-contract", type=float, default=0.00329)
    parser.add_argument("--round-trip-sides", type=float, default=2.0)
    parser.add_argument("--contracts-per-trade-fallback", type=float, default=1.0)
    parser.add_argument("--max-min-contract-risk-pct-of-equity", type=float, default=0.05)
    parser.add_argument("--min-trade-risk-dollars", type=float, default=1.0)
    args = parser.parse_args(argv)

    summary = build_capital_sufficiency(
        trade_ledger=args.trade_ledger,
        output_dir=args.output_dir,
        starting_capitals=_parse_capitals(args.starting_capitals),
        risk_per_trade_pct=args.risk_per_trade_pct,
        max_trade_risk_dollars=args.max_trade_risk_dollars,
        spread_gate_pct=args.spread_gate_pct,
        option_contract_multiplier=args.option_contract_multiplier,
        default_round_trip_spread_cost_pct_of_risk=args.default_round_trip_spread_cost_pct_of_risk,
        commission_per_contract=args.commission_per_contract,
        regulatory_fee_per_contract=args.regulatory_fee_per_contract,
        clearing_fee_per_contract=args.clearing_fee_per_contract,
        activity_fee_per_contract=args.activity_fee_per_contract,
        round_trip_sides=args.round_trip_sides,
        contracts_per_trade_fallback=args.contracts_per_trade_fallback,
        max_min_contract_risk_pct_of_equity=args.max_min_contract_risk_pct_of_equity,
        min_trade_risk_dollars=args.min_trade_risk_dollars,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
