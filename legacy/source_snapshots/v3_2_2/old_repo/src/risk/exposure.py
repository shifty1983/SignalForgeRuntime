from __future__ import annotations

import polars as pl


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def calculate_exposure(
    weights: pl.DataFrame,
    weight_col: str = "weight",
) -> dict[str, float]:
    """
    Calculate total portfolio exposure.

    Returns:
    - long_exposure: sum of positive weights
    - short_exposure: sum of negative weights
    - gross_exposure: sum of absolute weights
    - net_exposure: sum of signed weights
    """

    _require_columns(weights, {weight_col})

    long_exposure = weights.filter(pl.col(weight_col) > 0).select(
        pl.col(weight_col).sum()
    ).item()

    short_exposure = weights.filter(pl.col(weight_col) < 0).select(
        pl.col(weight_col).sum()
    ).item()

    gross_exposure = weights.select(pl.col(weight_col).abs().sum()).item()
    net_exposure = weights.select(pl.col(weight_col).sum()).item()

    return {
        "long_exposure": float(long_exposure or 0.0),
        "short_exposure": float(short_exposure or 0.0),
        "gross_exposure": float(gross_exposure or 0.0),
        "net_exposure": float(net_exposure or 0.0),
    }


def calculate_asset_exposure(
    weights: pl.DataFrame,
    asset_col: str = "symbol",
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Calculate net and gross exposure by asset.
    """

    _require_columns(weights, {asset_col, weight_col})

    return (
        weights.group_by(asset_col)
        .agg(
            pl.col(weight_col).sum().alias("net_exposure"),
            pl.col(weight_col).abs().sum().alias("gross_exposure"),
            pl.col(weight_col).filter(pl.col(weight_col) > 0).sum().alias("long_exposure"),
            pl.col(weight_col).filter(pl.col(weight_col) < 0).sum().alias("short_exposure"),
        )
        .sort(asset_col)
    )


def calculate_group_exposure(
    weights: pl.DataFrame,
    group_col: str,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Calculate exposure by group.

    Useful for:
    - sector exposure
    - asset class exposure
    - country exposure
    - strategy exposure
    """

    _require_columns(weights, {group_col, weight_col})

    return (
        weights.group_by(group_col)
        .agg(
            pl.col(weight_col).sum().alias("net_exposure"),
            pl.col(weight_col).abs().sum().alias("gross_exposure"),
            pl.col(weight_col).filter(pl.col(weight_col) > 0).sum().alias("long_exposure"),
            pl.col(weight_col).filter(pl.col(weight_col) < 0).sum().alias("short_exposure"),
        )
        .sort(group_col)
    )


def calculate_concentration(
    weights: pl.DataFrame,
    weight_col: str = "weight",
) -> dict[str, float]:
    """
    Calculate basic portfolio concentration metrics.

    hhi is the Herfindahl-Hirschman Index using absolute normalized weights.
    Higher values mean more concentration.
    """

    _require_columns(weights, {weight_col})

    gross_exposure = weights.select(pl.col(weight_col).abs().sum()).item()

    if gross_exposure == 0:
        raise ValueError("Gross exposure is zero")

    normalized_abs = weights.with_columns(
        (pl.col(weight_col).abs() / gross_exposure).alias("_abs_weight")
    )

    hhi = normalized_abs.select((pl.col("_abs_weight") ** 2).sum()).item()
    max_weight = weights.select(pl.col(weight_col).abs().max()).item()
    position_count = weights.height

    effective_positions = 1.0 / hhi if hhi > 0 else 0.0

    return {
        "hhi": float(hhi),
        "effective_positions": float(effective_positions),
        "max_abs_weight": float(max_weight or 0.0),
        "position_count": float(position_count),
    }


def add_exposure_flags(
    weights: pl.DataFrame,
    max_position_weight: float = 0.10,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Add position-level exposure flags.
    """

    _require_columns(weights, {weight_col})

    return weights.with_columns(
        (pl.col(weight_col).abs() > max_position_weight).alias("exceeds_position_limit")
    )


def calculate_beta_exposure(
    weights: pl.DataFrame,
    beta_col: str = "beta",
    weight_col: str = "weight",
) -> float:
    """
    Calculate portfolio beta exposure.

    Formula:
    sum(weight * beta)
    """

    _require_columns(weights, {weight_col, beta_col})

    beta_exposure = weights.select(
        (pl.col(weight_col) * pl.col(beta_col)).sum()
    ).item()

    return float(beta_exposure or 0.0)
