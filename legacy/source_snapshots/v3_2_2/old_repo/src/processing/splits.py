import polars as pl


class DatasetSplitter:
    """
    Time-aware dataset splitting utilities.

    These are used for:
    - factor research validation
    - train/test model splits
    - walk-forward testing
    - preventing lookahead bias
    """

    required_columns = {"date", "symbol"}

    def train_test_split_by_date(
        self,
        df: pl.DataFrame,
        split_date: str,
        include_split_date_in_train: bool = True,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        self._validate(df)

        sorted_df = df.sort(["date", "symbol"])

        if include_split_date_in_train:
            train = sorted_df.filter(pl.col("date") <= split_date)
            test = sorted_df.filter(pl.col("date") > split_date)
        else:
            train = sorted_df.filter(pl.col("date") < split_date)
            test = sorted_df.filter(pl.col("date") >= split_date)

        return train, test

    def train_test_split_by_fraction(
        self,
        df: pl.DataFrame,
        train_fraction: float = 0.7,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        self._validate(df)

        if not 0 < train_fraction < 1:
            raise ValueError("train_fraction must be between 0 and 1.")

        dates = self.get_unique_dates(df)

        if len(dates) < 2:
            raise ValueError("At least two unique dates are required.")

        split_index = int(len(dates) * train_fraction)
        split_index = max(1, min(split_index, len(dates) - 1))

        split_date = dates[split_index - 1]

        return self.train_test_split_by_date(
            df=df,
            split_date=split_date,
            include_split_date_in_train=True,
        )

    def expanding_window_splits(
        self,
        df: pl.DataFrame,
        initial_train_window: int,
        test_window: int,
        step: int | None = None,
        gap: int = 0,
    ) -> list[tuple[pl.DataFrame, pl.DataFrame]]:
        self._validate(df)
        self._validate_window_args(
            train_window=initial_train_window,
            test_window=test_window,
            gap=gap,
        )

        if step is None:
            step = test_window

        if step <= 0:
            raise ValueError("step must be greater than 0.")

        dates = self.get_unique_dates(df)
        splits: list[tuple[pl.DataFrame, pl.DataFrame]] = []

        train_end = initial_train_window

        while train_end + gap + test_window <= len(dates):
            train_dates = dates[:train_end]

            test_start = train_end + gap
            test_end = test_start + test_window
            test_dates = dates[test_start:test_end]

            splits.append(
                (
                    self._filter_dates(df, train_dates),
                    self._filter_dates(df, test_dates),
                )
            )

            train_end += step

        return splits

    def rolling_window_splits(
        self,
        df: pl.DataFrame,
        train_window: int,
        test_window: int,
        step: int | None = None,
        gap: int = 0,
    ) -> list[tuple[pl.DataFrame, pl.DataFrame]]:
        self._validate(df)
        self._validate_window_args(
            train_window=train_window,
            test_window=test_window,
            gap=gap,
        )

        if step is None:
            step = test_window

        if step <= 0:
            raise ValueError("step must be greater than 0.")

        dates = self.get_unique_dates(df)
        splits: list[tuple[pl.DataFrame, pl.DataFrame]] = []

        train_start = 0

        while train_start + train_window + gap + test_window <= len(dates):
            train_end = train_start + train_window

            train_dates = dates[train_start:train_end]

            test_start = train_end + gap
            test_end = test_start + test_window
            test_dates = dates[test_start:test_end]

            splits.append(
                (
                    self._filter_dates(df, train_dates),
                    self._filter_dates(df, test_dates),
                )
            )

            train_start += step

        return splits

    def get_unique_dates(self, df: pl.DataFrame) -> list[str]:
        self._validate(df)

        return (
            df.select("date")
            .unique()
            .sort("date")
            .to_series()
            .to_list()
        )

    def get_date_bounds(self, df: pl.DataFrame) -> tuple[str, str]:
        dates = self.get_unique_dates(df)

        if not dates:
            raise ValueError("Dataset contains no dates.")

        return dates[0], dates[-1]

    def _filter_dates(
        self,
        df: pl.DataFrame,
        dates: list[str],
    ) -> pl.DataFrame:
        return (
            df.filter(pl.col("date").is_in(dates))
            .sort(["date", "symbol"])
        )

    def _validate(self, df: pl.DataFrame) -> None:
        missing = self.required_columns - set(df.columns)

        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")

    def _validate_window_args(
        self,
        train_window: int,
        test_window: int,
        gap: int,
    ) -> None:
        if train_window <= 0:
            raise ValueError("train_window must be greater than 0.")

        if test_window <= 0:
            raise ValueError("test_window must be greater than 0.")

        if gap < 0:
            raise ValueError("gap must be greater than or equal to 0.")
