from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.backtesting.portfolio import Portfolio, TradeRecord
from src.backtesting.rebalance import (
    RebalanceDecision,
    RebalanceSchedule,
    evaluate_rebalance,
)


@dataclass
class BacktestResult:
    dates: list[datetime] = field(default_factory=list)
    navs: list[float] = field(default_factory=list)
    cash: list[float] = field(default_factory=list)
    invested_values: list[float] = field(default_factory=list)
    weights: list[dict[str, float]] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    rebalance_dates: list[datetime] = field(default_factory=list)
    rebalance_decisions: list[RebalanceDecision] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dates": self.dates,
            "navs": self.navs,
            "cash": self.cash,
            "invested_values": self.invested_values,
            "weights": self.weights,
            "trades": self.trades,
            "rebalance_dates": self.rebalance_dates,
            "rebalance_decisions": self.rebalance_decisions,
        }


class BacktestEngine:
    def __init__(
        self,
        portfolio: Portfolio,
        schedule: RebalanceSchedule,
        drift_threshold: float | None = None,
    ) -> None:
        if drift_threshold is not None and drift_threshold < 0:
            raise ValueError("Drift threshold cannot be negative.")

        self.portfolio = portfolio
        self.schedule = schedule
        self.drift_threshold = drift_threshold

    def run(
        self,
        dates: list[datetime],
        prices: dict[datetime, dict[str, float]],
        target_weights: dict[datetime, dict[str, float]],
    ) -> BacktestResult:
        result = BacktestResult()

        previous_date = None
        active_target_weights: dict[str, float] | None = None

        for current_date in dates:
            if current_date not in prices:
                raise ValueError(f"Missing prices for date: {current_date}")

            daily_prices = prices[current_date]

            for symbol, price in daily_prices.items():
                self.portfolio.update_price(symbol, price)

            if current_date in target_weights:
                active_target_weights = target_weights[current_date]

            if active_target_weights is not None:
                decision = evaluate_rebalance(
                    current_date=current_date,
                    previous_date=previous_date,
                    schedule=self.schedule,
                    current_weights=self.portfolio.weights(),
                    target_weights=active_target_weights,
                    drift_threshold=self.drift_threshold,
                )

                result.rebalance_decisions.append(decision)

                if decision.should_rebalance:
                    trades = self.portfolio.rebalance_to_weights(
                        target_weights=active_target_weights,
                        prices=daily_prices,
                        trade_date=current_date,
                    )

                    result.trades.extend(trades)
                    result.rebalance_dates.append(current_date)

            result.dates.append(current_date)
            result.navs.append(self.portfolio.nav)
            result.cash.append(self.portfolio.cash)
            result.invested_values.append(self.portfolio.invested_value)
            result.weights.append(self.portfolio.weights())

            previous_date = current_date

        return result
