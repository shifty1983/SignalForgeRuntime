"""Portfolio construction rule sensitivity replay.

This CLI is intentionally self-contained. It replays the enriched SignalForge portfolio
trade ledger across portfolio construction rule variants without rebuilding expectancy,
reselecting strategies, or changing entry/exit logic.

The replay is designed for Phase 8 rule refinement:
- vary starting capital
- vary risk-per-trade percentage
- vary max dollar risk cap
- preserve quote-native live-realism assumptions
- report pass/fail gates and ranking diagnostics
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ADAPTER_TYPE = "portfolio_construction_rule_sensitivity_builder"
ARTIFACT_TYPE = "signalforge_portfolio_construction_rule_sensitivity"
CONTRACT = "portfolio_construction_rule_sensitivity"


@dataclass(frozen=True)
class ReplayPolicy:
    spread_gate_pct: float
    default_round_trip_spread_cost_pct_of_risk: float
    commission_per_contract: float
    regulatory_fee_per_contract: float
    clearing_fee_per_contract: float
    activity_fee_per_contract: float
    contracts_per_trade_fallback: float
    round_trip_sides: float
    option_contract_multiplier: float
    max_min_contract_risk_pct_of_equity: float
    min_trade_risk_dollars: float

    @property
    def fee_per_contract_round_trip(self) -> float:
        return (
            self.commission_per_contract
            + self.regulatory_fee_per_contract
            + self.clearing_fee_per_contract
            + self.activity_fee_per_contract
        ) * self.round_trip_sides


@dataclass(frozen=True)
class Thresholds:
    minimum_trade_retention_rate: float
    minimum_profit_factor: float
    maximum_drawdown_pct_abs: float
    maximum_min_contract_oversize_rate: float
    maximum_effective_risk_per_trade_pct: float
    maximum_execution_cost_pct_of_gross_profit: float
    maximum_top_symbol_positive_contribution_pct: float
    maximum_top_strategy_positive_contribution_pct: float
    minimum_sized_trade_count: int


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _parse_float_list(value: str) -> list[float]:
    out: list[float] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    if not out:
        raise argparse.ArgumentTypeError("expected at least one numeric value")
    return out


def _maybe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _first_float(row: dict[str, Any], names: Iterable[str]) -> tuple[float | None, str | None]:
    for name in names:
        value = _maybe_float(row.get(name))
        if value is not None:
            return value, name
    return None, None


def _first_str(row: dict[str, Any], names: Iterable[str], default: str = "") -> tuple[str, str | None]:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text, name
    return default, None


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Preserve yyyy-mm-dd if already present. datetime.fromisoformat handles common variants.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        if len(text) >= 10:
            return text[:10]
    return None


def _normalize_trade_rows(raw_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract the minimum execution-aware trade fields needed for sensitivity replay."""
    rows: list[dict[str, Any]] = []
    skipped_non_sized_or_missing_required_fields = 0
    field_usage: Counter[str] = Counter()

    for idx, row in enumerate(raw_rows):
        pnl, pnl_field = _first_float(row, ["realized_pnl_dollars", "selected_realized_pnl_dollars", "pnl"])
        realized_return, return_field = _first_float(row, ["realized_return", "selected_realized_return", "strategy_adjusted_return"])
        historical_risk, risk_field = _first_float(row, ["position_risk_dollars", "selected_position_risk_dollars", "risk_amount"])
        if pnl is None or realized_return is None or historical_risk is None or historical_risk <= 0:
            skipped_non_sized_or_missing_required_fields += 1
            continue

        date, date_field = _first_str(
            row,
            ["portfolio_realization_date", "outcome_availability_date", "selected_outcome_availability_date", "decision_date"],
        )
        date = _parse_date(date)
        if not date:
            skipped_non_sized_or_missing_required_fields += 1
            continue

        symbol, symbol_field = _first_str(row, ["symbol", "underlying_symbol", "selected_symbol"], default="UNKNOWN")
        strategy, strategy_field = _first_str(row, ["selected_strategy", "strategy", "strategy_name"], default="UNKNOWN")

        spread_pct, spread_pct_field = _first_float(row, ["spread_pct", "bid_ask_spread_pct", "selected_spread_pct"])
        spread_dollars, spread_dollars_field = _first_float(
            row,
            [
                "bid_ask_spread_dollars",
                "spread_dollars",
                "spread_width_dollars",
                "entry_spread_dollars",
                "exit_spread_dollars",
                "option_spread_dollars",
                "quote_spread_dollars",
                "strategy_spread_dollars",
                "round_trip_spread_cost_dollars",
            ],
        )
        contract_count, contract_count_field = _first_float(
            row,
            ["contract_count", "contract_quantity", "fallback_contract_count", "selected_contract_count", "contracts"],
        )
        if contract_count is None or contract_count <= 0:
            contract_count = 1.0
            contract_count_field = "fallback_contract_count_default_1"

        # Historical risk per contract is a proxy for minimum 1-contract risk.
        unit_risk = historical_risk / max(contract_count, 1e-9)
        if unit_risk <= 0:
            skipped_non_sized_or_missing_required_fields += 1
            continue

        for field, label in [
            (pnl_field, "pnl"),
            (return_field, "return"),
            (risk_field, "risk_amount"),
            (date_field, "date"),
            (symbol_field, "symbol"),
            (strategy_field, "strategy"),
            (spread_pct_field, "spread_pct"),
            (spread_dollars_field, "spread_dollars"),
            (contract_count_field, "contract_count"),
        ]:
            if field:
                field_usage[f"{label}:{field}"] += 1

        rows.append(
            {
                "source_index": idx,
                "date": date,
                "year": date[:4],
                "symbol": symbol,
                "strategy": strategy,
                "historical_pnl": pnl,
                "realized_return": realized_return,
                "historical_risk_dollars": historical_risk,
                "historical_contract_count": contract_count,
                "unit_risk_dollars": unit_risk,
                "spread_pct": spread_pct,
                "spread_pct_source": spread_pct_field,
                "spread_dollars": spread_dollars,
                "spread_dollars_source": spread_dollars_field,
                "contract_count_source": contract_count_field,
            }
        )

    rows.sort(key=lambda item: (item["date"], item["source_index"]))
    diagnostics = {
        "raw_row_count": len(raw_rows),
        "normalized_trade_count": len(rows),
        "skipped_non_sized_or_missing_required_fields_count": skipped_non_sized_or_missing_required_fields,
        "field_usage": dict(sorted(field_usage.items())),
    }
    return rows, diagnostics


def _max_drawdown(equity_points: list[tuple[str, float]]) -> tuple[float, float, str | None, float]:
    if not equity_points:
        return 0.0, 0.0, None, 0.0
    peak = equity_points[0][1]
    max_dd_dollars = 0.0
    max_dd_pct = 0.0
    max_dd_date: str | None = equity_points[0][0]
    peak_equity = peak
    for date, equity in equity_points:
        if equity > peak:
            peak = equity
            peak_equity = equity
        dd_dollars = equity - peak
        dd_pct = dd_dollars / peak if peak else 0.0
        if dd_pct < max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_dollars = dd_dollars
            max_dd_date = date
    return max_dd_pct, max_dd_dollars, max_dd_date, peak_equity


def _positive_contribution(items: dict[str, float]) -> tuple[dict[str, Any] | None, float]:
    total_positive = sum(value for value in items.values() if value > 0)
    if not items:
        return None, total_positive
    key, pnl = max(items.items(), key=lambda kv: kv[1])
    return {
        "name": key,
        "pnl": pnl,
        "positive_contribution_pct": (pnl / total_positive) if total_positive > 0 and pnl > 0 else 0.0,
    }, total_positive


def _scenario_gate_results(
    *,
    total_return: float,
    max_drawdown_pct: float,
    profit_factor: float | None,
    trade_retention_rate: float,
    minimum_contract_oversize_accepted_rate: float,
    max_effective_risk_per_trade_pct: float,
    execution_cost_pct_of_gross_profit: float,
    top_symbol_positive_contribution_pct: float | None,
    top_strategy_positive_contribution_pct: float | None,
    sized_trade_count: int,
    thresholds: Thresholds,
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []

    def fail(code: str, actual: Any, threshold: Any, direction: str) -> None:
        failures.append({"code": code, "actual": actual, "threshold": threshold, "direction": direction})

    if total_return <= 0:
        fail("total_return_not_positive", total_return, 0.0, "greater_than")
    if sized_trade_count < thresholds.minimum_sized_trade_count:
        fail("sized_trade_count_below_minimum", sized_trade_count, thresholds.minimum_sized_trade_count, "greater_than_or_equal")
    if trade_retention_rate < thresholds.minimum_trade_retention_rate:
        fail("trade_retention_rate_below_minimum", trade_retention_rate, thresholds.minimum_trade_retention_rate, "greater_than_or_equal")
    if profit_factor is None or profit_factor < thresholds.minimum_profit_factor:
        fail("profit_factor_below_minimum", profit_factor, thresholds.minimum_profit_factor, "greater_than_or_equal")
    if abs(max_drawdown_pct) > thresholds.maximum_drawdown_pct_abs:
        fail("max_drawdown_pct_above_limit", max_drawdown_pct, -thresholds.maximum_drawdown_pct_abs, "abs_less_than_or_equal")
    if minimum_contract_oversize_accepted_rate > thresholds.maximum_min_contract_oversize_rate:
        fail(
            "minimum_contract_oversize_rate_above_limit",
            minimum_contract_oversize_accepted_rate,
            thresholds.maximum_min_contract_oversize_rate,
            "less_than_or_equal",
        )
    if max_effective_risk_per_trade_pct > thresholds.maximum_effective_risk_per_trade_pct:
        fail(
            "max_effective_risk_per_trade_pct_above_limit",
            max_effective_risk_per_trade_pct,
            thresholds.maximum_effective_risk_per_trade_pct,
            "less_than_or_equal",
        )
    if execution_cost_pct_of_gross_profit > thresholds.maximum_execution_cost_pct_of_gross_profit:
        fail(
            "execution_cost_pct_of_gross_profit_above_limit",
            execution_cost_pct_of_gross_profit,
            thresholds.maximum_execution_cost_pct_of_gross_profit,
            "less_than_or_equal",
        )
    if (
        top_symbol_positive_contribution_pct is not None
        and top_symbol_positive_contribution_pct > thresholds.maximum_top_symbol_positive_contribution_pct
    ):
        fail(
            "top_symbol_positive_contribution_pct_above_limit",
            top_symbol_positive_contribution_pct,
            thresholds.maximum_top_symbol_positive_contribution_pct,
            "less_than_or_equal",
        )
    if (
        top_strategy_positive_contribution_pct is not None
        and top_strategy_positive_contribution_pct > thresholds.maximum_top_strategy_positive_contribution_pct
    ):
        fail(
            "top_strategy_positive_contribution_pct_above_limit",
            top_strategy_positive_contribution_pct,
            thresholds.maximum_top_strategy_positive_contribution_pct,
            "less_than_or_equal",
        )

    return not failures, [failure["code"] for failure in failures], failures


def _calculate_score(row: dict[str, Any]) -> float:
    if not row.get("passes_portfolio_construction_gate"):
        return -1.0
    total_return = max(float(row.get("total_return") or 0.0), 0.0)
    profit_factor = float(row.get("profit_factor") or 0.0)
    retention = float(row.get("trade_retention_rate") or 0.0)
    max_dd = abs(float(row.get("max_drawdown_pct") or 0.0))
    exec_drag = float(row.get("execution_cost_pct_of_gross_profit") or 0.0)
    min_oversize = float(row.get("minimum_contract_oversize_accepted_rate") or 0.0)
    top_strategy = float(row.get("top_strategy_positive_contribution_pct") or 0.0)
    top_symbol = float(row.get("top_symbol_positive_contribution_pct") or 0.0)

    return (
        math.log1p(total_return)
        * max(profit_factor, 0.0)
        * max(retention, 0.0)
        / (1.0 + max_dd * 5.0)
        / (1.0 + exec_drag)
        / (1.0 + min_oversize)
        / (1.0 + top_strategy + top_symbol)
    )


def _replay_scenario(
    *,
    trades: list[dict[str, Any]],
    starting_capital: float,
    risk_per_trade_pct: float,
    max_trade_risk_dollars: float,
    policy: ReplayPolicy,
    thresholds: Thresholds,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    equity = starting_capital
    equity_points: list[tuple[str, float]] = [("START", starting_capital)]
    equity_rows: list[dict[str, Any]] = []

    attempted_trade_count = len(trades)
    sized_trade_count = 0
    skipped_spread_count = 0
    skipped_min_contract_oversize_count = 0
    skipped_budget_below_minimum_count = 0
    skipped_non_positive_equity_count = 0
    minimum_contract_oversize_accepted_count = 0

    total_execution_cost = 0.0
    total_fee_cost = 0.0
    total_contract_units = 0.0
    max_effective_risk_per_trade_pct = 0.0
    risk_amounts: list[float] = []
    pnl_values: list[float] = []

    by_symbol: defaultdict[str, float] = defaultdict(float)
    by_strategy: defaultdict[str, float] = defaultdict(float)
    by_year: defaultdict[str, float] = defaultdict(float)

    for trade in trades:
        if equity <= 0:
            skipped_non_positive_equity_count += 1
            continue

        spread_pct = trade.get("spread_pct")
        if spread_pct is not None and spread_pct > policy.spread_gate_pct:
            skipped_spread_count += 1
            continue

        budget = min(equity * risk_per_trade_pct, max_trade_risk_dollars)
        if budget < policy.min_trade_risk_dollars:
            skipped_budget_below_minimum_count += 1
            continue

        unit_risk = float(trade["unit_risk_dollars"])
        if budget < unit_risk:
            min_contract_risk_pct = unit_risk / equity if equity > 0 else math.inf
            if min_contract_risk_pct > policy.max_min_contract_risk_pct_of_equity:
                skipped_min_contract_oversize_count += 1
                continue
            contract_units = 1.0
            risk_dollars = unit_risk
            minimum_contract_oversize_accepted_count += 1
        else:
            # Sensitivity replay sizes continuously by risk budget while preserving a
            # contract-unit estimate for fee/spread cost. This avoids introducing a
            # fake broker order lot model before the margin/buying-power phase.
            risk_dollars = budget
            contract_units = max(policy.contracts_per_trade_fallback, risk_dollars / unit_risk)

        spread_dollars = trade.get("spread_dollars")
        if spread_dollars is None:
            execution_cost = risk_dollars * policy.default_round_trip_spread_cost_pct_of_risk
            execution_cost_source = "fallback_pct_of_risk"
        else:
            execution_cost = abs(float(spread_dollars)) * contract_units * policy.option_contract_multiplier
            execution_cost_source = "quote_native_spread_dollars_times_contracts_times_multiplier"

        fee_cost = contract_units * policy.fee_per_contract_round_trip
        gross_pnl = risk_dollars * float(trade["realized_return"])
        net_pnl = gross_pnl - execution_cost - fee_cost

        equity_before = equity
        equity += net_pnl
        sized_trade_count += 1
        total_execution_cost += execution_cost
        total_fee_cost += fee_cost
        total_contract_units += contract_units
        risk_amounts.append(risk_dollars)
        pnl_values.append(net_pnl)
        max_effective_risk_per_trade_pct = max(max_effective_risk_per_trade_pct, risk_dollars / equity_before if equity_before > 0 else 0.0)

        by_symbol[str(trade["symbol"])] += net_pnl
        by_strategy[str(trade["strategy"])] += net_pnl
        by_year[str(trade["year"])] += net_pnl

        equity_points.append((str(trade["date"]), equity))
        equity_rows.append(
            {
                "capital_scenario": starting_capital,
                "risk_per_trade_pct": risk_per_trade_pct,
                "max_trade_risk_dollars": max_trade_risk_dollars,
                "date": trade["date"],
                "symbol": trade["symbol"],
                "strategy": trade["strategy"],
                "equity_before_trade": equity_before,
                "equity_after_trade": equity,
                "risk_dollars": risk_dollars,
                "contract_units": contract_units,
                "execution_cost_dollars": execution_cost,
                "execution_cost_source": execution_cost_source,
                "fee_cost_dollars": fee_cost,
                "net_pnl_dollars": net_pnl,
                "realized_return": trade["realized_return"],
                "spread_pct": spread_pct,
                "spread_dollars": spread_dollars,
                "minimum_contract_oversize_accepted": budget < unit_risk,
            }
        )

    total_pnl = equity - starting_capital
    total_return = total_pnl / starting_capital if starting_capital else 0.0
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (None if gross_profit <= 0 else math.inf)
    winning_trade_count = sum(1 for value in pnl_values if value > 0)
    losing_trade_count = sum(1 for value in pnl_values if value < 0)
    win_rate = winning_trade_count / sized_trade_count if sized_trade_count else 0.0
    max_dd_pct, max_dd_dollars, max_dd_date, peak_equity = _max_drawdown(equity_points)
    trade_retention_rate = sized_trade_count / attempted_trade_count if attempted_trade_count else 0.0
    min_contract_oversize_rate = minimum_contract_oversize_accepted_count / sized_trade_count if sized_trade_count else 0.0
    execution_cost_pct_of_gross_profit = (total_execution_cost + total_fee_cost) / gross_profit if gross_profit > 0 else 0.0

    top_symbol, total_positive_symbol_pnl = _positive_contribution(by_symbol)
    top_strategy, total_positive_strategy_pnl = _positive_contribution(by_strategy)
    top_year, total_positive_year_pnl = _positive_contribution(by_year)

    top_symbol_pct = top_symbol["positive_contribution_pct"] if top_symbol else None
    top_strategy_pct = top_strategy["positive_contribution_pct"] if top_strategy else None
    top_year_pct = top_year["positive_contribution_pct"] if top_year else None

    passes, failure_reasons, gate_failures = _scenario_gate_results(
        total_return=total_return,
        max_drawdown_pct=max_dd_pct,
        profit_factor=profit_factor,
        trade_retention_rate=trade_retention_rate,
        minimum_contract_oversize_accepted_rate=min_contract_oversize_rate,
        max_effective_risk_per_trade_pct=max_effective_risk_per_trade_pct,
        execution_cost_pct_of_gross_profit=execution_cost_pct_of_gross_profit,
        top_symbol_positive_contribution_pct=top_symbol_pct,
        top_strategy_positive_contribution_pct=top_strategy_pct,
        sized_trade_count=sized_trade_count,
        thresholds=thresholds,
    )

    row: dict[str, Any] = {
        "scenario_name": f"capital_{starting_capital:g}_risk_{risk_per_trade_pct:g}_cap_{max_trade_risk_dollars:g}",
        "capital_scenario": starting_capital,
        "starting_capital": starting_capital,
        "risk_per_trade_pct": risk_per_trade_pct,
        "max_trade_risk_dollars": max_trade_risk_dollars,
        "ending_capital": equity,
        "total_pnl": total_pnl,
        "total_return": total_return,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_dollars": max_dd_dollars,
        "max_drawdown_date": max_dd_date,
        "peak_equity": peak_equity,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "winning_trade_count": winning_trade_count,
        "losing_trade_count": losing_trade_count,
        "attempted_trade_count": attempted_trade_count,
        "sized_trade_count": sized_trade_count,
        "trade_retention_rate": trade_retention_rate,
        "skipped_trade_count": attempted_trade_count - sized_trade_count,
        "skipped_spread_count": skipped_spread_count,
        "skipped_min_contract_oversize_count": skipped_min_contract_oversize_count,
        "skipped_budget_below_minimum_count": skipped_budget_below_minimum_count,
        "skipped_non_positive_equity_count": skipped_non_positive_equity_count,
        "minimum_contract_oversize_accepted_count": minimum_contract_oversize_accepted_count,
        "minimum_contract_oversize_accepted_rate": min_contract_oversize_rate,
        "max_effective_risk_per_trade_pct": max_effective_risk_per_trade_pct,
        "average_risk_dollars": statistics.fmean(risk_amounts) if risk_amounts else 0.0,
        "median_risk_dollars": statistics.median(risk_amounts) if risk_amounts else 0.0,
        "total_contract_units": total_contract_units,
        "total_execution_cost_dollars": total_execution_cost,
        "total_fee_cost_dollars": total_fee_cost,
        "total_combined_execution_and_fee_cost_dollars": total_execution_cost + total_fee_cost,
        "execution_cost_pct_of_gross_profit": execution_cost_pct_of_gross_profit,
        "top_symbol": top_symbol,
        "top_symbol_positive_contribution_pct": top_symbol_pct,
        "top_strategy": top_strategy,
        "top_strategy_positive_contribution_pct": top_strategy_pct,
        "top_year": top_year,
        "top_year_positive_contribution_pct": top_year_pct,
        "total_positive_symbol_pnl": total_positive_symbol_pnl,
        "total_positive_strategy_pnl": total_positive_strategy_pnl,
        "total_positive_year_pnl": total_positive_year_pnl,
        "passes_portfolio_construction_gate": passes,
        "portfolio_construction_gate_status": "pass" if passes else "fail",
        "failure_reasons": failure_reasons,
        "gate_failures": gate_failures,
    }
    row["robustness_score"] = _calculate_score(row)
    return row, equity_rows


def _best_by_capital(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scenarios:
        grouped[str(row["starting_capital"])].append(row)
    for capital, rows in grouped.items():
        passing = [row for row in rows if row.get("passes_portfolio_construction_gate")]
        candidates = passing or rows
        best = max(candidates, key=lambda item: item.get("robustness_score", -1.0))
        output[capital] = {
            "scenario_name": best["scenario_name"],
            "starting_capital": best["starting_capital"],
            "risk_per_trade_pct": best["risk_per_trade_pct"],
            "max_trade_risk_dollars": best["max_trade_risk_dollars"],
            "passes_portfolio_construction_gate": best["passes_portfolio_construction_gate"],
            "robustness_score": best["robustness_score"],
            "total_return": best["total_return"],
            "max_drawdown_pct": best["max_drawdown_pct"],
            "profit_factor": best["profit_factor"],
            "trade_retention_rate": best["trade_retention_rate"],
            "minimum_contract_oversize_accepted_rate": best["minimum_contract_oversize_accepted_rate"],
            "max_effective_risk_per_trade_pct": best["max_effective_risk_per_trade_pct"],
        }
    return output


def build(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_rows = _read_jsonl(Path(args.trade_ledger))
    trades, input_diagnostics = _normalize_trade_rows(raw_rows)

    policy = ReplayPolicy(
        spread_gate_pct=args.spread_gate_pct,
        default_round_trip_spread_cost_pct_of_risk=args.default_round_trip_spread_cost_pct_of_risk,
        commission_per_contract=args.commission_per_contract,
        regulatory_fee_per_contract=args.regulatory_fee_per_contract,
        clearing_fee_per_contract=args.clearing_fee_per_contract,
        activity_fee_per_contract=args.activity_fee_per_contract,
        contracts_per_trade_fallback=args.contracts_per_trade_fallback,
        round_trip_sides=args.round_trip_sides,
        option_contract_multiplier=args.option_contract_multiplier,
        max_min_contract_risk_pct_of_equity=args.max_min_contract_risk_pct_of_equity,
        min_trade_risk_dollars=args.min_trade_risk_dollars,
    )
    thresholds = Thresholds(
        minimum_trade_retention_rate=args.minimum_trade_retention_rate,
        minimum_profit_factor=args.minimum_profit_factor,
        maximum_drawdown_pct_abs=args.maximum_drawdown_pct_abs,
        maximum_min_contract_oversize_rate=args.maximum_min_contract_oversize_rate,
        maximum_effective_risk_per_trade_pct=args.maximum_effective_risk_per_trade_pct,
        maximum_execution_cost_pct_of_gross_profit=args.maximum_execution_cost_pct_of_gross_profit,
        maximum_top_symbol_positive_contribution_pct=args.maximum_top_symbol_positive_contribution_pct,
        maximum_top_strategy_positive_contribution_pct=args.maximum_top_strategy_positive_contribution_pct,
        minimum_sized_trade_count=args.minimum_sized_trade_count,
    )

    scenarios: list[dict[str, Any]] = []
    equity_curve_rows: list[dict[str, Any]] = []
    for starting_capital in args.starting_capitals:
        for risk_pct in args.risk_per_trade_pcts:
            for max_risk in args.max_trade_risk_dollars:
                scenario, equity_rows = _replay_scenario(
                    trades=trades,
                    starting_capital=starting_capital,
                    risk_per_trade_pct=risk_pct,
                    max_trade_risk_dollars=max_risk,
                    policy=policy,
                    thresholds=thresholds,
                )
                scenarios.append(scenario)
                equity_curve_rows.extend(equity_rows)

    scenario_count = len(scenarios)
    passing = [row for row in scenarios if row.get("passes_portfolio_construction_gate")]
    gate_failure_counts = Counter(reason for row in scenarios for reason in row.get("failure_reasons", []))

    best_overall = max(passing or scenarios, key=lambda item: item.get("robustness_score", -1.0)) if scenarios else None
    best_by_capital = _best_by_capital(scenarios)

    blockers: list[str] = []
    warnings: list[str] = []
    if not trades:
        blockers.append("no_normalized_trades_available")
    if scenario_count == 0:
        blockers.append("no_scenarios_generated")
    if not passing:
        warnings.append("no_portfolio_construction_scenarios_passed_quality_gate")

    scenarios_path = output_dir / "signalforge_portfolio_construction_rule_sensitivity_scenarios.jsonl"
    equity_curves_path = output_dir / "signalforge_portfolio_construction_rule_sensitivity_equity_curves.jsonl"
    summary_path = output_dir / "signalforge_portfolio_construction_rule_sensitivity_summary.json"
    thresholds_path = output_dir / "signalforge_portfolio_construction_rule_sensitivity_thresholds.json"

    threshold_payload = {
        "minimum_trade_retention_rate": thresholds.minimum_trade_retention_rate,
        "minimum_profit_factor": thresholds.minimum_profit_factor,
        "maximum_drawdown_pct_abs": thresholds.maximum_drawdown_pct_abs,
        "maximum_min_contract_oversize_rate": thresholds.maximum_min_contract_oversize_rate,
        "maximum_effective_risk_per_trade_pct": thresholds.maximum_effective_risk_per_trade_pct,
        "maximum_execution_cost_pct_of_gross_profit": thresholds.maximum_execution_cost_pct_of_gross_profit,
        "maximum_top_symbol_positive_contribution_pct": thresholds.maximum_top_symbol_positive_contribution_pct,
        "maximum_top_strategy_positive_contribution_pct": thresholds.maximum_top_strategy_positive_contribution_pct,
        "minimum_sized_trade_count": thresholds.minimum_sized_trade_count,
    }

    summary: dict[str, Any] = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": not blockers,
        "readiness_state": "pass" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "scenario_count": scenario_count,
        "passing_scenario_count": len(passing),
        "starting_capitals": args.starting_capitals,
        "risk_per_trade_pcts": args.risk_per_trade_pcts,
        "max_trade_risk_dollars": args.max_trade_risk_dollars,
        "input_diagnostics": input_diagnostics,
        "replay_policy": {
            "execution_cost_model": "spread_gate_plus_quote_native_no_mid_spread_cost_plus_ibkr_like_fees",
            "spread_gate_pct": policy.spread_gate_pct,
            "risk_budget_rule": "min(current_equity * risk_per_trade_pct, max_trade_risk_dollars)",
            "minimum_contract_risk_model": "historical_position_risk_dollars_divided_by_contract_units_proxy",
            "default_round_trip_spread_cost_pct_of_risk": policy.default_round_trip_spread_cost_pct_of_risk,
            "commission_per_contract": policy.commission_per_contract,
            "regulatory_fee_per_contract": policy.regulatory_fee_per_contract,
            "clearing_fee_per_contract": policy.clearing_fee_per_contract,
            "activity_fee_per_contract": policy.activity_fee_per_contract,
            "contracts_per_trade_fallback": policy.contracts_per_trade_fallback,
            "round_trip_sides": policy.round_trip_sides,
            "option_contract_multiplier": policy.option_contract_multiplier,
            "max_min_contract_risk_pct_of_equity": policy.max_min_contract_risk_pct_of_equity,
            "min_trade_risk_dollars": policy.min_trade_risk_dollars,
            "reselection_allowed": False,
            "expectancy_rebuild_allowed": False,
            "entry_exit_rule_changes_allowed": False,
            "broker_fill_simulation_allowed": False,
        },
        "thresholds": threshold_payload,
        "gate_failure_counts": dict(sorted(gate_failure_counts.items())),
        "best_overall_scenario": best_overall,
        "best_by_capital": best_by_capital,
        "paths": {
            "summary_path": str(summary_path),
            "scenarios_path": str(scenarios_path),
            "equity_curves_path": str(equity_curves_path),
            "thresholds_path": str(thresholds_path),
        },
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
    }

    _write_jsonl(scenarios_path, scenarios)
    _write_jsonl(equity_curves_path, equity_curve_rows)
    _write_json(thresholds_path, threshold_payload)
    _write_json(summary_path, summary)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay portfolio construction rule sensitivity variants.")
    parser.add_argument("--trade-ledger", required=True)
    parser.add_argument("--starting-capitals", type=_parse_float_list, default=[31000.0, 40000.0, 100000.0])
    parser.add_argument("--risk-per-trade-pcts", type=_parse_float_list, default=[0.0025, 0.005, 0.0075, 0.01, 0.0125])
    parser.add_argument("--max-trade-risk-dollars", type=_parse_float_list, default=[250.0, 500.0, 750.0, 1000.0])
    parser.add_argument("--spread-gate-pct", type=float, default=0.10)
    parser.add_argument("--default-round-trip-spread-cost-pct-of-risk", type=float, default=0.02)
    parser.add_argument("--commission-per-contract", type=float, default=0.65)
    parser.add_argument("--regulatory-fee-per-contract", type=float, default=0.02295)
    parser.add_argument("--clearing-fee-per-contract", type=float, default=0.025)
    parser.add_argument("--activity-fee-per-contract", type=float, default=0.00329)
    parser.add_argument("--contracts-per-trade-fallback", type=float, default=1.0)
    parser.add_argument("--round-trip-sides", type=float, default=2.0)
    parser.add_argument("--option-contract-multiplier", type=float, default=100.0)
    parser.add_argument("--max-min-contract-risk-pct-of-equity", type=float, default=0.05)
    parser.add_argument("--min-trade-risk-dollars", type=float, default=1.0)
    parser.add_argument("--minimum-trade-retention-rate", type=float, default=0.50)
    parser.add_argument("--minimum-profit-factor", type=float, default=1.40)
    parser.add_argument("--maximum-drawdown-pct-abs", type=float, default=0.25)
    parser.add_argument("--maximum-min-contract-oversize-rate", type=float, default=0.10)
    parser.add_argument("--maximum-effective-risk-per-trade-pct", type=float, default=0.05)
    parser.add_argument("--maximum-execution-cost-pct-of-gross-profit", type=float, default=0.25)
    parser.add_argument("--maximum-top-symbol-positive-contribution-pct", type=float, default=0.15)
    parser.add_argument("--maximum-top-strategy-positive-contribution-pct", type=float, default=0.50)
    parser.add_argument("--minimum-sized-trade-count", type=int, default=100)
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    summary = build(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
