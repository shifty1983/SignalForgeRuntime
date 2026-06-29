"""Portfolio entry-filter sensitivity replay.

This CLI is intentionally self-contained. It replays the enriched SignalForge
portfolio trade ledger across decision-time entry filter variants without
rebuilding expectancy, reselecting strategies, changing exits, or using realized
outcomes to choose filters.

Phase 8 scope:
- filter already-selected trades by decision-time fields such as expectancy score,
  expectancy sample count, construction quality, and observed spread percentage
- preserve quote-native live-realism costs and IBKR-like fees
- report quality gates and ranking diagnostics
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ADAPTER_TYPE = "portfolio_entry_filter_sensitivity_builder"
ARTIFACT_TYPE = "signalforge_portfolio_entry_filter_sensitivity"
CONTRACT = "portfolio_entry_filter_sensitivity"


@dataclass(frozen=True)
class ReplayPolicy:
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


@dataclass(frozen=True)
class EntryFilterVariant:
    starting_capital: float
    minimum_expectancy_score: float | None
    minimum_expectancy_sample_count: int | None
    max_spread_pct: float | None
    construction_quality_mode: str

    @property
    def name(self) -> str:
        score = "none" if self.minimum_expectancy_score is None else _fmt_num(self.minimum_expectancy_score)
        sample = "none" if self.minimum_expectancy_sample_count is None else str(self.minimum_expectancy_sample_count)
        spread = "none" if self.max_spread_pct is None else _fmt_num(self.max_spread_pct)
        return (
            f"capital_{_fmt_num(self.starting_capital)}"
            f"_score_{score}"
            f"_sample_{sample}"
            f"_spread_{spread}"
            f"_quality_{self.construction_quality_mode}"
        )


def _fmt_num(value: float) -> str:
    text = ("%0.8f" % value).rstrip("0").rstrip(".")
    return text.replace(".", "p")


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


def _parse_optional_float_list(value: str) -> list[float | None]:
    out: list[float | None] = []
    for part in value.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part in {"none", "null", "unlimited", "all"}:
            out.append(None)
        else:
            out.append(float(part))
    if not out:
        raise argparse.ArgumentTypeError("expected at least one value")
    return out


def _parse_optional_int_list(value: str) -> list[int | None]:
    out: list[int | None] = []
    for part in value.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part in {"none", "null", "unlimited", "all"}:
            out.append(None)
        else:
            out.append(int(part))
    if not out:
        raise argparse.ArgumentTypeError("expected at least one value")
    return out


def _parse_str_list(value: str) -> list[str]:
    out = [part.strip() for part in value.split(",") if part.strip()]
    if not out:
        raise argparse.ArgumentTypeError("expected at least one value")
    allowed = {"all", "primary_only", "primary_secondary"}
    bad = [item for item in out if item not in allowed]
    if bad:
        raise argparse.ArgumentTypeError(f"unsupported construction quality modes: {bad}; allowed={sorted(allowed)}")
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


def _maybe_int(value: Any) -> int | None:
    number = _maybe_float(value)
    if number is None:
        return None
    return int(number)


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        if len(text) >= 10:
            return text[:10]
    return None


def _iter_nested_values(obj: Any, *, depth: int = 0, max_depth: int = 5) -> Iterable[dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_nested_values(value, depth=depth + 1, max_depth=max_depth)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_nested_values(value, depth=depth + 1, max_depth=max_depth)


def _deep_first(row: dict[str, Any], names: Iterable[str]) -> tuple[Any, str | None]:
    name_list = list(names)
    for name in name_list:
        if name in row and row.get(name) not in (None, ""):
            return row.get(name), name
    for mapping in _iter_nested_values(row):
        if mapping is row:
            continue
        for name in name_list:
            if name in mapping and mapping.get(name) not in (None, ""):
                return mapping.get(name), name
    return None, None


def _deep_float(row: dict[str, Any], names: Iterable[str]) -> tuple[float | None, str | None]:
    value, field = _deep_first(row, names)
    return _maybe_float(value), field


def _deep_int(row: dict[str, Any], names: Iterable[str]) -> tuple[int | None, str | None]:
    value, field = _deep_first(row, names)
    return _maybe_int(value), field


def _deep_str(row: dict[str, Any], names: Iterable[str], default: str = "") -> tuple[str, str | None]:
    value, field = _deep_first(row, names)
    if value is None:
        return default, None
    text = str(value).strip()
    return (text if text else default), field


def _normalize_quality(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "primary": "primary",
        "primary_quality": "primary",
        "secondary": "secondary",
        "secondary_quality": "secondary",
        "fallback": "fallback_review",
        "fallback_review": "fallback_review",
        "review": "fallback_review",
    }
    return aliases.get(text, text)


def _quality_allowed(quality: str | None, mode: str) -> bool:
    if mode == "all":
        return True
    if mode == "primary_only":
        return quality == "primary"
    if mode == "primary_secondary":
        return quality in {"primary", "secondary"}
    raise ValueError(f"unsupported construction quality mode: {mode}")


def _normalize_trade_rows(raw_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped_non_sized_or_missing_required_fields = 0
    field_usage: Counter[str] = Counter()
    missing_entry_field_counts: Counter[str] = Counter()

    for idx, row in enumerate(raw_rows):
        sizing_state, _ = _deep_str(row, ["sizing_state"], default="")
        if sizing_state and sizing_state != "sized":
            skipped_non_sized_or_missing_required_fields += 1
            continue

        pnl, pnl_field = _deep_float(row, ["realized_pnl_dollars", "selected_realized_pnl_dollars", "pnl"])
        realized_return, return_field = _deep_float(row, ["realized_return", "selected_realized_return", "strategy_adjusted_return"])
        historical_risk, risk_field = _deep_float(row, ["position_risk_dollars", "selected_position_risk_dollars", "risk_amount"])
        if pnl is None or realized_return is None or historical_risk is None or historical_risk <= 0:
            skipped_non_sized_or_missing_required_fields += 1
            continue

        date_text, date_field = _deep_str(
            row,
            ["portfolio_realization_date", "outcome_availability_date", "selected_outcome_availability_date", "decision_date"],
        )
        date = _parse_date(date_text)
        if not date:
            skipped_non_sized_or_missing_required_fields += 1
            continue

        symbol, symbol_field = _deep_str(row, ["symbol", "underlying_symbol", "selected_symbol"], default="UNKNOWN")
        strategy, strategy_field = _deep_str(row, ["selected_strategy", "strategy", "strategy_name"], default="UNKNOWN")

        spread_pct, spread_pct_field = _deep_float(row, ["spread_pct", "bid_ask_spread_pct", "selected_spread_pct"])
        spread_dollars, spread_dollars_field = _deep_float(
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
        contract_count, contract_count_field = _deep_float(
            row,
            ["contract_count", "contract_quantity", "fallback_contract_count", "selected_contract_count", "contracts"],
        )
        if contract_count is None or contract_count <= 0:
            contract_count = 1.0
            contract_count_field = "fallback_contract_count_default_1"

        expectancy_score, expectancy_score_field = _deep_float(
            row,
            [
                "selected_confidence_adjusted_expectancy_score",
                "selected_expectancy_score",
                "expectancy_score",
                "confidence_adjusted_expectancy_score",
            ],
        )
        expectancy_sample_count, expectancy_sample_count_field = _deep_int(
            row,
            ["selected_expectancy_sample_count", "expectancy_sample_count", "sample_count"],
        )
        expectancy_scope, expectancy_scope_field = _deep_str(
            row,
            ["selected_expectancy_scope", "expectancy_scope"],
            default="UNKNOWN",
        )
        expectancy_state, expectancy_state_field = _deep_str(
            row,
            ["selected_expectancy_state", "expectancy_state"],
            default="UNKNOWN",
        )
        construction_quality_text, construction_quality_field = _deep_str(
            row,
            ["selected_construction_quality", "construction_quality", "leg_construction_quality"],
            default="",
        )
        construction_quality = _normalize_quality(construction_quality_text)

        unit_risk = historical_risk / max(contract_count, 1e-9)
        if unit_risk <= 0:
            skipped_non_sized_or_missing_required_fields += 1
            continue

        for name, value in [
            ("expectancy_score", expectancy_score),
            ("expectancy_sample_count", expectancy_sample_count),
            ("construction_quality", construction_quality),
            ("spread_pct", spread_pct),
        ]:
            if value is None:
                missing_entry_field_counts[name] += 1

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
            (expectancy_score_field, "expectancy_score"),
            (expectancy_sample_count_field, "expectancy_sample_count"),
            (expectancy_scope_field, "expectancy_scope"),
            (expectancy_state_field, "expectancy_state"),
            (construction_quality_field, "construction_quality"),
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
                "expectancy_score": expectancy_score,
                "expectancy_score_source": expectancy_score_field,
                "expectancy_sample_count": expectancy_sample_count,
                "expectancy_sample_count_source": expectancy_sample_count_field,
                "expectancy_scope": expectancy_scope,
                "expectancy_scope_source": expectancy_scope_field,
                "expectancy_state": expectancy_state,
                "expectancy_state_source": expectancy_state_field,
                "construction_quality": construction_quality,
                "construction_quality_source": construction_quality_field,
            }
        )

    rows.sort(key=lambda item: (item["date"], item["source_index"]))
    diagnostics = {
        "raw_row_count": len(raw_rows),
        "normalized_trade_count": len(rows),
        "skipped_non_sized_or_missing_required_fields_count": skipped_non_sized_or_missing_required_fields,
        "field_usage": dict(sorted(field_usage.items())),
        "missing_entry_field_counts": dict(sorted(missing_entry_field_counts.items())),
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
        fail("minimum_contract_oversize_rate_above_limit", minimum_contract_oversize_accepted_rate, thresholds.maximum_min_contract_oversize_rate, "less_than_or_equal")
    if max_effective_risk_per_trade_pct > thresholds.maximum_effective_risk_per_trade_pct:
        fail("max_effective_risk_per_trade_pct_above_limit", max_effective_risk_per_trade_pct, thresholds.maximum_effective_risk_per_trade_pct, "less_than_or_equal")
    if execution_cost_pct_of_gross_profit > thresholds.maximum_execution_cost_pct_of_gross_profit:
        fail("execution_cost_pct_of_gross_profit_above_limit", execution_cost_pct_of_gross_profit, thresholds.maximum_execution_cost_pct_of_gross_profit, "less_than_or_equal")
    if top_symbol_positive_contribution_pct is not None and top_symbol_positive_contribution_pct > thresholds.maximum_top_symbol_positive_contribution_pct:
        fail("top_symbol_positive_contribution_pct_above_limit", top_symbol_positive_contribution_pct, thresholds.maximum_top_symbol_positive_contribution_pct, "less_than_or_equal")
    if top_strategy_positive_contribution_pct is not None and top_strategy_positive_contribution_pct > thresholds.maximum_top_strategy_positive_contribution_pct:
        fail("top_strategy_positive_contribution_pct_above_limit", top_strategy_positive_contribution_pct, thresholds.maximum_top_strategy_positive_contribution_pct, "less_than_or_equal")

    return not failures, [failure["code"] for failure in failures], failures


def _calculate_score(row: dict[str, Any]) -> float:
    if not row.get("passes_entry_filter_gate"):
        return -1.0
    total_return = max(float(row.get("total_return") or 0.0), 0.0)
    profit_factor = float(row.get("profit_factor") or 0.0)
    retention = float(row.get("trade_retention_rate") or 0.0)
    max_dd = abs(float(row.get("max_drawdown_pct") or 0.0))
    exec_drag = float(row.get("execution_cost_pct_of_gross_profit") or 0.0)
    filter_skip = float(row.get("entry_filter_skip_rate") or 0.0)
    min_oversize = float(row.get("minimum_contract_oversize_accepted_rate") or 0.0)
    top_strategy = float(row.get("top_strategy_positive_contribution_pct") or 0.0)
    top_symbol = float(row.get("top_symbol_positive_contribution_pct") or 0.0)

    return (
        math.log1p(total_return)
        * max(profit_factor, 0.0)
        * max(retention, 0.0)
        / (1.0 + max_dd * 5.0)
        / (1.0 + exec_drag)
        / (1.0 + filter_skip)
        / (1.0 + min_oversize)
        / (1.0 + top_strategy + top_symbol)
    )


def _passes_entry_filters(trade: dict[str, Any], variant: EntryFilterVariant) -> tuple[bool, str | None]:
    if variant.minimum_expectancy_score is not None:
        score = trade.get("expectancy_score")
        if score is None:
            return False, "missing_expectancy_score"
        if float(score) < variant.minimum_expectancy_score:
            return False, "expectancy_score_below_minimum"

    if variant.minimum_expectancy_sample_count is not None:
        sample_count = trade.get("expectancy_sample_count")
        if sample_count is None:
            return False, "missing_expectancy_sample_count"
        if int(sample_count) < variant.minimum_expectancy_sample_count:
            return False, "expectancy_sample_count_below_minimum"

    if variant.max_spread_pct is not None:
        spread_pct = trade.get("spread_pct")
        if spread_pct is None:
            return False, "missing_spread_pct"
        if float(spread_pct) > variant.max_spread_pct:
            return False, "spread_pct_above_maximum"

    if not _quality_allowed(trade.get("construction_quality"), variant.construction_quality_mode):
        if trade.get("construction_quality") is None:
            return False, "missing_construction_quality"
        return False, "construction_quality_not_allowed"

    return True, None


def _replay_scenario(
    *,
    trades: list[dict[str, Any]],
    variant: EntryFilterVariant,
    risk_per_trade_pct: float,
    max_trade_risk_dollars: float,
    policy: ReplayPolicy,
    thresholds: Thresholds,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    equity = variant.starting_capital
    equity_points: list[tuple[str, float]] = [("START", variant.starting_capital)]
    equity_rows: list[dict[str, Any]] = []

    attempted_trade_count = len(trades)
    eligible_after_entry_filter_count = 0
    sized_trade_count = 0
    skipped_entry_filter_count = 0
    skipped_entry_filter_reasons: Counter[str] = Counter()
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
    by_scope: defaultdict[str, float] = defaultdict(float)
    by_quality: defaultdict[str, int] = defaultdict(int)

    for trade in trades:
        ok, skip_reason = _passes_entry_filters(trade, variant)
        if not ok:
            skipped_entry_filter_count += 1
            skipped_entry_filter_reasons[str(skip_reason)] += 1
            continue
        eligible_after_entry_filter_count += 1

        if equity <= 0:
            skipped_non_positive_equity_count += 1
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
        by_scope[str(trade.get("expectancy_scope") or "UNKNOWN")] += net_pnl
        by_quality[str(trade.get("construction_quality") or "UNKNOWN")] += 1

        equity_points.append((str(trade["date"]), equity))
        equity_rows.append(
            {
                "scenario_name": variant.name,
                "starting_capital": variant.starting_capital,
                "minimum_expectancy_score": variant.minimum_expectancy_score,
                "minimum_expectancy_sample_count": variant.minimum_expectancy_sample_count,
                "max_spread_pct": variant.max_spread_pct,
                "construction_quality_mode": variant.construction_quality_mode,
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
                "spread_pct": trade.get("spread_pct"),
                "expectancy_score": trade.get("expectancy_score"),
                "expectancy_sample_count": trade.get("expectancy_sample_count"),
                "construction_quality": trade.get("construction_quality"),
                "minimum_contract_oversize_accepted": budget < unit_risk,
            }
        )

    total_pnl = equity - variant.starting_capital
    total_return = total_pnl / variant.starting_capital if variant.starting_capital else 0.0
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (None if gross_profit <= 0 else math.inf)
    winning_trade_count = sum(1 for value in pnl_values if value > 0)
    losing_trade_count = sum(1 for value in pnl_values if value < 0)
    win_rate = winning_trade_count / sized_trade_count if sized_trade_count else 0.0
    max_dd_pct, max_dd_dollars, max_dd_date, peak_equity = _max_drawdown(equity_points)
    trade_retention_rate = sized_trade_count / attempted_trade_count if attempted_trade_count else 0.0
    entry_filter_skip_rate = skipped_entry_filter_count / attempted_trade_count if attempted_trade_count else 0.0
    eligible_retention_rate = sized_trade_count / eligible_after_entry_filter_count if eligible_after_entry_filter_count else 0.0
    min_contract_oversize_rate = minimum_contract_oversize_accepted_count / sized_trade_count if sized_trade_count else 0.0
    execution_cost_pct_of_gross_profit = (total_execution_cost + total_fee_cost) / gross_profit if gross_profit > 0 else 0.0

    top_symbol, total_positive_symbol_pnl = _positive_contribution(by_symbol)
    top_strategy, total_positive_strategy_pnl = _positive_contribution(by_strategy)
    top_year, total_positive_year_pnl = _positive_contribution(by_year)
    top_scope, total_positive_scope_pnl = _positive_contribution(by_scope)

    top_symbol_pct = top_symbol["positive_contribution_pct"] if top_symbol else None
    top_strategy_pct = top_strategy["positive_contribution_pct"] if top_strategy else None
    top_year_pct = top_year["positive_contribution_pct"] if top_year else None
    top_scope_pct = top_scope["positive_contribution_pct"] if top_scope else None

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
        "scenario_name": variant.name,
        "capital_scenario": variant.starting_capital,
        "starting_capital": variant.starting_capital,
        "risk_per_trade_pct": risk_per_trade_pct,
        "max_trade_risk_dollars": max_trade_risk_dollars,
        "minimum_expectancy_score": variant.minimum_expectancy_score,
        "minimum_expectancy_sample_count": variant.minimum_expectancy_sample_count,
        "max_spread_pct": variant.max_spread_pct,
        "construction_quality_mode": variant.construction_quality_mode,
        "entry_rule_name": variant.name.split("_", 2)[-1],
        "passes_entry_filter_gate": passes,
        "entry_filter_gate_status": "pass" if passes else "fail",
        "failure_reasons": failure_reasons,
        "gate_failures": gate_failures,
        "attempted_trade_count": attempted_trade_count,
        "eligible_after_entry_filter_count": eligible_after_entry_filter_count,
        "sized_trade_count": sized_trade_count,
        "skipped_trade_count": attempted_trade_count - sized_trade_count,
        "skipped_entry_filter_count": skipped_entry_filter_count,
        "skipped_entry_filter_reasons": dict(sorted(skipped_entry_filter_reasons.items())),
        "skipped_min_contract_oversize_count": skipped_min_contract_oversize_count,
        "skipped_budget_below_minimum_count": skipped_budget_below_minimum_count,
        "skipped_non_positive_equity_count": skipped_non_positive_equity_count,
        "entry_filter_skip_rate": entry_filter_skip_rate,
        "trade_retention_rate": trade_retention_rate,
        "eligible_retention_rate": eligible_retention_rate,
        "ending_capital": equity,
        "total_pnl": total_pnl,
        "total_return": total_return,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "winning_trade_count": winning_trade_count,
        "losing_trade_count": losing_trade_count,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_dollars": max_dd_dollars,
        "max_drawdown_date": max_dd_date,
        "peak_equity": peak_equity,
        "average_risk_dollars": (sum(risk_amounts) / len(risk_amounts)) if risk_amounts else 0.0,
        "median_risk_dollars": _median(risk_amounts),
        "minimum_contract_oversize_accepted_count": minimum_contract_oversize_accepted_count,
        "minimum_contract_oversize_accepted_rate": min_contract_oversize_rate,
        "max_effective_risk_per_trade_pct": max_effective_risk_per_trade_pct,
        "total_execution_cost_dollars": total_execution_cost,
        "total_fee_cost_dollars": total_fee_cost,
        "total_combined_execution_and_fee_cost_dollars": total_execution_cost + total_fee_cost,
        "execution_cost_pct_of_gross_profit": execution_cost_pct_of_gross_profit,
        "total_contract_units": total_contract_units,
        "top_symbol": top_symbol,
        "top_symbol_positive_contribution_pct": top_symbol_pct,
        "total_positive_symbol_pnl": total_positive_symbol_pnl,
        "top_strategy": top_strategy,
        "top_strategy_positive_contribution_pct": top_strategy_pct,
        "total_positive_strategy_pnl": total_positive_strategy_pnl,
        "top_year": top_year,
        "top_year_positive_contribution_pct": top_year_pct,
        "total_positive_year_pnl": total_positive_year_pnl,
        "top_expectancy_scope": top_scope,
        "top_expectancy_scope_positive_contribution_pct": top_scope_pct,
        "total_positive_expectancy_scope_pnl": total_positive_scope_pnl,
        "construction_quality_counts": dict(sorted(by_quality.items())),
    }
    row["robustness_score"] = _calculate_score(row)
    return row, equity_rows


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    n = len(sorted_values)
    mid = n // 2
    if n % 2:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def _build_summary(
    *,
    scenarios: list[dict[str, Any]],
    equity_rows: list[dict[str, Any]],
    input_diagnostics: dict[str, Any],
    args: argparse.Namespace,
    thresholds: Thresholds,
    policy: ReplayPolicy,
    output_dir: Path,
) -> dict[str, Any]:
    passing = [row for row in scenarios if row.get("passes_entry_filter_gate")]
    best_overall = max(passing, key=lambda row: row.get("robustness_score", -1.0), default=None)
    best_by_capital: dict[str, dict[str, Any]] = {}
    for capital in sorted({row["starting_capital"] for row in scenarios}):
        capital_passing = [row for row in passing if row["starting_capital"] == capital]
        if capital_passing:
            best_by_capital[str(capital)] = max(capital_passing, key=lambda row: row.get("robustness_score", -1.0))
        else:
            capital_rows = [row for row in scenarios if row["starting_capital"] == capital]
            if capital_rows:
                best_by_capital[str(capital)] = max(capital_rows, key=lambda row: row.get("total_return", -math.inf))

    failure_counts: Counter[str] = Counter()
    skip_reason_counts: Counter[str] = Counter()
    for row in scenarios:
        for reason in row.get("failure_reasons", []):
            failure_counts[str(reason)] += 1
        for reason, count in row.get("skipped_entry_filter_reasons", {}).items():
            skip_reason_counts[str(reason)] += int(count)

    blockers: list[str] = []
    warnings: list[str] = []
    if not scenarios:
        blockers.append("no_entry_filter_scenarios_generated")
    if not passing:
        blockers.append("no_passing_entry_filter_scenarios")
    missing_passing_capitals = sorted(
        capital for capital in {row["starting_capital"] for row in scenarios}
        if str(capital) not in best_by_capital or not best_by_capital[str(capital)].get("passes_entry_filter_gate")
    )
    if missing_passing_capitals:
        warnings.append("some_starting_capitals_have_no_passing_entry_filter_variant")

    summary = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": not blockers,
        "readiness_state": "pass" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "scenario_count": len(scenarios),
        "passing_scenario_count": len(passing),
        "starting_capitals": args.starting_capitals,
        "minimum_expectancy_scores": args.minimum_expectancy_scores,
        "minimum_expectancy_sample_counts": args.minimum_expectancy_sample_counts,
        "max_spread_pcts": args.max_spread_pcts,
        "construction_quality_modes": args.construction_quality_modes,
        "risk_per_trade_pct": args.risk_per_trade_pct,
        "max_trade_risk_dollars": args.max_trade_risk_dollars,
        "best_overall_scenario": best_overall,
        "best_by_capital": best_by_capital,
        "gate_failure_counts": dict(sorted(failure_counts.items())),
        "aggregate_entry_filter_skip_reason_counts": dict(sorted(skip_reason_counts.items())),
        "input_diagnostics": input_diagnostics,
        "replay_policy": {
            "risk_per_trade_pct": args.risk_per_trade_pct,
            "max_trade_risk_dollars": args.max_trade_risk_dollars,
            "execution_cost_model": "entry_filter_plus_quote_native_no_mid_spread_cost_plus_ibkr_like_fees",
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
            "minimum_contract_risk_model": "historical_position_risk_dollars_divided_by_contract_units_proxy",
            "expectancy_rebuild_allowed": False,
            "reselection_allowed": False,
            "entry_exit_rule_changes_allowed": False,
            "broker_fill_simulation_allowed": False,
        },
        "thresholds": thresholds.__dict__,
        "explicit_exclusions": [
            "strategy_reselection",
            "expectancy_rebuild",
            "exit_rule_optimization",
            "defensive_adjustment_simulation",
            "broker_order_routing",
            "full_margin_model",
            "portfolio_margin",
            "intraday_order_book_queue_modeling",
            "realized_outcome_based_filter_selection",
        ],
        "paths": {
            "summary_path": str(output_dir / "signalforge_portfolio_entry_filter_sensitivity_summary.json"),
            "scenarios_path": str(output_dir / "signalforge_portfolio_entry_filter_sensitivity_scenarios.jsonl"),
            "equity_curves_path": str(output_dir / "signalforge_portfolio_entry_filter_sensitivity_equity_curves.jsonl"),
            "thresholds_path": str(output_dir / "signalforge_portfolio_entry_filter_sensitivity_thresholds.json"),
        },
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay entry filter sensitivity variants against an enriched portfolio ledger.")
    parser.add_argument("--trade-ledger", required=True, type=Path)
    parser.add_argument("--starting-capitals", required=True, type=_parse_float_list)
    parser.add_argument("--minimum-expectancy-scores", required=True, type=_parse_optional_float_list)
    parser.add_argument("--minimum-expectancy-sample-counts", required=True, type=_parse_optional_int_list)
    parser.add_argument("--max-spread-pcts", required=True, type=_parse_optional_float_list)
    parser.add_argument("--construction-quality-modes", required=True, type=_parse_str_list)
    parser.add_argument("--risk-per-trade-pct", type=float, required=True)
    parser.add_argument("--max-trade-risk-dollars", type=float, required=True)
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
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    raw_rows = _read_jsonl(args.trade_ledger)
    trades, input_diagnostics = _normalize_trade_rows(raw_rows)

    policy = ReplayPolicy(
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
    all_equity_rows: list[dict[str, Any]] = []
    for capital in args.starting_capitals:
        for score in args.minimum_expectancy_scores:
            for sample in args.minimum_expectancy_sample_counts:
                for spread in args.max_spread_pcts:
                    for quality_mode in args.construction_quality_modes:
                        variant = EntryFilterVariant(
                            starting_capital=capital,
                            minimum_expectancy_score=score,
                            minimum_expectancy_sample_count=sample,
                            max_spread_pct=spread,
                            construction_quality_mode=quality_mode,
                        )
                        scenario, equity_rows = _replay_scenario(
                            trades=trades,
                            variant=variant,
                            risk_per_trade_pct=args.risk_per_trade_pct,
                            max_trade_risk_dollars=args.max_trade_risk_dollars,
                            policy=policy,
                            thresholds=thresholds,
                        )
                        scenarios.append(scenario)
                        all_equity_rows.extend(equity_rows)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _build_summary(
        scenarios=scenarios,
        equity_rows=all_equity_rows,
        input_diagnostics=input_diagnostics,
        args=args,
        thresholds=thresholds,
        policy=policy,
        output_dir=output_dir,
    )

    _write_json(output_dir / "signalforge_portfolio_entry_filter_sensitivity_summary.json", summary)
    _write_jsonl(output_dir / "signalforge_portfolio_entry_filter_sensitivity_scenarios.jsonl", scenarios)
    _write_jsonl(output_dir / "signalforge_portfolio_entry_filter_sensitivity_equity_curves.jsonl", all_equity_rows)
    _write_json(output_dir / "signalforge_portfolio_entry_filter_sensitivity_thresholds.json", thresholds.__dict__)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
