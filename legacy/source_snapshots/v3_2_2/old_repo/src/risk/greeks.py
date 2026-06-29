from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class GreekLimitConfig:
    """
    Risk limits for option Greek exposure.

    Exposures are portfolio-level signed or absolute values.
    """

    max_abs_delta: float = 1.00
    max_abs_gamma: float = 0.50
    max_abs_theta: float = 0.05
    max_abs_vega: float = 0.50
    max_abs_rho: float = 0.25


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def calculate_position_greek_exposure(
    positions: pl.DataFrame,
    quantity_col: str = "quantity",
    contract_multiplier_col: str = "contract_multiplier",
    delta_col: str = "delta",
    gamma_col: str = "gamma",
    theta_col: str = "theta",
    vega_col: str = "vega",
    rho_col: str = "rho",
) -> pl.DataFrame:
    """
    Calculate position-level Greek exposures.

    Expected columns:
    - quantity
    - contract_multiplier
    - delta
    - gamma
    - theta
    - vega
    - rho

    Exposure formula:
    quantity * contract_multiplier * greek
    """

    required = {
        quantity_col,
        contract_multiplier_col,
        delta_col,
        gamma_col,
        theta_col,
        vega_col,
        rho_col,
    }

    _require_columns(positions, required)

    return positions.with_columns(
        (
            pl.col(quantity_col)
            * pl.col(contract_multiplier_col)
            * pl.col(delta_col)
        ).alias("delta_exposure"),
        (
            pl.col(quantity_col)
            * pl.col(contract_multiplier_col)
            * pl.col(gamma_col)
        ).alias("gamma_exposure"),
        (
            pl.col(quantity_col)
            * pl.col(contract_multiplier_col)
            * pl.col(theta_col)
        ).alias("theta_exposure"),
        (
            pl.col(quantity_col)
            * pl.col(contract_multiplier_col)
            * pl.col(vega_col)
        ).alias("vega_exposure"),
        (
            pl.col(quantity_col)
            * pl.col(contract_multiplier_col)
            * pl.col(rho_col)
        ).alias("rho_exposure"),
    )


def calculate_portfolio_greek_exposure(
    positions: pl.DataFrame,
) -> dict[str, float]:
    """
    Calculate total net and gross Greek exposure.
    """

    greek_cols = {
        "delta_exposure",
        "gamma_exposure",
        "theta_exposure",
        "vega_exposure",
        "rho_exposure",
    }

    if not greek_cols <= set(positions.columns):
        positions = calculate_position_greek_exposure(positions)

    return {
        "net_delta": float(positions.select(pl.col("delta_exposure").sum()).item() or 0.0),
        "gross_delta": float(positions.select(pl.col("delta_exposure").abs().sum()).item() or 0.0),
        "net_gamma": float(positions.select(pl.col("gamma_exposure").sum()).item() or 0.0),
        "gross_gamma": float(positions.select(pl.col("gamma_exposure").abs().sum()).item() or 0.0),
        "net_theta": float(positions.select(pl.col("theta_exposure").sum()).item() or 0.0),
        "gross_theta": float(positions.select(pl.col("theta_exposure").abs().sum()).item() or 0.0),
        "net_vega": float(positions.select(pl.col("vega_exposure").sum()).item() or 0.0),
        "gross_vega": float(positions.select(pl.col("vega_exposure").abs().sum()).item() or 0.0),
        "net_rho": float(positions.select(pl.col("rho_exposure").sum()).item() or 0.0),
        "gross_rho": float(positions.select(pl.col("rho_exposure").abs().sum()).item() or 0.0),
    }


def calculate_greek_exposure_by_symbol(
    positions: pl.DataFrame,
    symbol_col: str = "symbol",
) -> pl.DataFrame:
    """
    Aggregate Greek exposure by underlying symbol.
    """

    _require_columns(positions, {symbol_col})

    greek_cols = {
        "delta_exposure",
        "gamma_exposure",
        "theta_exposure",
        "vega_exposure",
        "rho_exposure",
    }

    if not greek_cols <= set(positions.columns):
        positions = calculate_position_greek_exposure(positions)

    return (
        positions.group_by(symbol_col)
        .agg(
            pl.col("delta_exposure").sum().alias("net_delta"),
            pl.col("delta_exposure").abs().sum().alias("gross_delta"),
            pl.col("gamma_exposure").sum().alias("net_gamma"),
            pl.col("gamma_exposure").abs().sum().alias("gross_gamma"),
            pl.col("theta_exposure").sum().alias("net_theta"),
            pl.col("theta_exposure").abs().sum().alias("gross_theta"),
            pl.col("vega_exposure").sum().alias("net_vega"),
            pl.col("vega_exposure").abs().sum().alias("gross_vega"),
            pl.col("rho_exposure").sum().alias("net_rho"),
            pl.col("rho_exposure").abs().sum().alias("gross_rho"),
        )
        .sort(symbol_col)
    )


def check_greek_limits(
    positions: pl.DataFrame,
    config: GreekLimitConfig | None = None,
) -> pl.DataFrame:
    """
    Check portfolio-level Greek limits.
    """

    if config is None:
        config = GreekLimitConfig()

    exposure = calculate_portfolio_greek_exposure(positions)

    return pl.DataFrame(
        {
            "greek": ["delta", "gamma", "theta", "vega", "rho"],
            "value": [
                abs(exposure["net_delta"]),
                abs(exposure["net_gamma"]),
                abs(exposure["net_theta"]),
                abs(exposure["net_vega"]),
                abs(exposure["net_rho"]),
            ],
            "threshold": [
                config.max_abs_delta,
                config.max_abs_gamma,
                config.max_abs_theta,
                config.max_abs_vega,
                config.max_abs_rho,
            ],
        }
    ).with_columns(
        (pl.col("value") > pl.col("threshold")).alias("breach")
    )


def build_greek_risk_report(
    positions: pl.DataFrame,
    config: GreekLimitConfig | None = None,
    symbol_col: str = "symbol",
) -> dict[str, object]:
    """
    Build a complete Greek risk report.
    """

    position_exposure = calculate_position_greek_exposure(positions)

    portfolio_exposure = calculate_portfolio_greek_exposure(position_exposure)

    symbol_exposure = calculate_greek_exposure_by_symbol(
        position_exposure,
        symbol_col=symbol_col,
    )

    limit_report = check_greek_limits(
        position_exposure,
        config=config,
    )

    breach_count = limit_report.filter(pl.col("breach")).height

    return {
        "position_exposure": position_exposure,
        "portfolio_exposure": portfolio_exposure,
        "symbol_exposure": symbol_exposure,
        "limit_report": limit_report,
        "breach_count": breach_count,
        "has_breach": breach_count > 0,
    }
