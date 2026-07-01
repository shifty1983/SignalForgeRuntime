from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PortfolioEquityReconstructionResult:
    rows: list[dict[str, Any]]
    summary: dict[str, Any]


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


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
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


def _sized_sort_key(row: dict[str, Any]) -> tuple[int, str, str, str]:
    replay_index = _coerce_int(row.get("replay_index"))
    return (
        replay_index if replay_index is not None else 999999999,
        str(row.get("decision_date") or "9999-12-31"),
        str(row.get("symbol") or "ZZZ_UNKNOWN_SYMBOL"),
        str(row.get("selected_strategy") or "ZZZ_UNKNOWN_STRATEGY"),
    )


def _realization_date(row: dict[str, Any]) -> str | None:
    for field in (
        "portfolio_realization_date",
        "outcome_availability_date",
        "selected_outcome_availability_date",
    ):
        value = row.get(field)
        if value not in (None, ""):
            return str(value)[:10]

    return None


def _realization_sort_key(row: dict[str, Any]) -> tuple[str, int, str, str]:
    return (
        _realization_date(row) or "9999-12-31",
        _coerce_int(row.get("replay_index")) or 999999999,
        str(row.get("symbol") or "ZZZ_UNKNOWN_SYMBOL"),
        str(row.get("selected_strategy") or "ZZZ_UNKNOWN_STRATEGY"),
    )


def _mean(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def _extract_starting_equity(
    *,
    position_sizing_rows: list[dict[str, Any]],
    position_sizing_summary: dict[str, Any],
) -> float | None:
    summary_starting_equity = _coerce_float(
        position_sizing_summary.get("capital_model", {}).get("starting_equity")
    )
    if summary_starting_equity is not None:
        return summary_starting_equity

    sized_rows = [
        row for row in position_sizing_rows if row.get("sizing_state") == "sized"
    ]
    if not sized_rows:
        return None

    sorted_rows = sorted(sized_rows, key=_sized_sort_key)
    return _coerce_float(sorted_rows[0].get("equity_before_trade"))


def _build_daily_curve(
    *,
    sized_rows: list[dict[str, Any]],
    starting_equity: float,
) -> list[dict[str, Any]]:
    rows_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in sorted(sized_rows, key=_realization_sort_key):
        realization_date = _realization_date(row)
        if realization_date is None:
            continue
        rows_by_date[realization_date].append(row)

    curve_rows: list[dict[str, Any]] = []

    current_equity = starting_equity
    peak_equity = starting_equity

    for curve_index, realization_date in enumerate(sorted(rows_by_date), start=1):
        day_rows = rows_by_date[realization_date]

        pnl_values = [
            _coerce_float(row.get("realized_pnl_dollars")) for row in day_rows
        ]
        realized_returns = [
            _coerce_float(row.get("realized_return")) for row in day_rows
        ]
        position_risks = [
            _coerce_float(row.get("position_risk_dollars")) for row in day_rows
        ]

        pnl_values = [value for value in pnl_values if value is not None]
        realized_returns = [value for value in realized_returns if value is not None]
        position_risks = [value for value in position_risks if value is not None]

        starting_equity_for_day = current_equity
        realized_pnl_dollars = sum(pnl_values)
        ending_equity_for_day = starting_equity_for_day + realized_pnl_dollars
        current_equity = ending_equity_for_day

        gross_profit = sum(value for value in pnl_values if value > 0)
        gross_loss = abs(sum(value for value in pnl_values if value < 0))

        winning_trade_count = sum(1 for value in pnl_values if value > 0)
        losing_trade_count = sum(1 for value in pnl_values if value < 0)
        flat_trade_count = sum(1 for value in pnl_values if value == 0)

        peak_equity = max(peak_equity, ending_equity_for_day)
        drawdown_dollars = ending_equity_for_day - peak_equity
        drawdown_pct = drawdown_dollars / peak_equity if peak_equity > 0 else None

        symbols = sorted(
            {
                str(row.get("symbol"))
                for row in day_rows
                if row.get("symbol") is not None
            }
        )
        strategies = sorted(
            {
                str(row.get("selected_strategy"))
                for row in day_rows
                if row.get("selected_strategy") is not None
            }
        )
        decision_dates = sorted(
            {
                str(row.get("decision_date"))
                for row in day_rows
                if row.get("decision_date") is not None
            }
        )

        curve_rows.append(
            {
                "equity_curve_id": f"portfolio_equity_curve_{curve_index:08d}",
                "curve_index": curve_index,
                "date": realization_date,
                "realization_date": realization_date,
                "starting_equity": starting_equity_for_day,
                "ending_equity": ending_equity_for_day,
                "realized_pnl_dollars": realized_pnl_dollars,
                "daily_return": (
                    realized_pnl_dollars / starting_equity_for_day
                    if starting_equity_for_day > 0
                    else None
                ),
                "cumulative_return": (
                    ending_equity_for_day / starting_equity - 1
                    if starting_equity > 0
                    else None
                ),
                "peak_equity_to_date": peak_equity,
                "drawdown_dollars": drawdown_dollars,
                "drawdown_pct": drawdown_pct,
                "closed_trade_count": len(day_rows),
                "winning_trade_count": winning_trade_count,
                "losing_trade_count": losing_trade_count,
                "flat_trade_count": flat_trade_count,
                "gross_profit_dollars": gross_profit,
                "gross_loss_dollars": gross_loss,
                "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
                "average_realized_return": _mean(realized_returns),
                "average_position_risk_dollars": _mean(position_risks),
                "symbols": symbols,
                "symbol_count": len(symbols),
                "strategies": strategies,
                "strategy_count": len(strategies),
                "decision_dates": decision_dates,
                "source_position_sizing_ids": [
                    row.get("position_sizing_id") for row in day_rows
                ],
            }
        )

    return curve_rows


def build_portfolio_equity_reconstruction(
    *,
    position_sizing_rows: list[dict[str, Any]],
    position_sizing_summary: dict[str, Any],
    output_dir: str | Path,
) -> PortfolioEquityReconstructionResult:
    output_dir = Path(output_dir)
    blockers: list[str] = []

    if not bool(position_sizing_summary.get("is_ready")):
        blockers.append("position_sizing_summary_not_ready")

    if not position_sizing_rows:
        blockers.append("no_position_sizing_rows")

    starting_equity = _extract_starting_equity(
        position_sizing_rows=position_sizing_rows,
        position_sizing_summary=position_sizing_summary,
    )

    if starting_equity is None or starting_equity <= 0:
        blockers.append("invalid_starting_equity")

    sized_rows = [
        row for row in position_sizing_rows if row.get("sizing_state") == "sized"
    ]
    skipped_rows = [
        row for row in position_sizing_rows if row.get("sizing_state") == "skipped"
    ]

    if position_sizing_rows and not sized_rows:
        blockers.append("no_sized_position_rows")

    invalid_sized_rows: list[dict[str, Any]] = []
    non_positive_equity_rows: list[dict[str, Any]] = []
    missing_realization_date_rows: list[dict[str, Any]] = []

    for row in sized_rows:
        equity_before = _coerce_float(row.get("equity_before_trade"))
        equity_after = _coerce_float(row.get("equity_after_trade"))
        pnl = _coerce_float(row.get("realized_pnl_dollars"))
        decision_date = row.get("decision_date")
        realization_date = _realization_date(row)

        if (
            equity_before is None
            or equity_after is None
            or pnl is None
            or decision_date is None
            or decision_date == ""
        ):
            invalid_sized_rows.append(row)

        if realization_date is None:
            missing_realization_date_rows.append(row)

        if equity_before is not None and equity_before <= 0:
            non_positive_equity_rows.append(row)

        if equity_after is not None and equity_after <= 0:
            non_positive_equity_rows.append(row)

    if invalid_sized_rows:
        blockers.append("invalid_sized_position_rows")

    if missing_realization_date_rows:
        blockers.append("missing_portfolio_realization_date")

    if non_positive_equity_rows:
        blockers.append("non_positive_equity_in_sized_rows")

    curve_rows: list[dict[str, Any]] = []
    if starting_equity is not None and starting_equity > 0 and not invalid_sized_rows:
        curve_rows = _build_daily_curve(
            sized_rows=sized_rows,
            starting_equity=starting_equity,
        )

    if sized_rows and not curve_rows:
        blockers.append("no_equity_curve_rows")

    output_rows_path = output_dir / "signalforge_portfolio_equity_curve.jsonl"
    output_summary_path = (
        output_dir / "signalforge_portfolio_equity_reconstruction_summary.json"
    )

    ending_equity = curve_rows[-1]["ending_equity"] if curve_rows else None
    total_pnl = (
        ending_equity - starting_equity
        if ending_equity is not None and starting_equity is not None
        else None
    )
    total_return_pct = (
        total_pnl / starting_equity
        if total_pnl is not None and starting_equity is not None and starting_equity > 0
        else None
    )

    drawdown_rows = [
        row for row in curve_rows if row.get("drawdown_pct") is not None
    ]
    max_drawdown_row = (
        min(drawdown_rows, key=lambda row: row["drawdown_pct"])
        if drawdown_rows
        else None
    )

    daily_returns = [
        float(row["daily_return"])
        for row in curve_rows
        if row.get("daily_return") is not None
    ]

    daily_pnls = [
        float(row["realized_pnl_dollars"])
        for row in curve_rows
        if row.get("realized_pnl_dollars") is not None
    ]

    gross_profit = sum(value for value in daily_pnls if value > 0)
    gross_loss = abs(sum(value for value in daily_pnls if value < 0))

    winning_days = [value for value in daily_pnls if value > 0]
    losing_days = [value for value in daily_pnls if value < 0]
    flat_days = [value for value in daily_pnls if value == 0]

    symbols = sorted(
        {
            str(row.get("symbol"))
            for row in sized_rows
            if row.get("symbol") is not None
        }
    )
    strategies = sorted(
        {
            str(row.get("selected_strategy"))
            for row in sized_rows
            if row.get("selected_strategy") is not None
        }
    )

    sizing_skip_reason_counts = Counter(
        reason
        for row in skipped_rows
        for reason in row.get("sizing_skip_reasons", [])
    )
    realization_date_source_counts = Counter(
        str(row.get("realization_date_source") or "missing") for row in sized_rows
    )

    summary = {
        "adapter_type": "portfolio_equity_reconstruction_builder",
        "artifact_type": "signalforge_portfolio_equity_reconstruction",
        "contract": "portfolio_equity_reconstruction",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_position_sizing_row_count": len(position_sizing_rows),
        "sized_trade_count": len(sized_rows),
        "skipped_position_sizing_row_count": len(skipped_rows),
        "sizing_skip_reason_counts": dict(sorted(sizing_skip_reason_counts.items())),
        "equity_curve_row_count": len(curve_rows),
        "missing_realization_date_row_count": len(missing_realization_date_rows),
        "realization_date_source_counts": dict(sorted(realization_date_source_counts.items())),
        "equity_recognition_policy": "realize_pnl_on_portfolio_realization_date_outcome_availability_date",
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
        "total_pnl_dollars": total_pnl,
        "total_return_pct": total_return_pct,
        "max_drawdown_dollars": (
            max_drawdown_row["drawdown_dollars"] if max_drawdown_row else None
        ),
        "max_drawdown_pct": (
            max_drawdown_row["drawdown_pct"] if max_drawdown_row else None
        ),
        "max_drawdown_date": max_drawdown_row["date"] if max_drawdown_row else None,
        "peak_equity": (
            max(row["peak_equity_to_date"] for row in curve_rows)
            if curve_rows
            else None
        ),
        "daily_performance": {
            "trading_day_count": len(curve_rows),
            "winning_day_count": len(winning_days),
            "losing_day_count": len(losing_days),
            "flat_day_count": len(flat_days),
            "winning_day_rate": (
                len(winning_days) / len(curve_rows) if curve_rows else None
            ),
            "average_daily_return": _mean(daily_returns),
            "best_day_return": max(daily_returns) if daily_returns else None,
            "worst_day_return": min(daily_returns) if daily_returns else None,
            "gross_profit_dollars": gross_profit,
            "gross_loss_dollars": gross_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        },
        "date_range": {
            "start": curve_rows[0]["date"] if curve_rows else None,
            "end": curve_rows[-1]["date"] if curve_rows else None,
        },
        "unique_symbol_count": len(symbols),
        "unique_strategy_count": len(strategies),
        "unique_symbols_sample": symbols[:25],
        "unique_strategies": strategies,
        "source_position_sizing_summary": {
            "is_ready": position_sizing_summary.get("is_ready"),
            "sized_trade_count": position_sizing_summary.get("sized_trade_count"),
            "skipped_sequence_row_count": position_sizing_summary.get(
                "skipped_sequence_row_count"
            ),
            "non_positive_equity_row_count": position_sizing_summary.get(
                "non_positive_equity_row_count"
            ),
            "return_bound_violation_counts": position_sizing_summary.get(
                "return_bound_violation_counts",
                {},
            ),
        },
        "depends_on": {
            "position_sizing_rows": "portfolio_position_sizing_replay",
            "position_sizing_summary": "portfolio_position_sizing_replay_summary",
        },
        "paths": {
            "rows_path": str(output_rows_path),
            "summary_path": str(output_summary_path),
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
            "cagr",
            "final_metrics_report",
        ],
    }

    write_jsonl(output_rows_path, curve_rows)
    write_json(output_summary_path, summary)

    return PortfolioEquityReconstructionResult(rows=curve_rows, summary=summary)


def build_from_paths(
    *,
    position_sizing_rows_path: str | Path,
    position_sizing_summary_path: str | Path,
    output_dir: str | Path,
) -> PortfolioEquityReconstructionResult:
    position_sizing_rows = read_jsonl(position_sizing_rows_path)
    position_sizing_summary = read_json(position_sizing_summary_path)

    return build_portfolio_equity_reconstruction(
        position_sizing_rows=position_sizing_rows,
        position_sizing_summary=position_sizing_summary,
        output_dir=output_dir,
    )
