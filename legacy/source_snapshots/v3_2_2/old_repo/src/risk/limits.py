from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class RiskLimitConfig:
    """
    Central configuration object for portfolio risk limits.
    """

    max_position_weight: float = 0.10
    max_gross_exposure: float = 1.00
    max_net_exposure: float = 0.50
    max_group_exposure: float = 0.30
    max_beta_exposure: float = 1.00
    max_portfolio_volatility: float = 0.20
    max_drawdown: float = 0.15


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def _safe_float(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def check_position_limits(
    weights: pl.DataFrame,
    max_position_weight: float = 0.10,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Flag individual positions whose absolute weight exceeds the limit.
    """

    _require_columns(weights, {weight_col})

    if max_position_weight <= 0:
        raise ValueError("max_position_weight must be positive")

    return weights.with_columns(
        pl.col(weight_col).abs().alias("abs_weight"),
        (pl.col(weight_col).abs() > max_position_weight).alias(
            "position_limit_breach"
        ),
    )


def check_leverage_limit(
    weights: pl.DataFrame,
    max_gross_exposure: float = 1.0,
    weight_col: str = "weight",
) -> dict[str, float | bool]:
    """
    Check whether total gross exposure is within the leverage limit.
    """

    _require_columns(weights, {weight_col})

    if max_gross_exposure <= 0:
        raise ValueError("max_gross_exposure must be positive")

    gross_exposure = _safe_float(
        weights.select(pl.col(weight_col).abs().sum()).item()
    )

    return {
        "gross_exposure": gross_exposure,
        "max_gross_exposure": float(max_gross_exposure),
        "within_limit": gross_exposure <= max_gross_exposure,
        "breach": gross_exposure > max_gross_exposure,
    }


def check_net_exposure_limit(
    weights: pl.DataFrame,
    max_net_exposure: float = 0.50,
    weight_col: str = "weight",
) -> dict[str, float | bool]:
    """
    Check whether absolute net exposure is within the allowed limit.
    """

    _require_columns(weights, {weight_col})

    if max_net_exposure < 0:
        raise ValueError("max_net_exposure cannot be negative")

    net_exposure = _safe_float(
        weights.select(pl.col(weight_col).sum()).item()
    )

    return {
        "net_exposure": net_exposure,
        "max_net_exposure": float(max_net_exposure),
        "within_limit": abs(net_exposure) <= max_net_exposure,
        "breach": abs(net_exposure) > max_net_exposure,
    }


def check_group_limit(
    weights: pl.DataFrame,
    group_col: str,
    max_group_exposure: float = 0.30,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Check exposure limits by group.

    Examples:
    - sector
    - country
    - asset_class
    - strategy
    """

    _require_columns(weights, {group_col, weight_col})

    if max_group_exposure <= 0:
        raise ValueError("max_group_exposure must be positive")

    grouped = (
        weights.group_by(group_col)
        .agg(
            pl.col(weight_col).sum().alias("net_exposure"),
            pl.col(weight_col).abs().sum().alias("gross_exposure"),
            pl.col(weight_col)
            .filter(pl.col(weight_col) > 0)
            .sum()
            .alias("long_exposure"),
            pl.col(weight_col)
            .filter(pl.col(weight_col) < 0)
            .sum()
            .alias("short_exposure"),
        )
        .sort(group_col)
    )

    return grouped.with_columns(
        (pl.col("gross_exposure") > max_group_exposure).alias(
            "group_limit_breach"
        )
    )


def check_beta_limit(
    weights: pl.DataFrame,
    max_beta_exposure: float = 1.0,
    beta_col: str = "beta",
    weight_col: str = "weight",
) -> dict[str, float | bool]:
    """
    Check portfolio beta exposure against a max absolute beta limit.
    """

    _require_columns(weights, {weight_col, beta_col})

    if max_beta_exposure < 0:
        raise ValueError("max_beta_exposure cannot be negative")

    beta_exposure = _safe_float(
        weights.select((pl.col(weight_col) * pl.col(beta_col)).sum()).item()
    )

    return {
        "beta_exposure": beta_exposure,
        "max_beta_exposure": float(max_beta_exposure),
        "within_limit": abs(beta_exposure) <= max_beta_exposure,
        "breach": abs(beta_exposure) > max_beta_exposure,
    }


def check_portfolio_volatility_limit(
    portfolio_volatility: float,
    max_portfolio_volatility: float = 0.20,
) -> dict[str, float | bool]:
    """
    Check portfolio volatility against a max volatility threshold.
    """

    if portfolio_volatility < 0:
        raise ValueError("portfolio_volatility cannot be negative")

    if max_portfolio_volatility <= 0:
        raise ValueError("max_portfolio_volatility must be positive")

    return {
        "portfolio_volatility": float(portfolio_volatility),
        "max_portfolio_volatility": float(max_portfolio_volatility),
        "within_limit": portfolio_volatility <= max_portfolio_volatility,
        "breach": portfolio_volatility > max_portfolio_volatility,
    }


def generate_limit_report(
    weights: pl.DataFrame,
    config: RiskLimitConfig | None = None,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Generate a compact risk limit report for portfolio-level limits.
    """

    _require_columns(weights, {weight_col})

    if config is None:
        config = RiskLimitConfig()

    leverage = check_leverage_limit(
        weights=weights,
        max_gross_exposure=config.max_gross_exposure,
        weight_col=weight_col,
    )

    net = check_net_exposure_limit(
        weights=weights,
        max_net_exposure=config.max_net_exposure,
        weight_col=weight_col,
    )

    max_abs_position = _safe_float(
        weights.select(pl.col(weight_col).abs().max()).item()
    )

    position_breach = max_abs_position > config.max_position_weight

    return pl.DataFrame(
        {
            "limit": [
                "max_position_weight",
                "max_gross_exposure",
                "max_net_exposure",
            ],
            "value": [
                max_abs_position,
                leverage["gross_exposure"],
                abs(net["net_exposure"]),
            ],
            "threshold": [
                config.max_position_weight,
                config.max_gross_exposure,
                config.max_net_exposure,
            ],
            "within_limit": [
                not position_breach,
                leverage["within_limit"],
                net["within_limit"],
            ],
            "breach": [
                position_breach,
                leverage["breach"],
                net["breach"],
            ],
        }
    )
