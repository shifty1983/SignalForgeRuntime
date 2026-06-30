from __future__ import annotations

import polars as pl

from src.signalforge.engines.options.schema import (
    normalize_option_type,
    validate_columns,
)


BASE_OPPORTUNITY_COLUMNS = [
    "symbol",
    "expiration",
    "strike",
    "option_type",
    "implied_volatility",
]


OPTIONAL_OPPORTUNITY_COLUMNS = [
    "underlying_price",
    "days_to_expiration",
    "moneyness",
    "mid_price",
    "bid_ask_spread",
    "spread_pct",
    "volume",
    "open_interest",
    "liquidity_score",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "delta_bucket",
    "delta_exposure",
    "gamma_exposure",
    "theta_exposure",
    "vega_exposure",
    "iv_rv_spread",
    "iv_rv_ratio",
    "iv_rv_premium_pct",
    "variance_risk_premium",
    "expected_move",
    "expected_move_pct",
    "vol_premium_regime",
    "skew_regime",
    "term_structure_regime",
]


def build_option_opportunity_inputs(df: pl.DataFrame) -> pl.DataFrame:
    """
    Build the standardized option opportunity input table.

    This table is the handoff from Options Analytics into:
    - Expected Value
    - Strategy Selection
    - Optimizer
    """

    validate_columns(
        df,
        BASE_OPPORTUNITY_COLUMNS,
        "option opportunity inputs",
    )

    result = normalize_option_type(df)

    selected_columns = [
        column
        for column in BASE_OPPORTUNITY_COLUMNS + OPTIONAL_OPPORTUNITY_COLUMNS
        if column in result.columns
    ]

    return result.select(selected_columns)


def _ensure_opportunity_score_columns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add default columns needed for opportunity scoring.

    This keeps scoring flexible when some analytics are not available yet.
    """

    result = df

    numeric_defaults = {
        "iv_rv_spread": 0.0,
        "iv_rv_ratio": 1.0,
        "spread_pct": 0.25,
        "volume": 0.0,
        "open_interest": 0.0,
        "liquidity_score": 0.0,
        "variance_risk_premium": 0.0,
        "expected_move_pct": 0.0,
        "delta": 0.0,
        "gamma": 0.0,
        "theta": 0.0,
        "vega": 0.0,
    }

    string_defaults = {
        "vol_premium_regime": "neutral",
        "skew_regime": "balanced",
        "term_structure_regime": "flat",
    }

    expressions = []

    for column, default in numeric_defaults.items():
        if column not in result.columns:
            expressions.append(pl.lit(default).alias(column))

    for column, default in string_defaults.items():
        if column not in result.columns:
            expressions.append(pl.lit(default).alias(column))

    if expressions:
        result = result.with_columns(expressions)

    return result


def add_opportunity_components(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add component scores used to rank option opportunities.

    Components:
    - short_vol_premium_component
    - long_vol_premium_component
    - liquidity_component
    - variance_premium_component
    - movement_component
    - regime_component
    """

    result = df

    if "option_type" in result.columns:
        result = normalize_option_type(result)

    result = _ensure_opportunity_score_columns(result)

    result = result.with_columns(
        [
            (
                pl.col("iv_rv_spread").fill_null(0.0)
                + (pl.col("iv_rv_ratio").fill_null(1.0) - 1.0)
            ).alias("short_vol_premium_component"),
            (
                -pl.col("iv_rv_spread").fill_null(0.0)
                + (1.0 - pl.col("iv_rv_ratio").fill_null(1.0))
            ).alias("long_vol_premium_component"),
            (
                (pl.col("liquidity_score").fill_null(0.0) / 10.0)
                + (
                    pl.col("volume")
                    .cast(pl.Float64)
                    .fill_null(0.0)
                    .log1p()
                    / 10.0
                )
                + (
                    pl.col("open_interest")
                    .cast(pl.Float64)
                    .fill_null(0.0)
                    .log1p()
                    / 10.0
                )
                - pl.col("spread_pct").fill_null(0.25)
            ).alias("liquidity_component"),
            pl.col("variance_risk_premium")
            .fill_null(0.0)
            .alias("variance_premium_component"),
            pl.col("expected_move_pct")
            .fill_null(0.0)
            .alias("movement_component"),
            (
                pl.col("gamma").abs().fill_null(0.0)
                + pl.col("vega").abs().fill_null(0.0)
                + pl.col("theta").abs().fill_null(0.0)
                + pl.col("delta").abs().fill_null(0.0)
            ).alias("greek_activity_component"),
        ]
    )

    return result.with_columns(
        [
            (
                pl.when(pl.col("vol_premium_regime") == "rich")
                .then(pl.lit(0.25))
                .when(pl.col("vol_premium_regime") == "cheap")
                .then(pl.lit(-0.25))
                .otherwise(pl.lit(0.0))
            ).alias("short_vol_regime_component"),
            (
                pl.when(pl.col("vol_premium_regime") == "cheap")
                .then(pl.lit(0.25))
                .when(pl.col("vol_premium_regime") == "rich")
                .then(pl.lit(-0.25))
                .otherwise(pl.lit(0.0))
            ).alias("long_vol_regime_component"),
            (
                pl.when(pl.col("term_structure_regime") == "contango")
                .then(pl.lit(0.10))
                .when(pl.col("term_structure_regime") == "backwardation")
                .then(pl.lit(-0.10))
                .otherwise(pl.lit(0.0))
            ).alias("term_structure_component"),
            (
                pl.when(pl.col("skew_regime") == "downside_rich")
                .then(pl.lit(0.05))
                .when(pl.col("skew_regime") == "upside_rich")
                .then(pl.lit(0.05))
                .otherwise(pl.lit(0.0))
            ).alias("skew_component"),
        ]
    )


def score_option_opportunities(
    df: pl.DataFrame,
    objective: str = "short_vol",
) -> pl.DataFrame:
    """
    Score option opportunities.

    objective:
    - short_vol: favors rich IV, high liquidity, positive premium
    - long_vol: favors cheap IV, high liquidity, negative premium
    - neutral: favors liquidity and large IV/RV dislocation
    """

    objective = objective.lower()

    if objective not in {"short_vol", "long_vol", "neutral"}:
        raise ValueError(
            "objective must be one of: 'short_vol', 'long_vol', 'neutral'"
        )

    result = add_opportunity_components(df)

    if objective == "short_vol":
        score_expr = (
            (2.0 * pl.col("short_vol_premium_component"))
            + pl.col("liquidity_component")
            + pl.col("variance_premium_component")
            + (0.25 * pl.col("greek_activity_component"))
            + pl.col("short_vol_regime_component")
            + pl.col("term_structure_component")
            + pl.col("skew_component")
        )
    elif objective == "long_vol":
        score_expr = (
            (2.0 * pl.col("short_vol_premium_component"))
            + pl.col("liquidity_component")
            + pl.col("variance_premium_component")
            + (0.25 * pl.col("greek_activity_component"))
            + pl.col("short_vol_regime_component")
            + pl.col("term_structure_component")
            + pl.col("skew_component")
        )
    else:
        score_expr = (
            pl.col("liquidity_component")
            + pl.col("iv_rv_spread").abs().fill_null(0.0)
            + (pl.col("iv_rv_ratio").fill_null(1.0) - 1.0).abs()
            + (0.25 * pl.col("greek_activity_component"))
            + pl.col("skew_component")
        )

    return (
        result.with_columns(score_expr.alias("option_opportunity_score"))
        .sort("option_opportunity_score", descending=True)
    )


def classify_option_opportunities(
    df: pl.DataFrame,
    score_col: str = "option_opportunity_score",
    high_threshold: float = 2.5,
    low_threshold: float = 1.0,
) -> pl.DataFrame:
    """
    Classify opportunity quality.

    Output:
    - high
    - medium
    - low
    """

    validate_columns(
        df,
        [score_col],
        "option opportunity classification",
    )

    return df.with_columns(
        pl.when(pl.col(score_col) >= high_threshold)
        .then(pl.lit("high"))
        .when(pl.col(score_col) <= low_threshold)
        .then(pl.lit("low"))
        .otherwise(pl.lit("medium"))
        .alias("option_opportunity_quality")
    )


def filter_option_opportunities(
    df: pl.DataFrame,
    min_score: float = 1.0,
    max_spread_pct: float | None = 0.20,
    min_open_interest: int | None = 100,
    objective: str = "short_vol",
) -> pl.DataFrame:
    """
    Filter scored option opportunities.
    """

    result = score_option_opportunities(df, objective=objective)

    result = result.filter(pl.col("option_opportunity_score") >= min_score)

    if max_spread_pct is not None:
        result = result.filter(pl.col("spread_pct") <= max_spread_pct)

    if min_open_interest is not None:
        result = result.filter(pl.col("open_interest") >= min_open_interest)

    return result


def select_top_opportunities(
    df: pl.DataFrame,
    n: int = 10,
    objective: str = "short_vol",
) -> pl.DataFrame:
    """
    Select top N option opportunities.
    """

    if n <= 0:
        raise ValueError("n must be greater than zero")

    result = score_option_opportunities(df, objective=objective)

    return result.head(n)
