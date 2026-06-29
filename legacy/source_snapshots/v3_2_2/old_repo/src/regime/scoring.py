from __future__ import annotations

import polars as pl


REGIME_SCORE_MAP: dict[str, float] = {
    "goldilocks": 1.0,
    "overheating": 0.25,
    "stagflation": -1.0,
    "deflationary_slowdown": -0.75,
    "mixed": 0.0,
}


def score_regime(
    df: pl.DataFrame,
    regime_col: str = "regime_label",
    output_column: str = "regime_score",
    score_map: dict[str, float] | None = None,
) -> pl.DataFrame:
    if regime_col not in df.columns:
        raise ValueError(f"Missing column: {regime_col}")

    score_map = score_map or REGIME_SCORE_MAP

    return df.with_columns(
        pl.col(regime_col)
        .replace_strict(
            score_map,
            default=0.0,
        )
        .cast(pl.Float64)
        .alias(output_column)
        )


def regime_risk_bias(
    df: pl.DataFrame,
    score_col: str = "regime_score",
    output_column: str = "regime_risk_bias",
) -> pl.DataFrame:
    if score_col not in df.columns:
        raise ValueError(f"Missing column: {score_col}")

    return df.with_columns(
        pl.when(pl.col(score_col) > 0.5)
        .then(pl.lit("risk_on_bias"))
        .when(pl.col(score_col) < -0.5)
        .then(pl.lit("risk_off_bias"))
        .otherwise(pl.lit("neutral_bias"))
        .alias(output_column)
    )
