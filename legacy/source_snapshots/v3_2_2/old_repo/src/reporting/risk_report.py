from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from src.reporting.exposures import GREEK_COLUMNS, normalize_exposures, summarize_exposures
from src.reporting.performance import max_drawdown_from_returns


_EPSILON = 1e-12


@dataclass(frozen=True)
class ReturnRiskSummary:
    observations: int
    annualized_volatility: float
    downside_volatility: float
    max_drawdown: float
    average_drawdown: float
    value_at_risk: float
    conditional_value_at_risk: float
    worst_return: float
    best_return: float
    average_return: float
    skewness: float
    kurtosis: float
    positive_period_rate: float
    negative_period_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_series(
    data: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
    name: str = "returns",
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


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if not np.isfinite(result):
        return default

    return result


def calculate_value_at_risk(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    confidence_level: float = 0.95,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return 0.0

    tail_probability = 1.0 - confidence_level
    quantile_return = float(series.quantile(tail_probability))

    return float(max(0.0, -quantile_return))


def calculate_conditional_value_at_risk(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    confidence_level: float = 0.95,
    value_col: str | None = None,
    date_col: str | None = None,
) -> float:
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return 0.0

    tail_probability = 1.0 - confidence_level
    threshold = float(series.quantile(tail_probability))
    tail_returns = series[series <= threshold]

    if tail_returns.empty:
        return 0.0

    return float(max(0.0, -tail_returns.mean()))


def downside_volatility(
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
    downside = series[series < periodic_target] - periodic_target

    if len(downside) < 2:
        return 0.0

    return float(downside.std(ddof=1) * np.sqrt(periods_per_year))


def rolling_volatility(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    window: int = 20,
    periods_per_year: int = 252,
    value_col: str | None = None,
    date_col: str | None = None,
) -> pd.Series:
    if window <= 0:
        raise ValueError("window must be greater than zero.")

    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")

    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    result = series.rolling(window=window).std(ddof=1) * np.sqrt(periods_per_year)
    result.name = "rolling_volatility"

    return result


def drawdown_report(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
) -> pd.DataFrame:
    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return pd.DataFrame(
            columns=[
                "returns",
                "equity",
                "running_peak",
                "drawdown",
            ]
        )

    equity = (1.0 + series).cumprod()
    running_peak = equity.cummax().replace(0.0, np.nan)
    drawdown = equity / running_peak - 1.0
    drawdown = drawdown.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    return pd.DataFrame(
        {
            "returns": series,
            "equity": equity,
            "running_peak": running_peak,
            "drawdown": drawdown,
        }
    )


def summarize_return_risk(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    periods_per_year: int = 252,
    confidence_level: float = 0.95,
    target_return: float = 0.0,
    value_col: str | None = None,
    date_col: str | None = None,
) -> ReturnRiskSummary:
    series = _to_series(
        returns,
        value_col=value_col,
        date_col=date_col,
        name="returns",
    )

    if series.empty:
        return ReturnRiskSummary(
            observations=0,
            annualized_volatility=0.0,
            downside_volatility=0.0,
            max_drawdown=0.0,
            average_drawdown=0.0,
            value_at_risk=0.0,
            conditional_value_at_risk=0.0,
            worst_return=0.0,
            best_return=0.0,
            average_return=0.0,
            skewness=0.0,
            kurtosis=0.0,
            positive_period_rate=0.0,
            negative_period_rate=0.0,
        )

    drawdowns = drawdown_report(series)["drawdown"]

    annualized_vol = (
        float(series.std(ddof=1) * np.sqrt(periods_per_year))
        if len(series) >= 2
        else 0.0
    )

    return ReturnRiskSummary(
        observations=int(len(series)),
        annualized_volatility=annualized_vol,
        downside_volatility=downside_volatility(
            series,
            target_return=target_return,
            periods_per_year=periods_per_year,
        ),
        max_drawdown=max_drawdown_from_returns(series),
        average_drawdown=float(drawdowns.mean()) if not drawdowns.empty else 0.0,
        value_at_risk=calculate_value_at_risk(
            series,
            confidence_level=confidence_level,
        ),
        conditional_value_at_risk=calculate_conditional_value_at_risk(
            series,
            confidence_level=confidence_level,
        ),
        worst_return=float(series.min()),
        best_return=float(series.max()),
        average_return=float(series.mean()),
        skewness=_finite_float(series.skew()),
        kurtosis=_finite_float(series.kurtosis()),
        positive_period_rate=float((series > 0.0).mean()),
        negative_period_rate=float((series < 0.0).mean()),
    )


def greek_risk_report(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    limits: Mapping[str, float] | None = None,
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_exposures(positions, **normalize_kwargs)
    limits = dict(limits or {})

    rows: list[dict[str, Any]] = []

    for greek in GREEK_COLUMNS:
        if normalized.empty:
            net_value = 0.0
            gross_value = 0.0
        else:
            values = normalized[greek]
            net_value = float(values.sum())
            gross_value = float(values.abs().sum())

        net_limit = limits.get(f"net_{greek}")
        gross_limit = limits.get(f"gross_{greek}")

        net_limit_breached = (
            abs(net_value) > abs(float(net_limit))
            if net_limit is not None
            else False
        )

        gross_limit_breached = (
            gross_value > abs(float(gross_limit))
            if gross_limit is not None
            else False
        )

        net_utilization = (
            abs(net_value) / abs(float(net_limit))
            if net_limit is not None and abs(float(net_limit)) > _EPSILON
            else 0.0
        )

        gross_utilization = (
            gross_value / abs(float(gross_limit))
            if gross_limit is not None and abs(float(gross_limit)) > _EPSILON
            else 0.0
        )

        rows.append(
            {
                "greek": greek,
                "net": net_value,
                "gross": gross_value,
                "net_limit": net_limit,
                "gross_limit": gross_limit,
                "net_limit_breached": bool(net_limit_breached),
                "gross_limit_breached": bool(gross_limit_breached),
                "net_utilization": float(net_utilization),
                "gross_utilization": float(gross_utilization),
            }
        )

    return pd.DataFrame(rows).set_index("greek")


def risk_limit_breaches(
    metrics: Mapping[str, float],
    limits: Mapping[str, float],
    *,
    absolute: bool = True,
) -> list[dict[str, Any]]:
    breaches: list[dict[str, Any]] = []

    for metric_name, limit_value in limits.items():
        if metric_name not in metrics:
            continue

        value = float(metrics[metric_name])
        limit = float(limit_value)

        comparison_value = abs(value) if absolute else value
        comparison_limit = abs(limit) if absolute else limit

        breached = comparison_value > comparison_limit

        if not breached:
            continue

        breaches.append(
            {
                "metric": metric_name,
                "value": value,
                "limit": limit,
                "breach_amount": comparison_value - comparison_limit,
                "utilization": (
                    comparison_value / comparison_limit
                    if abs(comparison_limit) > _EPSILON
                    else float("inf")
                ),
            }
        )

    return breaches


def portfolio_risk_report(
    returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    positions: pd.DataFrame | Sequence[Mapping[str, Any]] | None = None,
    return_limits: Mapping[str, float] | None = None,
    exposure_limits: Mapping[str, float] | None = None,
    greek_limits: Mapping[str, float] | None = None,
    periods_per_year: int = 252,
    confidence_level: float = 0.95,
    target_return: float = 0.0,
    value_col: str | None = None,
    date_col: str | None = None,
) -> dict[str, Any]:
    return_summary = summarize_return_risk(
        returns,
        periods_per_year=periods_per_year,
        confidence_level=confidence_level,
        target_return=target_return,
        value_col=value_col,
        date_col=date_col,
    )

    return_risk = return_summary.to_dict()
    return_breaches = risk_limit_breaches(
        return_risk,
        return_limits or {},
        absolute=True,
    )

    exposure_risk: dict[str, Any] = {}
    exposure_breaches: list[dict[str, Any]] = []
    greek_risk: dict[str, Any] = {}

    if positions is not None:
        exposure_summary = summarize_exposures(
            positions,
            weight_col="weight",
        )
        exposure_risk = exposure_summary.to_dict()

        exposure_breaches = risk_limit_breaches(
            exposure_risk,
            exposure_limits or {},
            absolute=True,
        )

        greek_table = greek_risk_report(
            positions,
            limits=greek_limits,
            weight_col="weight",
        )
        greek_risk = greek_table.to_dict(orient="index")

    return {
        "return_risk": return_risk,
        "exposure_risk": exposure_risk,
        "greek_risk": greek_risk,
        "limit_breaches": [
            *return_breaches,
            *exposure_breaches,
        ],
    }
