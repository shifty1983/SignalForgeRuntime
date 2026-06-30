from __future__ import annotations

import polars as pl


def combine_regimes(
    df: pl.DataFrame,
    growth_col: str = "growth_regime",
    inflation_col: str = "inflation_regime",
    rates_col: str = "rates_regime",
    liquidity_col: str = "liquidity_regime",
    risk_col: str = "risk_environment",
    credit_col: str = "credit_regime",
    yield_curve_col: str = "yield_curve_regime",
    output_column: str = "macro_regime",
) -> pl.DataFrame:

    required = [
        growth_col,
        inflation_col,
        rates_col,
        liquidity_col,
        risk_col,
        credit_col,
        yield_curve_col,
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return df.with_columns(
        pl.concat_str(
            [
                pl.col(growth_col),
                pl.col(inflation_col),
                pl.col(rates_col),
                pl.col(liquidity_col),
                pl.col(risk_col),
                pl.col(credit_col),
                pl.col(yield_curve_col),
            ],
            separator="|"
        ).alias(output_column)
    )


def simplified_regime_label(
    df: pl.DataFrame,
    growth_col: str = "growth_regime",
    inflation_col: str = "inflation_regime",
    output_column: str = "regime_label",
) -> pl.DataFrame:

    required = [growth_col, inflation_col]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return df.with_columns(
        pl.when(
            (pl.col(growth_col) == "growth_expansion")
            & (pl.col(inflation_col) == "inflation_falling")
        )
        .then(pl.lit("goldilocks"))

        .when(
            (pl.col(growth_col) == "growth_expansion")
            & (pl.col(inflation_col) == "inflation_rising")
        )
        .then(pl.lit("overheating"))

        .when(
            (pl.col(growth_col) == "growth_contraction")
            & (pl.col(inflation_col) == "inflation_rising")
        )
        .then(pl.lit("stagflation"))

        .when(
            (pl.col(growth_col) == "growth_contraction")
            & (pl.col(inflation_col) == "inflation_falling")
        )
        .then(pl.lit("deflationary_slowdown"))

        .otherwise(pl.lit("mixed"))
        .alias(output_column)
    )

