from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.backtesting.engine import BacktestResult
from src.backtesting.performance import PerformanceSummary, summarize_performance


@dataclass(frozen=True)
class BacktestResearchReport:
    performance: PerformanceSummary
    nav_series: list[dict[str, Any]]
    exposure_series: list[dict[str, Any]]
    trade_summary: dict[str, Any]
    rebalance_summary: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "performance": self.performance.to_dict(),
            "nav_series": self.nav_series,
            "exposure_series": self.exposure_series,
            "trade_summary": dict(self.trade_summary),
            "rebalance_summary": dict(self.rebalance_summary),
            "metadata": dict(self.metadata),
        }


def _date_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def build_nav_series(
    result: BacktestResult,
) -> list[dict[str, Any]]:
    """
    Convert BacktestResult NAV fields into report rows.
    """

    return [
        {
            "date": _date_value(date),
            "nav": nav,
            "cash": cash,
            "invested_value": invested_value,
        }
        for date, nav, cash, invested_value in zip(
            result.dates,
            result.navs,
            result.cash,
            result.invested_values,
        )
    ]


def build_exposure_series(
    result: BacktestResult,
) -> list[dict[str, Any]]:
    """
    Convert BacktestResult weights into date-level exposure rows.
    """

    exposure_rows: list[dict[str, Any]] = []

    for date, weights in zip(result.dates, result.weights):
        gross_exposure = sum(abs(weight) for weight in weights.values())
        net_exposure = sum(weights.values())
        max_abs_weight = max((abs(weight) for weight in weights.values()), default=0.0)

        exposure_rows.append(
            {
                "date": _date_value(date),
                "gross_exposure": gross_exposure,
                "net_exposure": net_exposure,
                "max_abs_weight": max_abs_weight,
                "weights": dict(weights),
            }
        )

    return exposure_rows


def build_trade_summary(
    result: BacktestResult,
) -> dict[str, Any]:
    """
    Summarize trade activity from BacktestResult.
    """

    total_gross_value = sum(abs(trade.gross_value) for trade in result.trades)
    total_transaction_cost = sum(trade.transaction_cost for trade in result.trades)

    symbols = sorted({trade.symbol for trade in result.trades})

    return {
        "trade_count": len(result.trades),
        "symbols_traded": symbols,
        "symbol_count": len(symbols),
        "total_gross_value": total_gross_value,
        "total_transaction_cost": total_transaction_cost,
    }


def build_rebalance_summary(
    result: BacktestResult,
) -> dict[str, Any]:
    """
    Summarize rebalance activity from BacktestResult.
    """

    rebalance_count = len(result.rebalance_dates)
    decision_count = len(result.rebalance_decisions)

    reasons: dict[str, int] = {}

    for decision in result.rebalance_decisions:
        reasons[decision.reason] = reasons.get(decision.reason, 0) + 1

    average_turnover = (
        sum(decision.turnover for decision in result.rebalance_decisions)
        / decision_count
        if decision_count
        else 0.0
    )

    max_drift = max(
        (decision.max_drift for decision in result.rebalance_decisions),
        default=0.0,
    )

    return {
        "rebalance_count": rebalance_count,
        "decision_count": decision_count,
        "reasons": reasons,
        "average_turnover": average_turnover,
        "max_drift": max_drift,
        "rebalance_dates": [_date_value(date) for date in result.rebalance_dates],
    }


def build_backtest_research_report(
    result: BacktestResult,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
    metadata: dict[str, Any] | None = None,
) -> BacktestResearchReport:
    """
    Build a research-facing report from a BacktestResult.
    """

    if not result.navs:
        raise ValueError("BacktestResult contains no NAV values.")

    performance = summarize_performance(
        values=result.navs,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )

    return BacktestResearchReport(
        performance=performance,
        nav_series=build_nav_series(result),
        exposure_series=build_exposure_series(result),
        trade_summary=build_trade_summary(result),
        rebalance_summary=build_rebalance_summary(result),
        metadata=dict(metadata or {}),
    )
