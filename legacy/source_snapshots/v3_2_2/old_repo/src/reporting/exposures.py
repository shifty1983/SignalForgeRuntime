from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


_EPSILON = 1e-12

GREEK_COLUMNS = ["delta", "gamma", "theta", "vega", "rho"]


@dataclass(frozen=True)
class ExposureSummary:
    number_of_positions: int
    gross_exposure: float
    net_exposure: float
    long_exposure: float
    short_exposure: float
    cash_weight: float
    largest_long_weight: float
    largest_short_weight: float
    top_position_weight: float
    concentration_hhi: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    net_rho: float
    gross_delta: float
    gross_gamma: float
    gross_theta: float
    gross_vega: float
    gross_rho: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_frame(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    if isinstance(positions, pd.DataFrame):
        return positions.copy()

    return pd.DataFrame(list(positions))


def _safe_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _side_to_direction(side: Any) -> float:
    if pd.isna(side):
        return 1.0

    if isinstance(side, (int, float, np.integer, np.floating)):
        if side > 0:
            return 1.0
        if side < 0:
            return -1.0
        return 1.0

    normalized = str(side).strip().lower()

    if normalized in {"long", "buy", "b", "bullish", "1"}:
        return 1.0

    if normalized in {"short", "sell", "s", "bearish", "-1"}:
        return -1.0

    return 1.0


def normalize_exposures(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    symbol_col: str = "symbol",
    asset_class_col: str = "asset_class",
    sector_col: str = "sector",
    strategy_col: str = "strategy",
    side_col: str = "side",
    quantity_col: str = "quantity",
    price_col: str = "price",
    multiplier_col: str = "multiplier",
    market_value_col: str | None = None,
    weight_col: str | None = None,
    portfolio_value: float | None = None,
) -> pd.DataFrame:
    frame = _to_frame(positions)

    if frame.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "asset_class",
                "sector",
                "strategy",
                "side",
                "direction",
                "quantity",
                "price",
                "multiplier",
                "market_value",
                "weight",
                "abs_weight",
                "is_long",
                "is_short",
                *GREEK_COLUMNS,
            ]
        )

    normalized = pd.DataFrame(index=frame.index)

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

    normalized["side"] = (
        frame[side_col].astype(str)
        if side_col in frame.columns
        else "long"
    )

    normalized["direction"] = (
        frame[side_col].map(_side_to_direction)
        if side_col in frame.columns
        else 1.0
    )

    normalized["quantity"] = (
        _safe_numeric(frame[quantity_col], default=np.nan)
        if quantity_col in frame.columns
        else np.nan
    )

    normalized["price"] = (
        _safe_numeric(frame[price_col], default=np.nan)
        if price_col in frame.columns
        else np.nan
    )

    normalized["multiplier"] = (
        _safe_numeric(frame[multiplier_col], default=1.0)
        if multiplier_col in frame.columns
        else 1.0
    )

    if market_value_col is not None and market_value_col in frame.columns:
        normalized["market_value"] = _safe_numeric(
            frame[market_value_col],
            default=np.nan,
        )
    else:
        can_derive_market_value = normalized[
            ["quantity", "price", "multiplier"]
        ].notna().all(axis=1)

        derived_market_value = (
            normalized["quantity"].abs()
            * normalized["price"]
            * normalized["multiplier"]
            * normalized["direction"]
        )

        normalized["market_value"] = np.where(
            can_derive_market_value,
            derived_market_value,
            np.nan,
        )

    if weight_col is not None and weight_col in frame.columns:
        normalized["weight"] = _safe_numeric(frame[weight_col], default=0.0)
    else:
        if portfolio_value is None:
            gross_market_value = normalized["market_value"].abs().sum()
            portfolio_value = (
                float(gross_market_value)
                if gross_market_value > _EPSILON
                else 1.0
            )

        if portfolio_value <= 0:
            raise ValueError("portfolio_value must be greater than zero.")

        normalized["weight"] = normalized["market_value"] / portfolio_value

    normalized["abs_weight"] = normalized["weight"].abs()
    normalized["is_long"] = normalized["weight"] > 0.0
    normalized["is_short"] = normalized["weight"] < 0.0

    for greek in GREEK_COLUMNS:
        if greek in frame.columns:
            normalized[greek] = _safe_numeric(frame[greek], default=0.0)
        else:
            normalized[greek] = 0.0

    return normalized.reset_index(drop=True)


def summarize_exposures(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> ExposureSummary:
    normalized = normalize_exposures(positions, **normalize_kwargs)

    if normalized.empty:
        return ExposureSummary(
            number_of_positions=0,
            gross_exposure=0.0,
            net_exposure=0.0,
            long_exposure=0.0,
            short_exposure=0.0,
            cash_weight=1.0,
            largest_long_weight=0.0,
            largest_short_weight=0.0,
            top_position_weight=0.0,
            concentration_hhi=0.0,
            net_delta=0.0,
            net_gamma=0.0,
            net_theta=0.0,
            net_vega=0.0,
            net_rho=0.0,
            gross_delta=0.0,
            gross_gamma=0.0,
            gross_theta=0.0,
            gross_vega=0.0,
            gross_rho=0.0,
        )

    weights = normalized["weight"]
    abs_weights = normalized["abs_weight"]

    gross_exposure = float(abs_weights.sum())
    net_exposure = float(weights.sum())
    long_exposure = float(weights[weights > 0.0].sum())
    short_exposure = float(abs(weights[weights < 0.0].sum()))
    cash_weight = float(1.0 - net_exposure)

    if gross_exposure > _EPSILON:
        concentration_hhi = float(((abs_weights / gross_exposure) ** 2).sum())
    else:
        concentration_hhi = 0.0

    greek_values: dict[str, float] = {}

    for greek in GREEK_COLUMNS:
        values = normalized[greek]
        greek_values[f"net_{greek}"] = float(values.sum())
        greek_values[f"gross_{greek}"] = float(values.abs().sum())

    long_weights = weights[weights > 0.0]
    short_weights = weights[weights < 0.0]

    return ExposureSummary(
        number_of_positions=int(len(normalized)),
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        long_exposure=long_exposure,
        short_exposure=short_exposure,
        cash_weight=cash_weight,
        largest_long_weight=float(long_weights.max()) if not long_weights.empty else 0.0,
        largest_short_weight=float(short_weights.min()) if not short_weights.empty else 0.0,
        top_position_weight=float(abs_weights.max()) if not abs_weights.empty else 0.0,
        concentration_hhi=concentration_hhi,
        net_delta=greek_values["net_delta"],
        net_gamma=greek_values["net_gamma"],
        net_theta=greek_values["net_theta"],
        net_vega=greek_values["net_vega"],
        net_rho=greek_values["net_rho"],
        gross_delta=greek_values["gross_delta"],
        gross_gamma=greek_values["gross_gamma"],
        gross_theta=greek_values["gross_theta"],
        gross_vega=greek_values["gross_vega"],
        gross_rho=greek_values["gross_rho"],
    )


def exposure_by_group(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    group_col: str,
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_exposures(positions, **normalize_kwargs)

    if normalized.empty:
        return pd.DataFrame()

    if group_col not in normalized.columns:
        raise ValueError(f"group_col '{group_col}' not found in normalized exposures.")

    grouped = normalized.groupby(group_col, dropna=False)

    table = grouped.agg(
        number_of_positions=("symbol", "count"),
        net_exposure=("weight", "sum"),
        gross_exposure=("abs_weight", "sum"),
        long_exposure=("weight", lambda x: float(x[x > 0.0].sum())),
        short_exposure=("weight", lambda x: float(abs(x[x < 0.0].sum()))),
        net_delta=("delta", "sum"),
        net_gamma=("gamma", "sum"),
        net_theta=("theta", "sum"),
        net_vega=("vega", "sum"),
        net_rho=("rho", "sum"),
    )

    return table.sort_index()


def asset_class_exposure(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    return exposure_by_group(
        positions,
        group_col="asset_class",
        **normalize_kwargs,
    )


def sector_exposure(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    return exposure_by_group(
        positions,
        group_col="sector",
        **normalize_kwargs,
    )


def strategy_exposure(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    return exposure_by_group(
        positions,
        group_col="strategy",
        **normalize_kwargs,
    )


def greek_exposure(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_exposures(positions, **normalize_kwargs)

    if normalized.empty:
        return pd.DataFrame(
            columns=[
                "net",
                "gross",
                "long_book",
                "short_book",
            ],
            index=GREEK_COLUMNS,
        )

    rows: list[dict[str, Any]] = []

    for greek in GREEK_COLUMNS:
        values = normalized[greek]
        long_values = normalized.loc[normalized["is_long"], greek]
        short_values = normalized.loc[normalized["is_short"], greek]

        rows.append(
            {
                "greek": greek,
                "net": float(values.sum()),
                "gross": float(values.abs().sum()),
                "long_book": float(long_values.sum()),
                "short_book": float(short_values.sum()),
            }
        )

    return pd.DataFrame(rows).set_index("greek")


def top_positions(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    n: int = 10,
    by: str = "abs_weight",
    ascending: bool = False,
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    if n <= 0:
        raise ValueError("n must be greater than zero.")

    normalized = normalize_exposures(positions, **normalize_kwargs)

    if normalized.empty:
        return normalized

    if by not in normalized.columns:
        raise ValueError(f"Column '{by}' not found in normalized exposures.")

    return normalized.sort_values(by=by, ascending=ascending).head(n).reset_index(drop=True)


def exposure_snapshot(
    positions: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> dict[str, Any]:
    normalized = normalize_exposures(positions, **normalize_kwargs)

    return {
        "summary": summarize_exposures(
            normalized,
            weight_col="weight",
        ).to_dict(),
        "positions": normalized.to_dict(orient="records"),
        "asset_class_exposure": asset_class_exposure(
            normalized,
            weight_col="weight",
        ).to_dict(orient="index"),
        "sector_exposure": sector_exposure(
            normalized,
            weight_col="weight",
        ).to_dict(orient="index"),
        "strategy_exposure": strategy_exposure(
            normalized,
            weight_col="weight",
        ).to_dict(orient="index"),
        "greek_exposure": greek_exposure(
            normalized,
            weight_col="weight",
        ).to_dict(orient="index"),
    }
