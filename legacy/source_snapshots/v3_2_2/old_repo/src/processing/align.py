import polars as pl


class DatasetAligner:
    """
    Aligns multi-asset datasets across dates and symbols.
    """

    def get_common_dates(self, df: pl.DataFrame) -> pl.Series:
        self._validate(df)

        symbol_count = df["symbol"].n_unique()

        return (
            df.group_by("date")
            .agg(pl.col("symbol").n_unique().alias("symbol_count"))
            .filter(pl.col("symbol_count") == symbol_count)
            .select("date")
            .to_series()
        )

    def align_to_common_dates(self, df: pl.DataFrame) -> pl.DataFrame:
        common_dates = self.get_common_dates(df).to_list()

        return (
            df.filter(pl.col("date").is_in(common_dates))
            .sort(["date", "symbol"])
        )
    def align_to_symbol_universe(
        self,
        df: pl.DataFrame,
        symbols: list[str],
    ) -> pl.DataFrame:
        self._validate(df)

        symbols = [symbol.upper() for symbol in symbols]

        return (
            df.filter(pl.col("symbol").str.to_uppercase().is_in(symbols))
            .sort(["date", "symbol"])
        )

    def drop_rows_with_null_features(
        self,
        df: pl.DataFrame,
        feature_columns: list[str] | None = None,
    ) -> pl.DataFrame:
        self._validate(df)

        if feature_columns is None:
            feature_columns = [
                col for col in df.columns if col not in {"date", "symbol"}
            ]

        return df.drop_nulls(subset=feature_columns)

    def _validate(self, df: pl.DataFrame) -> None:
        required = {"date", "symbol"}
        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")
