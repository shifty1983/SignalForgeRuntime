import polars as pl


class DatasetFilter:
    """
    Filtering utilities for processed research datasets.

    These filters are used before factor research, backtesting, and modeling.
    """

    required_columns = {"date", "symbol"}

    def filter_symbols(
        self,
        df: pl.DataFrame,
        symbols: list[str],
    ) -> pl.DataFrame:
        self._validate(df)

        symbols_upper = [symbol.upper() for symbol in symbols]

        return (
            df.filter(pl.col("symbol").str.to_uppercase().is_in(symbols_upper))
            .sort(["date", "symbol"])
        )

    def filter_date_range(
        self,
        df: pl.DataFrame,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        self._validate(df)

        condition = pl.lit(True)

        if start_date is not None:
            condition = condition & (pl.col("date") >= start_date)

        if end_date is not None:
            condition = condition & (pl.col("date") <= end_date)

        return df.filter(condition).sort(["date", "symbol"])

    def drop_null_features(
        self,
        df: pl.DataFrame,
        feature_columns: list[str] | None = None,
    ) -> pl.DataFrame:
        self._validate(df)

        if feature_columns is None:
            feature_columns = self.get_feature_columns(df)

        return df.drop_nulls(subset=feature_columns)

    def filter_min_observations_per_symbol(
        self,
        df: pl.DataFrame,
        min_observations: int,
    ) -> pl.DataFrame:
        self._validate(df)

        if min_observations <= 0:
            raise ValueError("min_observations must be greater than 0.")

        valid_symbols = (
            df.group_by("symbol")
            .len()
            .filter(pl.col("len") >= min_observations)
            .select("symbol")
        )

        return (
            df.join(valid_symbols, on="symbol", how="inner")
            .sort(["date", "symbol"])
        )

    def filter_complete_dates(
        self,
        df: pl.DataFrame,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        self._validate(df)

        if symbols is not None:
            df = self.filter_symbols(df, symbols)

        symbol_count = df["symbol"].n_unique()

        complete_dates = (
            df.group_by("date")
            .agg(pl.col("symbol").n_unique().alias("symbol_count"))
            .filter(pl.col("symbol_count") == symbol_count)
            .select("date")
        )

        return (
            df.join(complete_dates, on="date", how="inner")
            .sort(["date", "symbol"])
        )

    def get_feature_columns(self, df: pl.DataFrame) -> list[str]:
        return [
            col
            for col in df.columns
            if col not in self.required_columns
        ]

    def _validate(self, df: pl.DataFrame) -> None:
        missing = self.required_columns - set(df.columns)

        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")
