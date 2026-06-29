import polars as pl


class DatasetNormalizer:
    """
    Cross-sectional normalization utilities for research datasets.
    """

    def zscore_by_date(
        self,
        df: pl.DataFrame,
        columns: list[str],
    ) -> pl.DataFrame:
        self._validate(df)

        expressions = []

        for col in columns:
            expressions.append(
                (
                    (pl.col(col) - pl.col(col).mean().over("date"))
                    / pl.col(col).std().over("date")
                ).alias(f"{col}_zscore")
            )

        return df.with_columns(expressions)

    def rank_by_date(
        self,
        df: pl.DataFrame,
        columns: list[str],
        descending: bool = False,
    ) -> pl.DataFrame:
        self._validate(df)

        expressions = [
            pl.col(col)
            .rank(descending=descending)
            .over("date")
            .alias(f"{col}_rank")
            for col in columns
        ]

        return df.with_columns(expressions)

    def percentile_rank_by_date(
        self,
        df: pl.DataFrame,
        columns: list[str],
        descending: bool = False,
    ) -> pl.DataFrame:
        self._validate(df)

        expressions = [
            (
                pl.col(col).rank(descending=descending).over("date")
                / pl.col(col).count().over("date")
            ).alias(f"{col}_percentile_rank")
            for col in columns
        ]

        return df.with_columns(expressions)

    def min_max_scale_by_date(
        self,
        df: pl.DataFrame,
        columns: list[str],
    ) -> pl.DataFrame:
        self._validate(df)

        expressions = []

        for col in columns:
            expressions.append(
                (
                    (pl.col(col) - pl.col(col).min().over("date"))
                    / (
                        pl.col(col).max().over("date")
                        - pl.col(col).min().over("date")
                    )
                ).alias(f"{col}_minmax")
            )

        return df.with_columns(expressions)

    def _validate(self, df: pl.DataFrame) -> None:
        required = {"date", "symbol"}
        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")
