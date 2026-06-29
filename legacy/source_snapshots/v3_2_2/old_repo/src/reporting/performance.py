from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


_EPSILON = 1e-12


@dataclass(frozen=True)
class PerformanceSummary:
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    best_period: float
    worst_period: float
    average_period_return: float
    number_of_observations: int
    start_date: str | None
    end_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_series(
    data: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
    name: str = "value",
) -> pd.Series:
    if isinstance(data, pd.Series):
        series = data.copy()

    elif isinstance(data, pd.DataFrame):
        frame = data.copy()

        if date_col is not None:
            if date_col not in frame.columns:
                raise ValueError(f"date_col '{date_col}' not found in DataFrame.")
            frame = frame.set_index(date_col)

        if value_col is None:
            numeric_cols = frame.select_dtypes(include=[np.number]).columns.tolist()
            if len(numeric_cols) != 1:
                raise ValueError(
                    "value_col must be provided when DataFrame has zero or multiple numeric columns."
                )
            value_col = numeric_cols[0]

        if value_col not in frame.columns:
            raise ValueError(f"value_col '{value_col}' not found in DataFrame.")

        series = frame[value_col].copy()

    elif isinstance(data, Mapping):
        series = pd.Series(data)

    else:
        series = pd.Series(data)

    series = pd.to_numeric(series, errors="coerce")
    series = series.replace([np.inf, -np.inf], np.nan).dropna()
    series.name = name

    try:
        series = series.sort_index()
    except TypeError:
        pass

    return series


def calculate_returns_from_equity(
    equity_curve: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> pd.Series:
    equity = _to_series(
        equity_curve,
        value_col=value_col,
        date_col=date_col,
        name="equity",
    )

    if equity.empty:
        return pd.Series(dtype=float, name="returns")

    returns = equity.pct_change()
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    returns.name = "returns"

    return returns


def cumulative_returns(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> pd.Series:
    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    cumulative = (1.0 + series).cumprod() - 1.0
    cumulative.name = "cumulative_return"

    return cumulative


def equity_curve_from_returns(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    initial_capital: float = 1.0,
    value_col: str | None = None,
    date_col: str | None = None,
) -> pd.Series:
    if initial_capital <= 0:
        raise ValueError("initial_capital must be greater than zero.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    equity = initial_capital * (1.0 + series).cumprod()
    equity.name = "equity"

    return equity


def drawdown_series_from_equity(
    equity_curve: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> pd.Series:
    equity = _to_series(
        equity_curve,
        value_col=value_col,
        date_col=date_col,
        name="equity",
    )

    running_max = equity.cummax().replace(0.0, np.nan)
    drawdown = equity / running_max - 1.0
    drawdown = drawdown.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    drawdown.name = "drawdown"

    return drawdown


def drawdown_series_from_returns(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> pd.Series:
    equity = equity_curve_from_returns(
        returns,
        value_col=value_col,
        date_col=date_col,
    )

    return drawdown_series_from_equity(equity)


def max_drawdown_from_returns(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    drawdowns = drawdown_series_from_returns(
        returns,
        value_col=value_col,
        date_col=date_col,
    )

    if drawdowns.empty:
        return 0.0

    return float(drawdowns.min())


def total_return(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return 0.0

    return float((1.0 + series).prod() - 1.0)


def annualized_return(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    periods_per_year: int = 252,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return 0.0

    realized_total_return = total_return(series)

    if realized_total_return <= -1.0:
        return -1.0

    years = len(series) / periods_per_year

    if years <= 0:
        return 0.0

    return float((1.0 + realized_total_return) ** (1.0 / years) - 1.0)


def annualized_volatility(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    periods_per_year: int = 252,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if len(series) < 2:
        return 0.0

    return float(series.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if len(series) < 2:
        return 0.0

    periodic_risk_free_rate = risk_free_rate / periods_per_year
    excess_returns = series - periodic_risk_free_rate
    volatility = excess_returns.std(ddof=1)

    if abs(volatility) < _EPSILON:
        return 0.0

    return float(excess_returns.mean() / volatility * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    target_return: float = 0.0,
    periods_per_year: int = 252,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if len(series) < 2:
        return 0.0

    periodic_target = target_return / periods_per_year
    downside_returns = series[series < periodic_target] - periodic_target

    if len(downside_returns) < 2:
        return 0.0

    downside_deviation = downside_returns.std(ddof=1)

    if abs(downside_deviation) < _EPSILON:
        return 0.0

    excess_mean = series.mean() - periodic_target

    return float(excess_mean / downside_deviation * np.sqrt(periods_per_year))


def win_rate(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return 0.0

    return float((series > 0.0).mean())


def summarize_returns(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    target_return: float = 0.0,
    value_col: str | None = None,
    date_col: str | None = None,
) -> PerformanceSummary:
    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return PerformanceSummary(
            total_return=0.0,
            annualized_return=0.0,
            annualized_volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            calmar_ratio=0.0,
            win_rate=0.0,
            best_period=0.0,
            worst_period=0.0,
            average_period_return=0.0,
            number_of_observations=0,
            start_date=None,
            end_date=None,
        )

    realized_total_return = total_return(series)
    realized_annualized_return = annualized_return(
        series,
        periods_per_year=periods_per_year,
    )
    realized_annualized_volatility = annualized_volatility(
        series,
        periods_per_year=periods_per_year,
    )
    realized_max_drawdown = max_drawdown_from_returns(series)

    calmar = (
        realized_annualized_return / abs(realized_max_drawdown)
        if abs(realized_max_drawdown) > _EPSILON
        else 0.0
    )

    return PerformanceSummary(
        total_return=realized_total_return,
        annualized_return=realized_annualized_return,
        annualized_volatility=realized_annualized_volatility,
        sharpe_ratio=sharpe_ratio(
            series,
            risk_free_rate=risk_free_rate,
            periods_per_year=periods_per_year,
        ),
        sortino_ratio=sortino_ratio(
            series,
            target_return=target_return,
            periods_per_year=periods_per_year,
        ),
        max_drawdown=realized_max_drawdown,
        calmar_ratio=float(calmar),
        win_rate=win_rate(series),
        best_period=float(series.max()),
        worst_period=float(series.min()),
        average_period_return=float(series.mean()),
        number_of_observations=int(len(series)),
        start_date=str(series.index.min()) if len(series.index) else None,
        end_date=str(series.index.max()) if len(series.index) else None,
    )


def summarize_equity_curve(
    equity_curve: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    target_return: float = 0.0,
    value_col: str | None = None,
    date_col: str | None = None,
) -> PerformanceSummary:
    returns = calculate_returns_from_equity(
        equity_curve,
        value_col=value_col,
        date_col=date_col,
    )

    return summarize_returns(
        returns,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        target_return=target_return,
    )


def performance_table(
    returns_by_strategy: Mapping[str, pd.Series | Sequence[float]],
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    target_return: float = 0.0,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for strategy_name, returns in returns_by_strategy.items():
        summary = summarize_returns(
            returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            target_return=target_return,
        ).to_dict()

        summary["strategy"] = strategy_name
        rows.append(summary)

    if not rows:
        return pd.DataFrame()

    table = pd.DataFrame(rows)
    table = table.set_index("strategy")

    return table
