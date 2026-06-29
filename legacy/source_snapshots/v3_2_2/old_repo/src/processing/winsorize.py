import polars as pl


class DatasetWinsorizer:
    """
    Caps extreme values in feature columns.

    Winsorization helps reduce the impact of outliers before:
    - cross-sectional ranking
    - z-score normalization
    - model training
    - factor research
    """

    required_columns = {"date", "symbol"}

    def winsorize_columns(
        self,
        df: pl.DataFrame,
        columns: list[str],
        lower_quantile: float = 0.01,
        upper_quantile: float = 0.99,
        suffix: str = "_winsorized",
    ) -> pl.DataFrame:
        self._validate(df)
        self._validate_quantiles(lower_quantile, upper_quantile)
        self._validate_columns(df, columns)

        expressions = []

        for col in columns:
            lower_bound = df.select(pl.col(col).quantile(lower_quantile)).item()
            upper_bound = df.select(pl.col(col).quantile(upper_quantile)).item()

            expressions.append(
                pl.when(pl.col(col) < lower_bound)
                .then(lower_bound)
                .when(pl.col(col) > upper_bound)
                .then(upper_bound)
                .otherwise(pl.col(col))
                .alias(f"{col}{suffix}")
            )

        return df.with_columns(expressions)

    def winsorize_by_date(
        self,
        df: pl.DataFrame,
        columns: list[str],
        lower_quantile: float = 0.01,
        upper_quantile: float = 0.99,
        suffix: str = "_winsorized",
    ) -> pl.DataFrame:
        self._validate(df)
        self._validate_quantiles(lower_quantile, upper_quantile)
        self._validate_columns(df, columns)

        expressions = []

        for col in columns:
            lower_bound = pl.col(col).quantile(lower_quantile).over("date")
            upper_bound = pl.col(col).quantile(upper_quantile).over("date")

            expressions.append(
                pl.when(pl.col(col) < lower_bound)
                .then(lower_bound)
                .when(pl.col(col) > upper_bound)
                .then(upper_bound)
                .otherwise(pl.col(col))
                .alias(f"{col}{suffix}")
            )

        return df.with_columns(expressions)

    def clip_columns(
        self,
        df: pl.DataFrame,
        bounds: dict[str, tuple[float, float]],
        suffix: str = "_clipped",
    ) -> pl.DataFrame:
        self._validate(df)
        self._validate_columns(df, list(bounds.keys()))

        expressions = []

        for col, (lower_bound, upper_bound) in bounds.items():
            if lower_bound > upper_bound:
                raise ValueError(
                    f"Lower bound cannot exceed upper bound for column {col}."
                )

            expressions.append(
                pl.when(pl.col(col) < lower_bound)
                .then(lower_bound)
                .when(pl.col(col) > upper_bound)
                .then(upper_bound)
                .otherwise(pl.col(col))
                .alias(f"{col}{suffix}")
            )

        return df.with_columns(expressions)

    def _validate(self, df: pl.DataFrame) -> None:
        missing = self.required_columns - set(df.columns)

        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")

    def _validate_columns(self, df: pl.DataFrame, columns: list[str]) -> None:
        missing = set(columns) - set(df.columns)

        if missing:
            raise ValueError(f"Missing columns for winsorization: {missing}")

        non_numeric = [
            col
            for col in columns
            if not df.schema[col].is_numeric()
        ]

        if non_numeric:
            raise TypeError(f"Winsorized columns must be numeric: {non_numeric}")

    def _validate_quantiles(
        self,
        lower_quantile: float,
        upper_quantile: float,
    ) -> None:
        if not 0 <= lower_quantile <= 1:
            raise ValueError("lower_quantile must be between 0 and 1.")

        if not 0 <= upper_quantile <= 1:
            raise ValueError("upper_quantile must be between 0 and 1.")

        if lower_quantile >= upper_quantile:
            raise ValueError("lower_quantile must be less than upper_quantile.")
