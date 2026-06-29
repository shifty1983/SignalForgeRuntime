from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from src.reporting.attribution import (
    attribution_summary,
    contribution_matrix,
    period_attribution,
    sector_attribution,
    strategy_attribution,
    symbol_attribution,
)
from src.reporting.exposures import (
    asset_class_exposure,
    greek_exposure,
    sector_exposure,
    strategy_exposure,
    summarize_exposures,
    top_positions,
)
from src.reporting.performance import (
    calculate_returns_from_equity,
    cumulative_returns,
    drawdown_series_from_returns,
    equity_curve_from_returns,
    performance_table,
    summarize_equity_curve,
    summarize_returns,
)
from src.reporting.risk_report import portfolio_risk_report, rolling_volatility
from src.reporting.trades import (
    summarize_trades,
    trade_blotter,
    trade_summary_by_strategy,
    trade_summary_by_symbol,
)


@dataclass(frozen=True)
class DashboardPayload:
    generated_at: str
    performance: dict[str, Any]
    risk: dict[str, Any]
    exposures: dict[str, Any]
    trades: dict[str, Any]
    attribution: dict[str, Any]
    time_series: dict[str, Any]
    tables: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _has_data(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, (pd.DataFrame, pd.Series)):
        return not value.empty

    try:
        return len(value) > 0
    except TypeError:
        return True


def _json_safe(value: Any) -> Any:
    if isinstance(value, DashboardPayload):
        return _json_safe(value.to_dict())

    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))

    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())

    if isinstance(value, Mapping):
        return {
            str(_json_safe(key)): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        result = float(value)
        if np.isnan(result):
            return None
        if np.isposinf(result):
            return "Infinity"
        if np.isneginf(result):
            return "-Infinity"
        return result

    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())

    if isinstance(value, float):
        if np.isnan(value):
            return None
        if np.isposinf(value):
            return "Infinity"
        if np.isneginf(value):
            return "-Infinity"
        return value

    if pd.isna(value):
        return None

    return value


def dataframe_to_records(
    frame: pd.DataFrame,
    *,
    include_index: bool = False,
    index_name: str = "index",
) -> list[dict[str, Any]]:
    if frame.empty:
        return []

    output = frame.copy()

    if include_index:
        output = output.reset_index()
        if output.columns[0] == "index":
            output = output.rename(columns={"index": index_name})

    return _json_safe(output.to_dict(orient="records"))


def series_to_points(
    series: pd.Series,
    *,
    index_name: str = "date",
    value_name: str = "value",
) -> list[dict[str, Any]]:
    if series.empty:
        return []

    frame = series.rename(value_name).reset_index()
    frame = frame.rename(columns={frame.columns[0]: index_name})

    return _json_safe(frame.to_dict(orient="records"))


def _resolve_returns(
    *,
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float] | None = None,
    equity_curve: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float] | None = None,
    return_value_col: str | None = None,
    equity_value_col: str | None = None,
    date_col: str | None = None,
) -> pd.Series:
    if returns is not None:
        if isinstance(returns, pd.Series):
            series = returns.copy()
        elif isinstance(returns, pd.DataFrame):
            frame = returns.copy()

            if date_col is not None:
                frame = frame.set_index(date_col)

            if return_value_col is None:
                numeric_cols = frame.select_dtypes(include=[np.number]).columns.tolist()
                if len(numeric_cols) != 1:
                    raise ValueError(
                        "return_value_col must be provided when returns DataFrame has zero or multiple numeric columns."
                    )
                return_value_col = numeric_cols[0]

            series = frame[return_value_col].copy()
        elif isinstance(returns, Mapping):
            series = pd.Series(returns)
        else:
            series = pd.Series(returns)

        series = pd.to_numeric(series, errors="coerce")
        series = series.replace([np.inf, -np.inf], np.nan).dropna()
        series.name = "returns"

        return series

    if equity_curve is not None:
        return calculate_returns_from_equity(
            equity_curve,
            value_col=equity_value_col,
            date_col=date_col,
        )

    return pd.Series(dtype=float, name="returns")


def dashboard_time_series(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    initial_capital: float = 1.0,
    rolling_window: int = 20,
    periods_per_year: int = 252,
) -> dict[str, Any]:
    if isinstance(returns, pd.Series):
        return_series = returns.copy()
    elif isinstance(returns, Mapping):
        return_series = pd.Series(returns)
    else:
        return_series = pd.Series(returns)

    return_series = pd.to_numeric(return_series, errors="coerce")
    return_series = return_series.replace([np.inf, -np.inf], np.nan).dropna()
    return_series.name = "returns"

    if return_series.empty:
        return {
            "returns": [],
            "cumulative_returns": [],
            "equity_curve": [],
            "drawdowns": [],
            "rolling_volatility": [],
        }

    cumulative = cumulative_returns(return_series)
    equity = equity_curve_from_returns(
        return_series,
        initial_capital=initial_capital,
    )
    drawdowns = drawdown_series_from_returns(return_series)
    rolling_vol = rolling_volatility(
        return_series,
        window=rolling_window,
        periods_per_year=periods_per_year,
    ).dropna()

    return {
        "returns": series_to_points(return_series, value_name="return"),
        "cumulative_returns": series_to_points(
            cumulative,
            value_name="cumulative_return",
        ),
        "equity_curve": series_to_points(equity, value_name="equity"),
        "drawdowns": series_to_points(drawdowns, value_name="drawdown"),
        "rolling_volatility": series_to_points(
            rolling_vol,
            value_name="rolling_volatility",
        ),
    }


def build_dashboard_data(
    *,
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float] | None = None,
    equity_curve: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float] | None = None,
    trades: pd.DataFrame | Sequence[Mapping[str, Any]] | None = None,
    positions: pd.DataFrame | Sequence[Mapping[str, Any]] | None = None,
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]] | None = None,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    target_return: float = 0.0,
    confidence_level: float = 0.95,
    initial_capital: float = 1.0,
    rolling_window: int = 20,
    top_n_positions: int = 10,
    return_limits: Mapping[str, float] | None = None,
    exposure_limits: Mapping[str, float] | None = None,
    greek_limits: Mapping[str, float] | None = None,
    return_value_col: str | None = None,
    equity_value_col: str | None = None,
    date_col: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_returns = _resolve_returns(
        returns=returns,
        equity_curve=equity_curve,
        return_value_col=return_value_col,
        equity_value_col=equity_value_col,
        date_col=date_col,
    )

    if equity_curve is not None and returns is None:
        performance_summary = summarize_equity_curve(
            equity_curve,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            target_return=target_return,
            value_col=equity_value_col,
            date_col=date_col,
        )
    else:
        performance_summary = summarize_returns(
            resolved_returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            target_return=target_return,
        )

    risk = portfolio_risk_report(
        resolved_returns,
        positions=positions if _has_data(positions) else None,
        return_limits=return_limits,
        exposure_limits=exposure_limits,
        greek_limits=greek_limits,
        periods_per_year=periods_per_year,
        confidence_level=confidence_level,
        target_return=target_return,
    )

    exposure_section: dict[str, Any] = {
        "summary": {},
        "top_positions": [],
        "asset_class": [],
        "sector": [],
        "strategy": [],
        "greeks": [],
    }

    if _has_data(positions):
        exposure_section = {
            "summary": summarize_exposures(
                positions,
                weight_col="weight",
            ).to_dict(),
            "top_positions": dataframe_to_records(
                top_positions(
                    positions,
                    n=top_n_positions,
                    weight_col="weight",
                )
            ),
            "asset_class": dataframe_to_records(
                asset_class_exposure(
                    positions,
                    weight_col="weight",
                ),
                include_index=True,
                index_name="asset_class",
            ),
            "sector": dataframe_to_records(
                sector_exposure(
                    positions,
                    weight_col="weight",
                ),
                include_index=True,
                index_name="sector",
            ),
            "strategy": dataframe_to_records(
                strategy_exposure(
                    positions,
                    weight_col="weight",
                ),
                include_index=True,
                index_name="strategy",
            ),
            "greeks": dataframe_to_records(
                greek_exposure(
                    positions,
                    weight_col="weight",
                ),
                include_index=True,
                index_name="greek",
            ),
        }

    trade_section: dict[str, Any] = {
        "summary": {},
        "blotter": [],
        "by_symbol": [],
        "by_strategy": [],
    }

    if _has_data(trades):
        trade_section = {
            "summary": summarize_trades(trades).to_dict(),
            "blotter": dataframe_to_records(trade_blotter(trades)),
            "by_symbol": dataframe_to_records(
                trade_summary_by_symbol(trades),
                include_index=True,
                index_name="symbol",
            ),
            "by_strategy": dataframe_to_records(
                trade_summary_by_strategy(trades),
                include_index=True,
                index_name="strategy",
            ),
        }

    attribution_section: dict[str, Any] = {
        "summary": {},
        "by_symbol": [],
        "by_sector": [],
        "by_strategy": [],
        "by_period": [],
        "contribution_matrix": [],
    }

    if _has_data(attribution):
        attribution_section = {
            "summary": attribution_summary(
                attribution,
                portfolio_returns=resolved_returns if not resolved_returns.empty else None,
            ).to_dict(),
            "by_symbol": dataframe_to_records(
                symbol_attribution(attribution),
                include_index=True,
                index_name="symbol",
            ),
            "by_sector": dataframe_to_records(
                sector_attribution(attribution),
                include_index=True,
                index_name="sector",
            ),
            "by_strategy": dataframe_to_records(
                strategy_attribution(attribution),
                include_index=True,
                index_name="strategy",
            ),
            "by_period": dataframe_to_records(
                period_attribution(attribution),
                include_index=True,
                index_name="date",
            ),
            "contribution_matrix": dataframe_to_records(
                contribution_matrix(attribution),
                include_index=True,
                index_name="date",
            ),
        }

    time_series = dashboard_time_series(
        resolved_returns,
        initial_capital=initial_capital,
        rolling_window=rolling_window,
        periods_per_year=periods_per_year,
    )

    payload = DashboardPayload(
        generated_at=datetime.now(timezone.utc).isoformat(),
        performance=performance_summary.to_dict(),
        risk=risk,
        exposures=exposure_section,
        trades=trade_section,
        attribution=attribution_section,
        time_series=time_series,
        tables={},
        metadata=dict(metadata or {}),
    )

    return _json_safe(payload.to_dict())


def strategy_comparison_dashboard(
    returns_by_strategy: Mapping[str, pd.Series | Sequence[float]],
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    target_return: float = 0.0,
    initial_capital: float = 1.0,
) -> dict[str, Any]:
    table = performance_table(
        returns_by_strategy,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        target_return=target_return,
    )

    charts: dict[str, Any] = {}

    for strategy_name, strategy_returns in returns_by_strategy.items():
        charts[strategy_name] = dashboard_time_series(
            strategy_returns,
            initial_capital=initial_capital,
            periods_per_year=periods_per_year,
        )

    return _json_safe(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "performance_table": dataframe_to_records(
                table,
                include_index=True,
                index_name="strategy",
            ),
            "charts": charts,
        }
    )
