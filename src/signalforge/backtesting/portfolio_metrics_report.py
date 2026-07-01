from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PortfolioMetricsReportResult:
    report: dict[str, Any]


def read_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc

            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")

            rows.append(value)

    return rows


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    try:
        parsed = float(text)
    except ValueError:
        return None

    return parsed if math.isfinite(parsed) else None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None

    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _downside_sample_std(values: list[float], *, threshold: float = 0.0) -> float | None:
    downside_values = [min(0.0, value - threshold) for value in values]
    return _sample_std(downside_values)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _sized_sort_key(row: dict[str, Any]) -> tuple[int, str, str, str]:
    replay_index = _coerce_int(row.get("replay_index"))
    return (
        replay_index if replay_index is not None else 999999999,
        str(row.get("decision_date") or "9999-12-31"),
        str(row.get("symbol") or "ZZZ_UNKNOWN_SYMBOL"),
        str(row.get("selected_strategy") or "ZZZ_UNKNOWN_STRATEGY"),
    )


def _curve_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    curve_index = _coerce_int(row.get("curve_index"))
    return (
        curve_index if curve_index is not None else 999999999,
        str(row.get("date") or "9999-12-31"),
    )


def _cagr(
    *,
    starting_equity: float | None,
    ending_equity: float | None,
    start_date: date | None,
    end_date: date | None,
) -> float | None:
    if (
        starting_equity is None
        or ending_equity is None
        or starting_equity <= 0
        or ending_equity <= 0
        or start_date is None
        or end_date is None
    ):
        return None

    day_count = (end_date - start_date).days
    if day_count <= 0:
        return None

    years = day_count / 365.25
    equity_ratio = ending_equity / starting_equity

    if equity_ratio <= 0:
        return None

    exponent = 1 / years

    try:
        value = math.exp(math.log(equity_ratio) * exponent) - 1
    except (OverflowError, ValueError):
        return None

    return value if math.isfinite(value) else None


def _trade_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [
        value
        for value in (_coerce_float(row.get("realized_pnl_dollars")) for row in rows)
        if value is not None
    ]
    realized_returns = [
        value
        for value in (_coerce_float(row.get("realized_return")) for row in rows)
        if value is not None
    ]
    position_risks = [
        value
        for value in (_coerce_float(row.get("position_risk_dollars")) for row in rows)
        if value is not None
    ]

    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    flats = [value for value in pnls if value == 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    average_win = _mean(wins)
    average_loss = _mean(losses)

    return {
        "trade_count": len(rows),
        "winning_trade_count": len(wins),
        "losing_trade_count": len(losses),
        "flat_trade_count": len(flats),
        "win_rate": len(wins) / len(rows) if rows else None,
        "loss_rate": len(losses) / len(rows) if rows else None,
        "total_pnl_dollars": sum(pnls),
        "gross_profit_dollars": gross_profit,
        "gross_loss_dollars": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "average_trade_pnl_dollars": _mean(pnls),
        "average_win_dollars": average_win,
        "average_loss_dollars": average_loss,
        "payoff_ratio": (
            average_win / abs(average_loss)
            if average_win is not None and average_loss is not None and average_loss != 0
            else None
        ),
        "largest_win_dollars": max(wins) if wins else None,
        "largest_loss_dollars": min(losses) if losses else None,
        "average_realized_return": _mean(realized_returns),
        "median_realized_return": (
            sorted(realized_returns)[len(realized_returns) // 2]
            if realized_returns
            else None
        ),
        "average_position_risk_dollars": _mean(position_risks),
        "min_position_risk_dollars": min(position_risks) if position_risks else None,
        "max_position_risk_dollars": max(position_risks) if position_risks else None,
    }


def _daily_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    daily_returns = [
        value
        for value in (_coerce_float(row.get("daily_return")) for row in rows)
        if value is not None
    ]
    daily_pnls = [
        value
        for value in (_coerce_float(row.get("realized_pnl_dollars")) for row in rows)
        if value is not None
    ]

    wins = [value for value in daily_pnls if value > 0]
    losses = [value for value in daily_pnls if value < 0]
    flats = [value for value in daily_pnls if value == 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    average_daily_return = _mean(daily_returns)
    daily_return_std = _sample_std(daily_returns)
    downside_daily_return_std = _downside_sample_std(daily_returns)

    annualized_sharpe = (
        (average_daily_return / daily_return_std) * math.sqrt(252)
        if average_daily_return is not None
        and daily_return_std is not None
        and daily_return_std > 0
        else None
    )

    annualized_sortino = (
        (average_daily_return / downside_daily_return_std) * math.sqrt(252)
        if average_daily_return is not None
        and downside_daily_return_std is not None
        and downside_daily_return_std > 0
        else None
    )

    return {
        "trading_day_count": len(rows),
        "winning_day_count": len(wins),
        "losing_day_count": len(losses),
        "flat_day_count": len(flats),
        "winning_day_rate": len(wins) / len(rows) if rows else None,
        "average_daily_return": average_daily_return,
        "daily_return_std": daily_return_std,
        "downside_daily_return_std": downside_daily_return_std,
        "best_day_return": max(daily_returns) if daily_returns else None,
        "worst_day_return": min(daily_returns) if daily_returns else None,
        "total_daily_pnl_dollars": sum(daily_pnls),
        "gross_profit_dollars": gross_profit,
        "gross_loss_dollars": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "average_winning_day_pnl_dollars": _mean(wins),
        "average_losing_day_pnl_dollars": _mean(losses),
        "annualized_sharpe": annualized_sharpe,
        "annualized_sortino": annualized_sortino,
        "daily_sharpe_like": annualized_sharpe,
        "risk_free_rate_assumption": 0.0,
        "annualization_trading_days": 252,
    }


def _breakdown_by(
    rows: list[dict[str, Any]],
    field: str,
    *,
    limit: int | None = None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        key = row.get(field)
        key_text = str(key) if key is not None and key != "" else "UNKNOWN"
        grouped[key_text].append(row)

    items = sorted(
        grouped.items(),
        key=lambda item: (
            -len(item[1]),
            item[0],
        ),
    )

    if limit is not None:
        items = items[:limit]

    result: dict[str, dict[str, Any]] = {}

    for key, group_rows in items:
        result[key] = _trade_metrics(group_rows)

    return result


def _breakdown_by_year_from_trades(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        realization_date = str(
            row.get("portfolio_realization_date")
            or row.get("outcome_availability_date")
            or row.get("decision_date")
            or ""
        )
        year = realization_date[:4] if len(realization_date) >= 4 else "UNKNOWN"
        grouped[year].append(row)

    return {
        year: _trade_metrics(group_rows)
        for year, group_rows in sorted(grouped.items())
    }


def _annual_equity_curve_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        curve_date = str(row.get("date") or "")
        year = curve_date[:4] if len(curve_date) >= 4 else "UNKNOWN"
        grouped[year].append(row)

    result: dict[str, dict[str, Any]] = {}
    for year, group_rows in sorted(grouped.items()):
        sorted_rows = sorted(group_rows, key=_curve_sort_key)
        start_equity = _coerce_float(sorted_rows[0].get("starting_equity"))
        end_equity = _coerce_float(sorted_rows[-1].get("ending_equity"))
        pnls = [
            value
            for value in (_coerce_float(row.get("realized_pnl_dollars")) for row in sorted_rows)
            if value is not None
        ]
        daily_returns = [
            value
            for value in (_coerce_float(row.get("daily_return")) for row in sorted_rows)
            if value is not None
        ]
        drawdowns = [
            value
            for value in (_coerce_float(row.get("drawdown_pct")) for row in sorted_rows)
            if value is not None
        ]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        result[year] = {
            "equity_curve_day_count": len(sorted_rows),
            "starting_equity": start_equity,
            "ending_equity": end_equity,
            "total_pnl_dollars": sum(pnls),
            "return_pct": (
                end_equity / start_equity - 1
                if start_equity is not None and start_equity > 0 and end_equity is not None
                else None
            ),
            "winning_day_count": len(wins),
            "losing_day_count": len(losses),
            "winning_day_rate": len(wins) / len(sorted_rows) if sorted_rows else None,
            "gross_profit_dollars": gross_profit,
            "gross_loss_dollars": gross_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
            "average_daily_return": _mean(daily_returns),
            "max_drawdown_pct": min(drawdowns) if drawdowns else None,
            "start_date": sorted_rows[0].get("date"),
            "end_date": sorted_rows[-1].get("date"),
        }

    return result


def build_portfolio_metrics_report(
    *,
    equity_curve_rows: list[dict[str, Any]],
    equity_reconstruction_summary: dict[str, Any],
    position_sizing_rows: list[dict[str, Any]],
    position_sizing_summary: dict[str, Any],
    output_dir: str | Path,
) -> PortfolioMetricsReportResult:
    output_dir = Path(output_dir)
    blockers: list[str] = []

    if not bool(equity_reconstruction_summary.get("is_ready")):
        blockers.append("equity_reconstruction_summary_not_ready")

    if not bool(position_sizing_summary.get("is_ready")):
        blockers.append("position_sizing_summary_not_ready")

    if not equity_curve_rows:
        blockers.append("no_equity_curve_rows")

    if not position_sizing_rows:
        blockers.append("no_position_sizing_rows")

    sorted_curve_rows = sorted(equity_curve_rows, key=_curve_sort_key)
    sorted_position_rows = sorted(position_sizing_rows, key=_sized_sort_key)

    sized_rows = [
        row for row in sorted_position_rows if row.get("sizing_state") == "sized"
    ]
    skipped_rows = [
        row for row in sorted_position_rows if row.get("sizing_state") == "skipped"
    ]

    if position_sizing_rows and not sized_rows:
        blockers.append("no_sized_trades")

    starting_equity = _coerce_float(equity_reconstruction_summary.get("starting_equity"))
    ending_equity = _coerce_float(equity_reconstruction_summary.get("ending_equity"))
    total_return_pct = _coerce_float(
        equity_reconstruction_summary.get("total_return_pct")
    )
    max_drawdown_pct = _coerce_float(
        equity_reconstruction_summary.get("max_drawdown_pct")
    )
    max_drawdown_dollars = _coerce_float(
        equity_reconstruction_summary.get("max_drawdown_dollars")
    )

    if starting_equity is None or starting_equity <= 0:
        blockers.append("invalid_starting_equity")

    if ending_equity is None or ending_equity <= 0:
        blockers.append("invalid_ending_equity")

    if sorted_curve_rows:
        curve_ending_equity = _coerce_float(sorted_curve_rows[-1].get("ending_equity"))
        if (
            curve_ending_equity is not None
            and ending_equity is not None
            and abs(curve_ending_equity - ending_equity) > 0.01
        ):
            blockers.append("ending_equity_mismatch")

    start_date = _parse_date(
        equity_reconstruction_summary.get("date_range", {}).get("start")
    )
    end_date = _parse_date(
        equity_reconstruction_summary.get("date_range", {}).get("end")
    )

    calendar_day_span = (
        (end_date - start_date).days + 1
        if start_date is not None and end_date is not None and end_date >= start_date
        else None
    )

    cagr = _cagr(
        starting_equity=starting_equity,
        ending_equity=ending_equity,
        start_date=start_date,
        end_date=end_date,
    )

    trade_metrics = _trade_metrics(sized_rows)
    daily_metrics = _daily_metrics(sorted_curve_rows)

    skipped_reason_counts = Counter(
        reason
        for row in skipped_rows
        for reason in row.get("sizing_skip_reasons", [])
    )

    return_bound_violation_counts = position_sizing_summary.get(
        "return_bound_violation_counts",
        {},
    )

    report_path = output_dir / "signalforge_portfolio_metrics_report.json"

    report = {
        "adapter_type": "portfolio_metrics_report_builder",
        "artifact_type": "signalforge_portfolio_metrics_report",
        "contract": "portfolio_metrics_report",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "overview": {
            "starting_equity": starting_equity,
            "ending_equity": ending_equity,
            "total_pnl_dollars": (
                ending_equity - starting_equity
                if starting_equity is not None and ending_equity is not None
                else None
            ),
            "total_return_pct": total_return_pct,
            "cagr": cagr,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
                "calendar_day_span": calendar_day_span,
            },
        },
        "risk_metrics": {
            "max_drawdown_pct": max_drawdown_pct,
            "max_drawdown_dollars": max_drawdown_dollars,
            "max_drawdown_date": equity_reconstruction_summary.get(
                "max_drawdown_date"
            ),
            "peak_equity": equity_reconstruction_summary.get("peak_equity"),
            "return_to_max_drawdown_ratio": (
                total_return_pct / abs(max_drawdown_pct)
                if total_return_pct is not None
                and max_drawdown_pct is not None
                and max_drawdown_pct < 0
                else None
            ),
            "profit_to_max_drawdown_ratio": (
                (ending_equity - starting_equity) / abs(max_drawdown_dollars)
                if starting_equity is not None
                and ending_equity is not None
                and max_drawdown_dollars is not None
                and max_drawdown_dollars < 0
                else None
            ),
        },
        "trade_metrics": trade_metrics,
        "daily_metrics": daily_metrics,
        "exposure_metrics": {
            "equity_curve_day_count": len(sorted_curve_rows),
            "calendar_day_span": calendar_day_span,
            "equity_curve_day_ratio": (
                len(sorted_curve_rows) / calendar_day_span
                if calendar_day_span is not None and calendar_day_span > 0
                else None
            ),
            "average_trades_per_equity_curve_day": (
                len(sized_rows) / len(sorted_curve_rows)
                if sorted_curve_rows
                else None
            ),
        },
        "data_quality": {
            "input_equity_curve_row_count": len(equity_curve_rows),
            "input_position_sizing_row_count": len(position_sizing_rows),
            "sized_trade_count": len(sized_rows),
            "skipped_position_sizing_row_count": len(skipped_rows),
            "sizing_skip_reason_counts": dict(sorted(skipped_reason_counts.items())),
            "return_bound_violation_counts": return_bound_violation_counts,
            "source_equity_reconstruction_ready": equity_reconstruction_summary.get(
                "is_ready"
            ),
            "source_position_sizing_ready": position_sizing_summary.get("is_ready"),
            "equity_recognition_policy": equity_reconstruction_summary.get("equity_recognition_policy"),
            "realization_date_source_counts": equity_reconstruction_summary.get("realization_date_source_counts", {}),
        },
        "breakdowns": {
            "by_strategy": _breakdown_by(sized_rows, "selected_strategy"),
            "by_symbol_sample": _breakdown_by(sized_rows, "symbol", limit=50),
            "by_selected_outcome_state": _breakdown_by(
                sized_rows,
                "selected_outcome_state",
            ),
            "by_selected_expectancy_state": _breakdown_by(
                sized_rows,
                "selected_expectancy_state",
            ),
            "by_realization_year_from_trades": _breakdown_by_year_from_trades(sized_rows),
            "by_year": _annual_equity_curve_metrics(sorted_curve_rows),
        },
        "depends_on": {
            "equity_curve_rows": "portfolio_equity_reconstruction",
            "equity_reconstruction_summary": (
                "portfolio_equity_reconstruction_summary"
            ),
            "position_sizing_rows": "portfolio_position_sizing_replay",
            "position_sizing_summary": "portfolio_position_sizing_replay_summary",
        },
        "paths": {
            "report_path": str(report_path),
        },
        "explicit_exclusions": [
            "new_strategy_selection_logic",
            "new_expectancy_calculation",
            "parameter_optimization",
            "broker_execution",
            "live_orders",
            "slippage_modeling",
            "open_position_overlap_modeling",
            "mark_to_market_open_positions",
            "calendar_day_gap_fill",
            "cash_interest",
            "fees_and_commissions",
            "taxes",
            "live_broker_reconciliation",
        ],
    }

    write_json(report_path, report)

    return PortfolioMetricsReportResult(report=report)


def build_from_paths(
    *,
    equity_curve_rows_path: str | Path,
    equity_reconstruction_summary_path: str | Path,
    position_sizing_rows_path: str | Path,
    position_sizing_summary_path: str | Path,
    output_dir: str | Path,
) -> PortfolioMetricsReportResult:
    equity_curve_rows = read_jsonl(equity_curve_rows_path)
    equity_reconstruction_summary = read_json(equity_reconstruction_summary_path)
    position_sizing_rows = read_jsonl(position_sizing_rows_path)
    position_sizing_summary = read_json(position_sizing_summary_path)

    return build_portfolio_metrics_report(
        equity_curve_rows=equity_curve_rows,
        equity_reconstruction_summary=equity_reconstruction_summary,
        position_sizing_rows=position_sizing_rows,
        position_sizing_summary=position_sizing_summary,
        output_dir=output_dir,
    )
