import polars as pl


class ProcessingSchema:
    """
    Validates processed research datasets before they are used by
    research, backtesting, modeling, or portfolio construction layers.
    """

    required_columns = {"date", "symbol"}

    def validate(
        self,
        df: pl.DataFrame,
        feature_columns: list[str] | None = None,
        require_features: bool = True,
        require_numeric_features: bool = True,
    ) -> None:
        self.validate_non_empty(df)
        self.validate_required_columns(df)
        self.validate_no_null_keys(df)
        self.validate_unique_symbol_date(df)

        if require_features:
            self.validate_has_features(df)

        if feature_columns is not None:
            self.validate_feature_columns(
                df=df,
                feature_columns=feature_columns,
                require_numeric=require_numeric_features,
            )

    def validate_non_empty(self, df: pl.DataFrame) -> None:
        if df.is_empty():
            raise ValueError("Processed dataset is empty.")

    def validate_required_columns(self, df: pl.DataFrame) -> None:
        missing = self.required_columns - set(df.columns)

        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")

    def validate_no_null_keys(self, df: pl.DataFrame) -> None:
        self.validate_required_columns(df)

        null_key_rows = df.filter(
            pl.col("date").is_null() | pl.col("symbol").is_null()
        )

        if null_key_rows.height > 0:
            raise ValueError("Dataset contains null date or symbol values.")

    def validate_unique_symbol_date(self, df: pl.DataFrame) -> None:
        self.validate_required_columns(df)

        duplicates = (
            df.group_by(["date", "symbol"])
            .len()
            .filter(pl.col("len") > 1)
        )

        if duplicates.height > 0:
            raise ValueError("Dataset contains duplicate date/symbol rows.")

    def validate_has_features(self, df: pl.DataFrame) -> None:
        feature_columns = self.get_feature_columns(df)

        if not feature_columns:
            raise ValueError("Dataset contains no feature columns.")

    def validate_feature_columns(
        self,
        df: pl.DataFrame,
        feature_columns: list[str],
        require_numeric: bool = True,
    ) -> None:
        missing = set(feature_columns) - set(df.columns)

        if missing:
            raise ValueError(f"Missing requested feature columns: {missing}")

        if require_numeric:
            non_numeric = [
                col
                for col in feature_columns
                if not df.schema[col].is_numeric()
            ]

            if non_numeric:
                raise TypeError(
                    f"Feature columns must be numeric: {non_numeric}"
                )

    def get_feature_columns(self, df: pl.DataFrame) -> list[str]:
        return [
            col
            for col in df.columns
            if col not in self.required_columns
        ]
