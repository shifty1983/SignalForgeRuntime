from __future__ import annotations

import polars as pl


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def apply_symbol_shocks(
    weights: pl.DataFrame,
    shocks: pl.DataFrame,
    symbol_col: str = "symbol",
    weight_col: str = "weight",
    shock_col: str = "shock",
) -> pl.DataFrame:
    """
    Apply symbol-level return shocks to portfolio weights.

    shock should be expressed as decimal return:
    -0.10 = -10%
     0.05 = +5%
    """

    _require_columns(weights, {symbol_col, weight_col})
    _require_columns(shocks, {symbol_col, shock_col})

    joined = weights.join(shocks, on=symbol_col, how="inner")

    if joined.height != weights.height:
        raise ValueError("Missing shock values for one or more symbols")

    return joined.with_columns(
        (pl.col(weight_col) * pl.col(shock_col)).alias("pnl_contribution")
    )


def portfolio_stress_pnl(
    weights: pl.DataFrame,
    shocks: pl.DataFrame,
    symbol_col: str = "symbol",
    weight_col: str = "weight",
    shock_col: str = "shock",
) -> float:
    """
    Calculate total portfolio return impact from symbol-level shocks.
    """

    shocked = apply_symbol_shocks(
        weights=weights,
        shocks=shocks,
        symbol_col=symbol_col,
        weight_col=weight_col,
        shock_col=shock_col,
    )

    pnl = shocked.select(pl.col("pnl_contribution").sum()).item()

    return float(pnl or 0.0)


def apply_group_shocks(
    weights: pl.DataFrame,
    group_shocks: pl.DataFrame,
    group_col: str,
    weight_col: str = "weight",
    shock_col: str = "shock",
) -> pl.DataFrame:
    """
    Apply group-level shocks.

    Useful for:
    - sector shocks
    - asset class shocks
    - country shocks
    - strategy sleeve shocks
    """

    _require_columns(weights, {group_col, weight_col})
    _require_columns(group_shocks, {group_col, shock_col})

    joined = weights.join(group_shocks, on=group_col, how="inner")

    if joined.height != weights.height:
        raise ValueError("Missing group shock values for one or more rows")

    return joined.with_columns(
        (pl.col(weight_col) * pl.col(shock_col)).alias("pnl_contribution")
    )


def scenario_stress_test(
    weights: pl.DataFrame,
    scenarios: pl.DataFrame,
    symbol_col: str = "symbol",
    scenario_col: str = "scenario",
    weight_col: str = "weight",
    shock_col: str = "shock",
) -> pl.DataFrame:
    """
    Run multiple symbol-level stress scenarios.

    Expected scenario columns:
    - scenario
    - symbol
    - shock
    """

    _require_columns(weights, {symbol_col, weight_col})
    _require_columns(scenarios, {scenario_col, symbol_col, shock_col})

    joined = weights.join(scenarios, on=symbol_col, how="inner")

    expected_rows = weights.height * scenarios.select(scenario_col).n_unique()

    if joined.height != expected_rows:
        raise ValueError("Each scenario must include shocks for every symbol")

    return (
        joined.with_columns(
            (pl.col(weight_col) * pl.col(shock_col)).alias("pnl_contribution")
        )
        .group_by(scenario_col)
        .agg(
            pl.col("pnl_contribution").sum().alias("portfolio_pnl"),
            pl.col("shock_col").count().alias("position_count")
            if "shock_col" in joined.columns
            else pl.col(shock_col).count().alias("position_count"),
        )
        .sort(scenario_col)
    )


def predefined_equity_stress_scenarios(
    symbols: list[str],
) -> pl.DataFrame:
    """
    Create simple default equity stress scenarios for early testing.

    These are not forecasts. They are mechanical portfolio shock tests.
    """

    if len(symbols) == 0:
        raise ValueError("symbols cannot be empty")

    scenario_shocks = {
        "equity_selloff_10": -0.10,
        "equity_selloff_20": -0.20,
        "risk_on_rally_10": 0.10,
    }

    rows = []

    for scenario, shock in scenario_shocks.items():
        for symbol in symbols:
            rows.append(
                {
                    "scenario": scenario,
                    "symbol": symbol,
                    "shock": shock,
                }
            )

    return pl.DataFrame(rows)


def stress_summary(
    stress_results: pl.DataFrame,
    scenario_col: str = "scenario",
    pnl_col: str = "portfolio_pnl",
) -> dict[str, float | str]:
    """
    Summarize stress test results.
    """

    _require_columns(stress_results, {scenario_col, pnl_col})

    worst = stress_results.sort(pnl_col).row(0, named=True)
    best = stress_results.sort(pnl_col, descending=True).row(0, named=True)

    return {
        "worst_scenario": str(worst[scenario_col]),
        "worst_pnl": float(worst[pnl_col]),
        "best_scenario": str(best[scenario_col]),
        "best_pnl": float(best[pnl_col]),
    }
