from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


_EPSILON = 1e-12


@dataclass(frozen=True)
class AttributionSummary:
    total_portfolio_return: float
    explained_return: float
    unexplained_return: float
    number_of_contributors: int
    positive_contributors: int
    negative_contributors: int
    top_contributor: str | None
    bottom_contributor: str | None
    top_contribution: float
    bottom_contribution: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_frame(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    if isinstance(attribution, pd.DataFrame):
        return attribution.copy()

    return pd.DataFrame(list(attribution))


def _safe_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _to_series(
    data: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float],
    *,
    value_col: str | None = None,
    date_col: str | None = None,
    name: str = "portfolio_return",
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


def normalize_attribution(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    date_col: str = "date",
    symbol_col: str = "symbol",
    asset_class_col: str = "asset_class",
    sector_col: str = "sector",
    strategy_col: str = "strategy",
    weight_col: str = "weight",
    asset_return_col: str = "asset_return",
    contribution_col: str | None = None,
    portfolio_return_col: str | None = None,
) -> pd.DataFrame:
    frame = _to_frame(attribution)

    if frame.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "symbol",
                "asset_class",
                "sector",
                "strategy",
                "weight",
                "asset_return",
                "contribution",
                "abs_contribution",
                "portfolio_return",
            ]
        )

    normalized = pd.DataFrame(index=frame.index)

    normalized["date"] = (
        pd.to_datetime(frame[date_col], errors="coerce")
        if date_col in frame.columns
        else pd.NaT
    )

    normalized["symbol"] = (
        frame[symbol_col].astype(str)
        if symbol_col in frame.columns
        else "UNKNOWN"
    )

    normalized["asset_class"] = (
        frame[asset_class_col].astype(str)
        if asset_class_col in frame.columns
        else "UNKNOWN"
    )

    normalized["sector"] = (
        frame[sector_col].astype(str)
        if sector_col in frame.columns
        else "UNKNOWN"
    )

    normalized["strategy"] = (
        frame[strategy_col].astype(str)
        if strategy_col in frame.columns
        else "UNKNOWN"
    )

    normalized["weight"] = (
        _safe_numeric(frame[weight_col], default=0.0)
        if weight_col in frame.columns
        else 0.0
    )

    effective_return_col = asset_return_col

    if effective_return_col not in frame.columns and "return" in frame.columns:
        effective_return_col = "return"

    normalized["asset_return"] = (
        _safe_numeric(frame[effective_return_col], default=0.0)
        if effective_return_col in frame.columns
        else 0.0
    )

    effective_contribution_col = contribution_col

    if effective_contribution_col is None and "contribution" in frame.columns:
        effective_contribution_col = "contribution"

    if effective_contribution_col is not None and effective_contribution_col in frame.columns:
        normalized["contribution"] = _safe_numeric(
            frame[effective_contribution_col],
            default=0.0,
        )
    else:
        if weight_col not in frame.columns or effective_return_col not in frame.columns:
            raise ValueError(
                "Either contribution_col, a 'contribution' column, or both weight and return columns must be provided."
            )

        normalized["contribution"] = (
            normalized["weight"] * normalized["asset_return"]
        )

    normalized["abs_contribution"] = normalized["contribution"].abs()

    if portfolio_return_col is not None and portfolio_return_col in frame.columns:
        normalized["portfolio_return"] = _safe_numeric(
            frame[portfolio_return_col],
            default=np.nan,
        )
    elif "portfolio_return" in frame.columns:
        normalized["portfolio_return"] = _safe_numeric(
            frame["portfolio_return"],
            default=np.nan,
        )
    else:
        normalized["portfolio_return"] = np.nan

    return normalized.reset_index(drop=True)


def group_attribution(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    group_col: str = "symbol",
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_attribution(attribution, **normalize_kwargs)

    if normalized.empty:
        return pd.DataFrame()

    if group_col not in normalized.columns:
        raise ValueError(f"group_col '{group_col}' not found in attribution data.")

    grouped = normalized.groupby(group_col, dropna=False)

    table = grouped.agg(
        number_of_rows=("contribution", "count"),
        total_contribution=("contribution", "sum"),
        average_contribution=("contribution", "mean"),
        contribution_volatility=("contribution", "std"),
        positive_periods=("contribution", lambda x: int((x > 0.0).sum())),
        negative_periods=("contribution", lambda x: int((x < 0.0).sum())),
    )

    table["contribution_volatility"] = table["contribution_volatility"].fillna(0.0)

    table["hit_rate"] = np.where(
        table["number_of_rows"] > 0,
        table["positive_periods"] / table["number_of_rows"],
        0.0,
    )

    gross_total = float(table["total_contribution"].abs().sum())

    table["contribution_share"] = (
        table["total_contribution"] / gross_total
        if gross_total > _EPSILON
        else 0.0
    )

    return table.sort_values("total_contribution", ascending=False)


def symbol_attribution(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    return group_attribution(
        attribution,
        group_col="symbol",
        **normalize_kwargs,
    )


def asset_class_attribution(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    return group_attribution(
        attribution,
        group_col="asset_class",
        **normalize_kwargs,
    )


def sector_attribution(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    return group_attribution(
        attribution,
        group_col="sector",
        **normalize_kwargs,
    )


def strategy_attribution(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    return group_attribution(
        attribution,
        group_col="strategy",
        **normalize_kwargs,
    )


def period_attribution(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    date_col: str = "date",
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_attribution(
        attribution,
        date_col=date_col,
        **normalize_kwargs,
    )

    if normalized.empty:
        return pd.DataFrame()

    if normalized["date"].isna().all():
        raise ValueError("date column is required for period attribution.")

    grouped = normalized.groupby("date", dropna=False)

    table = grouped.agg(
        total_contribution=("contribution", "sum"),
        gross_contribution=("abs_contribution", "sum"),
        number_of_contributors=("symbol", "count"),
        positive_contributors=("contribution", lambda x: int((x > 0.0).sum())),
        negative_contributors=("contribution", lambda x: int((x < 0.0).sum())),
        portfolio_return=("portfolio_return", "mean"),
    )

    table["unexplained_return"] = (
        table["portfolio_return"] - table["total_contribution"]
    )

    return table.sort_index()


def attribution_summary(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    portfolio_returns: pd.Series | pd.DataFrame | Mapping[Any, Any] | Sequence[float] | None = None,
    group_col: str = "symbol",
    portfolio_return_value_col: str | None = None,
    portfolio_return_date_col: str | None = None,
    **normalize_kwargs: Any,
) -> AttributionSummary:
    normalized = normalize_attribution(attribution, **normalize_kwargs)

    if normalized.empty:
        return AttributionSummary(
            total_portfolio_return=0.0,
            explained_return=0.0,
            unexplained_return=0.0,
            number_of_contributors=0,
            positive_contributors=0,
            negative_contributors=0,
            top_contributor=None,
            bottom_contributor=None,
            top_contribution=0.0,
            bottom_contribution=0.0,
        )

    grouped = group_attribution(
        normalized,
        group_col=group_col,
        contribution_col="contribution",
    )

    explained_return = float(normalized["contribution"].sum())

    if portfolio_returns is not None:
        portfolio_return_series = _to_series(
            portfolio_returns,
            value_col=portfolio_return_value_col,
            date_col=portfolio_return_date_col,
            name="portfolio_return",
        )
        total_portfolio_return = float(portfolio_return_series.sum())
    elif normalized["portfolio_return"].notna().any():
        total_portfolio_return = float(
            normalized.drop_duplicates("date")["portfolio_return"].sum()
        )
    else:
        total_portfolio_return = explained_return

    unexplained_return = total_portfolio_return - explained_return

    top_contributor = str(grouped.index[0]) if not grouped.empty else None
    bottom_contributor = str(grouped.index[-1]) if not grouped.empty else None

    top_contribution = (
        float(grouped.iloc[0]["total_contribution"])
        if not grouped.empty
        else 0.0
    )

    bottom_contribution = (
        float(grouped.iloc[-1]["total_contribution"])
        if not grouped.empty
        else 0.0
    )

    positive_contributors = int((grouped["total_contribution"] > 0.0).sum())
    negative_contributors = int((grouped["total_contribution"] < 0.0).sum())

    return AttributionSummary(
        total_portfolio_return=total_portfolio_return,
        explained_return=explained_return,
        unexplained_return=unexplained_return,
        number_of_contributors=int(len(grouped)),
        positive_contributors=positive_contributors,
        negative_contributors=negative_contributors,
        top_contributor=top_contributor,
        bottom_contributor=bottom_contributor,
        top_contribution=top_contribution,
        bottom_contribution=bottom_contribution,
    )


def contribution_matrix(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    index_col: str = "date",
    columns_col: str = "symbol",
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_attribution(attribution, **normalize_kwargs)

    if normalized.empty:
        return pd.DataFrame()

    if index_col not in normalized.columns:
        raise ValueError(f"index_col '{index_col}' not found in attribution data.")

    if columns_col not in normalized.columns:
        raise ValueError(f"columns_col '{columns_col}' not found in attribution data.")

    matrix = normalized.pivot_table(
        index=index_col,
        columns=columns_col,
        values="contribution",
        aggfunc="sum",
        fill_value=0.0,
    )

    return matrix.sort_index()


def top_contributors(
    attribution: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    n: int = 10,
    group_col: str = "symbol",
    largest: bool = True,
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    if n <= 0:
        raise ValueError("n must be greater than zero.")

    table = group_attribution(
        attribution,
        group_col=group_col,
        **normalize_kwargs,
    )

    if table.empty:
        return table

    if largest:
        return table.sort_values("total_contribution", ascending=False).head(n)

    return table.sort_values("total_contribution", ascending=True).head(n)
