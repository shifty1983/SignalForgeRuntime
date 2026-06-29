from __future__ import annotations

import math
from dataclasses import dataclass


def compute_returns(values: list[float]) -> list[float]:
    if len(values) < 2:
        return []

    returns = []

    for previous, current in zip(values[:-1], values[1:]):
        if previous == 0:
            raise ValueError("Previous value cannot be zero.")

        returns.append((current / previous) - 1)

    return returns


def cumulative_return(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    if values[0] == 0:
        raise ValueError("Starting value cannot be zero.")

    return (values[-1] / values[0]) - 1


def mean_return(returns: list[float]) -> float:
    if not returns:
        return 0.0

    return sum(returns) / len(returns)


def volatility(returns: list[float], periods_per_year: int = 252) -> float:
    if len(returns) < 2:
        return 0.0

    avg_return = mean_return(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)

    return math.sqrt(variance) * math.sqrt(periods_per_year)


def downside_deviation(
    returns: list[float],
    minimum_acceptable_return: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    if len(returns) < 2:
        return 0.0

    downside_returns = [
        min(0.0, r - minimum_acceptable_return)
        for r in returns
    ]

    variance = sum(r**2 for r in downside_returns) / len(downside_returns)

    return math.sqrt(variance) * math.sqrt(periods_per_year)


def sharpe_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    if len(returns) < 2:
        return 0.0

    period_rf = risk_free_rate / periods_per_year
    excess_returns = [r - period_rf for r in returns]

    vol = volatility(excess_returns, periods_per_year)

    if vol == 0:
        return 0.0

    avg_excess = mean_return(excess_returns)

    return (avg_excess * periods_per_year) / vol


def sortino_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    if len(returns) < 2:
        return 0.0

    period_rf = risk_free_rate / periods_per_year
    excess_returns = [r - period_rf for r in returns]

    downside = downside_deviation(
        returns=excess_returns,
        minimum_acceptable_return=0.0,
        periods_per_year=periods_per_year,
    )

    if downside == 0:
        return 0.0

    avg_excess = mean_return(excess_returns)

    return (avg_excess * periods_per_year) / downside


def drawdown_series(values: list[float]) -> list[float]:
    if not values:
        return []

    peak = values[0]
    drawdowns = []

    for value in values:
        peak = max(peak, value)

        if peak == 0:
            drawdowns.append(0.0)
        else:
            drawdowns.append((value / peak) - 1)

    return drawdowns


def max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0

    return min(drawdown_series(values))


def cagr(
    values: list[float],
    periods_per_year: int = 252,
) -> float:
    if len(values) < 2:
        return 0.0

    if values[0] == 0:
        raise ValueError("Starting value cannot be zero.")

    years = (len(values) - 1) / periods_per_year

    if years == 0:
        return 0.0

    return (values[-1] / values[0]) ** (1 / years) - 1


def calmar_ratio(
    values: list[float],
    periods_per_year: int = 252,
) -> float:
    annual_return = cagr(
        values=values,
        periods_per_year=periods_per_year,
    )

    drawdown = max_drawdown(values)

    if drawdown == 0:
        return 0.0

    return annual_return / abs(drawdown)


def hit_rate(returns: list[float]) -> float:
    if not returns:
        return 0.0

    winners = sum(1 for r in returns if r > 0)

    return winners / len(returns)


@dataclass(frozen=True)
class PerformanceSummary:
    start_value: float
    final_value: float
    total_return: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    hit_rate: float

    def to_dict(self) -> dict[str, float]:
        return {
            "start_value": self.start_value,
            "final_value": self.final_value,
            "total_return": self.total_return,
            "cagr": self.cagr,
            "volatility": self.volatility,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
            "calmar": self.calmar,
            "hit_rate": self.hit_rate,
        }


def summarize_performance(
    values: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> PerformanceSummary:
    if not values:
        raise ValueError("Values cannot be empty.")

    returns = compute_returns(values)

    return PerformanceSummary(
        start_value=values[0],
        final_value=values[-1],
        total_return=cumulative_return(values),
        cagr=cagr(values, periods_per_year=periods_per_year),
        volatility=volatility(returns, periods_per_year=periods_per_year),
        sharpe=sharpe_ratio(
            returns=returns,
            risk_free_rate=risk_free_rate,
            periods_per_year=periods_per_year,
        ),
        sortino=sortino_ratio(
            returns=returns,
            risk_free_rate=risk_free_rate,
            periods_per_year=periods_per_year,
        ),
        max_drawdown=max_drawdown(values),
        calmar=calmar_ratio(values, periods_per_year=periods_per_year),
        hit_rate=hit_rate(returns),
    )
