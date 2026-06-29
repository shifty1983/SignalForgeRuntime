from __future__ import annotations

from collections.abc import Sequence

import polars as pl


DEFAULT_DATE_COLUMN = "date"
DEFAULT_SYMBOL_COLUMN = "symbol"


def missing_columns(
    df: pl.DataFrame,
    required_columns: Sequence[str],
) -> list[str]:
    return [col for col in required_columns if col not in df.columns]


def require_columns(
    df: pl.DataFrame,
    required_columns: Sequence[str],
    context: str = "DataFrame",
) -> None:
    missing = missing_columns(df, required_columns)

    if missing:
        raise ValueError(f"{context} is missing required columns: {missing}")


def duplicate_panel_keys(
    df: pl.DataFrame,
    date_column: str = DEFAULT_DATE_COLUMN,
    symbol_column: str = DEFAULT_SYMBOL_COLUMN,
) -> pl.DataFrame:
    require_columns(
        df,
        [date_column, symbol_column],
        context="Research panel",
    )

    return (
        df.group_by([date_column, symbol_column])
        .len(name="row_count")
        .filter(pl.col("row_count") > 1)
        .sort([date_column, symbol_column])
    )


def has_duplicate_panel_keys(
    df: pl.DataFrame,
    date_column: str = DEFAULT_DATE_COLUMN,
    symbol_column: str = DEFAULT_SYMBOL_COLUMN,
) -> bool:
    return duplicate_panel_keys(
        df=df,
        date_column=date_column,
        symbol_column=symbol_column,
    ).height > 0


def null_summary(
    df: pl.DataFrame,
    columns: Sequence[str] | None = None,
) -> pl.DataFrame:
    selected_columns = list(columns or df.columns)

    require_columns(
        df,
        selected_columns,
        context="Null summary input",
    )

    row_count = df.height

    summary = pl.DataFrame(
        {
            "column": selected_columns,
            "null_count": [
                df.get_column(col).null_count()
                for col in selected_columns
            ],
        }
    )

    return summary.with_columns(
        pl.when(pl.lit(row_count) > 0)
        .then(pl.col("null_count") / row_count)
        .otherwise(0.0)
        .alias("null_pct")
    )


def panel_summary(
    df: pl.DataFrame,
    date_column: str = DEFAULT_DATE_COLUMN,
    symbol_column: str = DEFAULT_SYMBOL_COLUMN,
) -> pl.DataFrame:
    require_columns(
        df,
        [date_column, symbol_column],
        context="Research panel",
    )

    return df.select(
        pl.len().alias("row_count"),
        pl.col(date_column).n_unique().alias("date_count"),
        pl.col(symbol_column).n_unique().alias("symbol_count"),
        pl.col(date_column).min().alias("start_date"),
        pl.col(date_column).max().alias("end_date"),
    )


def coverage_by_date(
    df: pl.DataFrame,
    date_column: str = DEFAULT_DATE_COLUMN,
    symbol_column: str = DEFAULT_SYMBOL_COLUMN,
) -> pl.DataFrame:
    require_columns(
        df,
        [date_column, symbol_column],
        context="Research panel",
    )

    return (
        df.group_by(date_column)
        .agg(
            pl.len().alias("row_count"),
            pl.col(symbol_column).n_unique().alias("symbol_count"),
        )
        .sort(date_column)
    )


def coverage_by_symbol(
    df: pl.DataFrame,
    date_column: str = DEFAULT_DATE_COLUMN,
    symbol_column: str = DEFAULT_SYMBOL_COLUMN,
) -> pl.DataFrame:
    require_columns(
        df,
        [date_column, symbol_column],
        context="Research panel",
    )

    return (
        df.group_by(symbol_column)
        .agg(
            pl.len().alias("row_count"),
            pl.col(date_column).n_unique().alias("date_count"),
            pl.col(date_column).min().alias("start_date"),
            pl.col(date_column).max().alias("end_date"),
        )
        .sort(symbol_column)
    )


def validate_research_panel(
    df: pl.DataFrame,
    required_columns: Sequence[str] | None = None,
    no_null_columns: Sequence[str] | None = None,
    date_column: str = DEFAULT_DATE_COLUMN,
    symbol_column: str = DEFAULT_SYMBOL_COLUMN,
    allow_duplicate_keys: bool = False,
) -> None:
    required = [
        date_column,
        symbol_column,
        *(required_columns or []),
    ]

    require_columns(
        df,
        required,
        context="Research panel",
    )

    if df.is_empty():
        raise ValueError("Research panel is empty.")

    key_nulls = null_summary(
        df,
        [date_column, symbol_column],
    ).filter(pl.col("null_count") > 0)

    if key_nulls.height > 0:
        raise ValueError(
            f"Research panel contains null key values: {key_nulls.to_dicts()}"
        )

    if not allow_duplicate_keys:
        duplicates = duplicate_panel_keys(
            df=df,
            date_column=date_column,
            symbol_column=symbol_column,
        )

        if duplicates.height > 0:
            raise ValueError(
                f"Research panel contains duplicate date/symbol rows: "
                f"{duplicates.to_dicts()}"
            )

    if no_null_columns:
        require_columns(
            df,
            no_null_columns,
            context="Research panel no-null validation",
        )

        nulls = null_summary(df, no_null_columns).filter(
            pl.col("null_count") > 0
        )

        if nulls.height > 0:
            raise ValueError(
                f"Research panel contains unexpected null values: "
                f"{nulls.to_dicts()}"
            )
