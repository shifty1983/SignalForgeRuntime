from __future__ import annotations

import polars as pl


VALID_REGIMES = {
    "goldilocks",
    "overheating",
    "stagflation",
    "deflationary_slowdown",
    "mixed",
}


def validate_regime_labels(
    df: pl.DataFrame,
    column: str = "regime_label",
) -> list[str]:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    labels = set(df[column].drop_nulls().to_list())

    invalid = labels - VALID_REGIMES

    return sorted(invalid)


def regime_distribution(
    df: pl.DataFrame,
    column: str = "regime_label",
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    return (
        df.group_by(column)
        .len()
        .rename({"len": "count"})
        .sort("count", descending=True)
    )


def missing_regime_rows(
    df: pl.DataFrame,
    column: str = "regime_label",
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    return df.filter(
        pl.col(column).is_null()
    )




