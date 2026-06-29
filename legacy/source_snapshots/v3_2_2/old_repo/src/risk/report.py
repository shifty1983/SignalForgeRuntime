from __future__ import annotations

import numpy as np
import polars as pl

from src.risk.drawdown import drawdown_summary
from src.risk.exposure import (
    calculate_beta_exposure,
    calculate_concentration,
    calculate_exposure,
    calculate_group_exposure,
)
from src.risk.greeks import (
    GreekLimitConfig,
    build_greek_risk_report,
)
from src.risk.limits import (
    RiskLimitConfig,
    check_beta_limit,
    check_group_limit,
    check_portfolio_volatility_limit,
    generate_limit_report,
)
from src.risk.stress import scenario_stress_test, stress_summary
from src.risk.volatility import (
    calculate_portfolio_volatility,
    calculate_risk_contribution,
)


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def build_risk_snapshot(
    weights: pl.DataFrame,
    config: RiskLimitConfig | None = None,
    weight_col: str = "weight",
    beta_col: str | None = None,
) -> dict[str, float | int | bool]:
    """
    Build a compact portfolio-level risk snapshot.
    """

    _require_columns(weights, {weight_col})

    if config is None:
        config = RiskLimitConfig()

    exposure = calculate_exposure(weights, weight_col=weight_col)
    concentration = calculate_concentration(weights, weight_col=weight_col)

    limit_report = generate_limit_report(
        weights=weights,
        config=config,
        weight_col=weight_col,
    )

    breach_count = limit_report.filter(pl.col("breach")).height

    snapshot: dict[str, float | int | bool] = {
        **exposure,
        **concentration,
        "limit_breach_count": int(breach_count),
        "has_limit_breach": breach_count > 0,
    }

    if beta_col is not None and beta_col in weights.columns:
        beta_exposure = calculate_beta_exposure(
            weights,
            beta_col=beta_col,
            weight_col=weight_col,
        )

        beta_limit = check_beta_limit(
            weights,
            max_beta_exposure=config.max_beta_exposure,
            beta_col=beta_col,
            weight_col=weight_col,
        )

        snapshot["beta_exposure"] = beta_exposure
        snapshot["beta_limit_breach"] = bool(beta_limit["breach"])

    return snapshot


def build_options_risk_snapshot(
    positions: pl.DataFrame,
    greek_config: GreekLimitConfig | None = None,
    symbol_col: str = "symbol",
) -> dict[str, object]:
    """
    Build compact options-specific Greek risk snapshot.
    """

    greek_report = build_greek_risk_report(
        positions=positions,
        config=greek_config,
        symbol_col=symbol_col,
    )

    portfolio_exposure = greek_report["portfolio_exposure"]

    return {
        **portfolio_exposure,
        "greek_breach_count": greek_report["breach_count"],
        "has_greek_breach": greek_report["has_breach"],
        "greek_limit_report": greek_report["limit_report"],
        "greek_symbol_exposure": greek_report["symbol_exposure"],
    }


def build_group_risk_report(
    weights: pl.DataFrame,
    group_col: str,
    config: RiskLimitConfig | None = None,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Build group-level exposure and limit report.
    """

    if config is None:
        config = RiskLimitConfig()

    exposure = calculate_group_exposure(
        weights,
        group_col=group_col,
        weight_col=weight_col,
    )

    limits = check_group_limit(
        weights,
        group_col=group_col,
        max_group_exposure=config.max_group_exposure,
        weight_col=weight_col,
    ).select(group_col, "group_limit_breach")

    return exposure.join(limits, on=group_col, how="left").sort(group_col)


def build_volatility_risk_report(
    weights: np.ndarray,
    covariance_matrix: np.ndarray,
    symbols: list[str],
    config: RiskLimitConfig | None = None,
    covariance_is_annualized: bool = True,
) -> dict[str, object]:
    """
    Build volatility and risk contribution report.
    """

    if config is None:
        config = RiskLimitConfig()

    portfolio_volatility = calculate_portfolio_volatility(
        weights=weights,
        covariance_matrix=covariance_matrix,
        covariance_is_annualized=covariance_is_annualized,
    )

    volatility_limit = check_portfolio_volatility_limit(
        portfolio_volatility=portfolio_volatility,
        max_portfolio_volatility=config.max_portfolio_volatility,
    )

    risk_contribution = calculate_risk_contribution(
        weights=weights,
        covariance_matrix=covariance_matrix,
        symbols=symbols,
    )

    return {
        "portfolio_volatility": portfolio_volatility,
        "volatility_limit": volatility_limit,
        "risk_contribution": risk_contribution,
    }


def build_drawdown_risk_report(
    equity: pl.DataFrame,
    equity_col: str = "equity",
) -> dict[str, float | int]:
    """
    Build drawdown risk summary from an equity curve.
    """

    return drawdown_summary(equity, equity_col=equity_col)


def build_stress_risk_report(
    weights: pl.DataFrame,
    scenarios: pl.DataFrame,
    symbol_col: str = "symbol",
    scenario_col: str = "scenario",
    weight_col: str = "weight",
    shock_col: str = "shock",
) -> dict[str, object]:
    """
    Build scenario stress test report.
    """

    results = scenario_stress_test(
        weights=weights,
        scenarios=scenarios,
        symbol_col=symbol_col,
        scenario_col=scenario_col,
        weight_col=weight_col,
        shock_col=shock_col,
    )

    summary = stress_summary(
        results,
        scenario_col=scenario_col,
        pnl_col="portfolio_pnl",
    )

    return {
        "stress_results": results,
        "stress_summary": summary,
    }


def build_combined_risk_report(
    weights: pl.DataFrame,
    config: RiskLimitConfig | None = None,
    options_positions: pl.DataFrame | None = None,
    greek_config: GreekLimitConfig | None = None,
    group_col: str | None = None,
    beta_col: str | None = None,
    weight_col: str = "weight",
) -> dict[str, object]:
    """
    Build a unified risk report.

    Includes:
    - portfolio exposure snapshot
    - optional group risk report
    - optional beta exposure
    - optional options Greek risk
    """

    report: dict[str, object] = {
        "portfolio_snapshot": build_risk_snapshot(
            weights=weights,
            config=config,
            weight_col=weight_col,
            beta_col=beta_col,
        )
    }

    if group_col is not None and group_col in weights.columns:
        report["group_risk"] = build_group_risk_report(
            weights=weights,
            group_col=group_col,
            config=config,
            weight_col=weight_col,
        )

    if options_positions is not None:
        report["options_risk"] = build_options_risk_snapshot(
            positions=options_positions,
            greek_config=greek_config,
        )

    return report
