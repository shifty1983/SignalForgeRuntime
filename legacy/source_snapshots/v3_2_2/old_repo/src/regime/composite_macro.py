from __future__ import annotations

from collections.abc import Sequence

import polars as pl


DEFAULT_DRIVER_COLUMNS = [
    "growth_regime",
    "inflation_regime",
    "rates_regime",
    "liquidity_regime",
    "credit_regime",
    "credit_stress_level",
    "yield_curve_regime",
    "breadth_regime",
    "risk_environment",
]


def add_macro_regime_score(
    df: pl.DataFrame,
    *,
    growth_column: str = "growth_regime",
    inflation_column: str = "inflation_regime",
    rates_column: str = "rates_regime",
    liquidity_column: str = "liquidity_regime",
    credit_column: str = "credit_regime",
    credit_level_column: str = "credit_stress_level",
    yield_curve_column: str = "yield_curve_regime",
    breadth_column: str = "breadth_regime",
    risk_column: str = "risk_environment",
    output_column: str = "macro_regime_score",
) -> pl.DataFrame:
    """Score macro conditions from the completed regime components.

    The score is intentionally simple and explainable: each component maps to
    +1, 0, or -1 and the final score is the average. Positive values indicate
    supportive risk conditions; negative values indicate defensive/stress
    conditions. This gives later layers a compact numeric decision context
    without hiding the individual regime drivers.
    """

    required = [
        growth_column,
        inflation_column,
        rates_column,
        liquidity_column,
        credit_column,
        credit_level_column,
        yield_curve_column,
        breadth_column,
        risk_column,
    ]
    _validate_required_columns(df, required)

    component_exprs = [
        _string_signal(
            growth_column,
            positive_values={"growth_expansion"},
            negative_values={"growth_contraction"},
        ),
        _string_signal(
            inflation_column,
            positive_values={"inflation_falling", "inflation_stable"},
            negative_values={"inflation_rising"},
        ),
        _string_signal(
            rates_column,
            positive_values={"rates_falling", "rates_stable"},
            negative_values={"rates_rising"},
        ),
        _string_signal(
            liquidity_column,
            positive_values={"liquidity_expanding"},
            negative_values={"liquidity_contracting"},
        ),
        _string_signal(
            credit_column,
            positive_values={"credit_improving"},
            negative_values={"credit_deteriorating"},
        ),
        _string_signal(
            credit_level_column,
            positive_values={"credit_low_stress"},
            negative_values={"credit_high_stress"},
        ),
        _string_signal(
            yield_curve_column,
            positive_values={"curve_normal", "curve_resteepening"},
            negative_values={"curve_inverted", "curve_flattening", "curve_bearish_resteepening"},
        ),
        _string_signal(
            breadth_column,
            positive_values={"broad_strength", "breadth_improving"},
            negative_values={"broad_weakness", "breadth_deteriorating"},
        ),
        _string_signal(
            risk_column,
            positive_values={"strong_risk_on", "risk_on"},
            negative_values={"strong_risk_off", "risk_off"},
        ),
    ]

    return df.with_columns(pl.mean_horizontal(component_exprs).alias(output_column))


def classify_composite_macro_regime(
    df: pl.DataFrame,
    *,
    growth_column: str = "growth_regime",
    inflation_column: str = "inflation_regime",
    rates_column: str = "rates_regime",
    liquidity_column: str = "liquidity_regime",
    credit_column: str = "credit_regime",
    credit_level_column: str = "credit_stress_level",
    yield_curve_column: str = "yield_curve_regime",
    breadth_column: str = "breadth_regime",
    risk_column: str = "risk_environment",
    output_column: str = "macro_regime",
) -> pl.DataFrame:
    """Classify the composite macro regime from all regime sub-layers."""

    required = [
        growth_column,
        inflation_column,
        rates_column,
        liquidity_column,
        credit_column,
        credit_level_column,
        yield_curve_column,
        breadth_column,
        risk_column,
    ]
    _validate_required_columns(df, required)

    growth_expansion = pl.col(growth_column) == "growth_expansion"
    growth_contraction = pl.col(growth_column) == "growth_contraction"
    inflation_rising = pl.col(inflation_column) == "inflation_rising"
    inflation_falling = pl.col(inflation_column) == "inflation_falling"
    rates_rising = pl.col(rates_column) == "rates_rising"
    liquidity_contracting = pl.col(liquidity_column) == "liquidity_contracting"
    credit_deteriorating = pl.col(credit_column) == "credit_deteriorating"
    high_credit_stress = pl.col(credit_level_column) == "credit_high_stress"
    inverted_curve = pl.col(yield_curve_column).is_in(["curve_inverted", "curve_bearish_resteepening"])
    broad_strength = pl.col(breadth_column) == "broad_strength"
    broad_weakness = pl.col(breadth_column) == "broad_weakness"
    risk_on = pl.col(risk_column).is_in(["strong_risk_on", "risk_on"])
    risk_off = pl.col(risk_column).is_in(["strong_risk_off", "risk_off"])
    strong_risk_off = pl.col(risk_column) == "strong_risk_off"

    return df.with_columns(
        pl.when(high_credit_stress | (credit_deteriorating & strong_risk_off))
        .then(pl.lit("credit_stress"))
        .when(liquidity_contracting & strong_risk_off)
        .then(pl.lit("liquidity_stress"))
        .when(growth_contraction & inflation_falling & ~(risk_off | broad_weakness))
        .then(pl.lit("disinflationary_slowdown"))
        .when(growth_contraction & inflation_falling & (risk_off | broad_weakness))
        .then(pl.lit("deflationary_shock"))
        .when(growth_contraction & inflation_rising)
        .then(pl.lit("stagflation"))
        .when(growth_expansion & inflation_rising & rates_rising & (inverted_curve | credit_deteriorating))
        .then(pl.lit("late_cycle_overheating"))
        .when(growth_expansion & inflation_rising)
        .then(pl.lit("reflation"))
        .when(growth_expansion & inflation_falling & risk_on & broad_strength)
        .then(pl.lit("goldilocks"))
        .when(risk_off | broad_weakness | credit_deteriorating)
        .then(pl.lit("risk_off_transition"))
        .otherwise(pl.lit("neutral_mixed"))
        .alias(output_column)
    )


def add_macro_regime_confidence(
    df: pl.DataFrame,
    score_column: str = "macro_regime_score",
    output_column: str = "macro_regime_confidence",
) -> pl.DataFrame:
    """Use the absolute macro score as a simple agreement/confidence proxy."""

    if score_column not in df.columns:
        raise ValueError(f"Missing column: {score_column}")

    return df.with_columns(pl.col(score_column).abs().alias(output_column))


def add_macro_regime_drivers(
    df: pl.DataFrame,
    driver_columns: Sequence[str] | None = None,
    output_column: str = "macro_regime_drivers",
) -> pl.DataFrame:
    """Add a compact text audit trail of the component regimes used."""

    columns = list(driver_columns or DEFAULT_DRIVER_COLUMNS)
    _validate_required_columns(df, columns)

    driver_exprs = [
        pl.concat_str([pl.lit(f"{column}="), pl.col(column).cast(pl.Utf8)], separator="")
        for column in columns
    ]

    return df.with_columns(pl.concat_str(driver_exprs, separator=" | ").alias(output_column))


def build_composite_macro_regime(
    df: pl.DataFrame,
) -> pl.DataFrame:
    """Build score, label, confidence, and driver audit fields."""

    result = add_macro_regime_score(df)
    result = classify_composite_macro_regime(result)
    result = add_macro_regime_confidence(result)
    return add_macro_regime_drivers(result)


def _string_signal(
    column: str,
    *,
    positive_values: set[str],
    negative_values: set[str],
) -> pl.Expr:
    return (
        pl.when(pl.col(column).is_in(list(positive_values)))
        .then(pl.lit(1.0))
        .when(pl.col(column).is_in(list(negative_values)))
        .then(pl.lit(-1.0))
        .otherwise(pl.lit(0.0))
    )


def _validate_required_columns(df: pl.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
