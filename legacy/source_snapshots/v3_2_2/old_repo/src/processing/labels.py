import polars as pl


class DatasetLabeler:
    """
    Creates forward-looking research labels.

    Labels are used for:
    - forward return analysis
    - signal validation
    - expected value modeling
    - supervised learning targets
    - strategy research
    """

    required_columns = {"date", "symbol"}

    def add_forward_returns(
        self,
        df: pl.DataFrame,
        price_column: str = "close",
        horizons: list[int] | None = None,
        prefix: str = "forward_return",
    ) -> pl.DataFrame:
        self._validate(df)
        self._validate_numeric_columns(df, [price_column])

        if horizons is None:
            horizons = [1, 5, 20]

        self._validate_horizons(horizons)

        working_df = df.sort(["symbol", "date"])

        expressions = [
            (
                (pl.col(price_column).shift(-horizon).over("symbol") / pl.col(price_column))
                - 1
            ).alias(f"{prefix}_{horizon}d")
            for horizon in horizons
        ]

        return working_df.with_columns(expressions).sort(["date", "symbol"])

    def add_forward_log_returns(
        self,
        df: pl.DataFrame,
        price_column: str = "close",
        horizons: list[int] | None = None,
        prefix: str = "forward_log_return",
    ) -> pl.DataFrame:
        self._validate(df)
        self._validate_numeric_columns(df, [price_column])

        if horizons is None:
            horizons = [1, 5, 20]

        self._validate_horizons(horizons)

        working_df = df.sort(["symbol", "date"])

        expressions = [
            (
                pl.col(price_column).shift(-horizon).over("symbol").log()
                - pl.col(price_column).log()
            ).alias(f"{prefix}_{horizon}d")
            for horizon in horizons
        ]

        return working_df.with_columns(expressions).sort(["date", "symbol"])

    def add_direction_labels(
        self,
        df: pl.DataFrame,
        return_columns: list[str],
        threshold: float = 0.0,
        suffix: str = "_direction",
    ) -> pl.DataFrame:
        self._validate(df)
        self._validate_numeric_columns(df, return_columns)

        expressions = [
            pl.when(pl.col(col) > threshold)
            .then(1)
            .when(pl.col(col) < -threshold)
            .then(-1)
            .otherwise(0)
            .alias(f"{col}{suffix}")
            for col in return_columns
        ]

        return df.with_columns(expressions)

    def add_positive_return_labels(
        self,
        df: pl.DataFrame,
        return_columns: list[str],
        threshold: float = 0.0,
        suffix: str = "_positive",
    ) -> pl.DataFrame:
        self._validate(df)
        self._validate_numeric_columns(df, return_columns)

        expressions = [
            pl.when(pl.col(col) > threshold)
            .then(1)
            .otherwise(0)
            .alias(f"{col}{suffix}")
            for col in return_columns
        ]

        return df.with_columns(expressions)

    def drop_unlabeled_rows(
        self,
        df: pl.DataFrame,
        label_columns: list[str],
    ) -> pl.DataFrame:
        self._validate(df)

        missing = set(label_columns) - set(df.columns)

        if missing:
            raise ValueError(f"Missing label columns: {missing}")

        return df.drop_nulls(subset=label_columns)

    def _validate(self, df: pl.DataFrame) -> None:
        missing = self.required_columns - set(df.columns)

        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")

    def _validate_numeric_columns(
        self,
        df: pl.DataFrame,
        columns: list[str],
    ) -> None:
        missing = set(columns) - set(df.columns)

        if missing:
            raise ValueError(f"Missing columns: {missing}")

        non_numeric = [
            col
            for col in columns
            if not df.schema[col].is_numeric()
        ]

        if non_numeric:
            raise TypeError(f"Columns must be numeric: {non_numeric}")

    def _validate_horizons(self, horizons: list[int]) -> None:
        if not horizons:
            raise ValueError("At least one horizon is required.")

        invalid = [horizon for horizon in horizons if horizon <= 0]

        if invalid:
            raise ValueError(f"Horizons must be positive integers: {invalid}")
