from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


REQUIRED_WALK_FORWARD_COLUMNS = {
    "date",
    "asset",
    "factor_value",
    "factor_rank",
    "signal",
    "forward_return",
}


@dataclass(frozen=True)
class FactorWalkForwardWindow:
    train_start_date: str
    train_end_date: str
    test_start_date: str
    test_end_date: str
    train_period_count: int
    test_period_count: int
    train_average_spread: float | None
    test_average_spread: float | None
    passed: bool
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FactorWalkForwardReport:
    case_name: str
    row_count: int
    date_count: int
    asset_count: int
    window_count: int
    passed_window_count: int
    pass_rate: float
    average_test_spread: float | None
    min_test_spread: float | None
    max_test_spread: float | None
    walk_forward_passed: bool
    failure_reasons: tuple[str, ...]
    windows: tuple[FactorWalkForwardWindow, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["windows"] = [window.to_dict() for window in self.windows]
        return data


def build_factor_walk_forward_report(
    *,
    case_name: str,
    factor_data: pd.DataFrame,
    min_train_periods: int = 3,
    test_periods: int = 1,
    min_test_spread: float = 0.0,
    min_pass_rate: float = 0.67,
) -> FactorWalkForwardReport:
    failure_reasons: list[str] = []

    row_count = len(factor_data)
    date_count = _safe_nunique(factor_data, "date")
    asset_count = _safe_nunique(factor_data, "asset")

    missing_columns = REQUIRED_WALK_FORWARD_COLUMNS.difference(factor_data.columns)
    if missing_columns:
        failure_reasons.append("missing_factor_columns")
        return _empty_report(
            case_name=case_name,
            row_count=row_count,
            date_count=date_count,
            asset_count=asset_count,
            failure_reasons=tuple(failure_reasons),
        )

    if factor_data.empty:
        failure_reasons.append("empty_factor_data")
        return _empty_report(
            case_name=case_name,
            row_count=row_count,
            date_count=date_count,
            asset_count=asset_count,
            failure_reasons=tuple(failure_reasons),
        )

    required_frame = factor_data[list(REQUIRED_WALK_FORWARD_COLUMNS)]
    if required_frame.isna().any().any():
        failure_reasons.append("missing_factor_data")

    dates = sorted(pd.to_datetime(factor_data["date"].dropna().unique()))

    required_period_count = min_train_periods + test_periods
    if len(dates) < required_period_count:
        failure_reasons.append("insufficient_walk_forward_history")

    windows = tuple(
        _build_walk_forward_windows(
            factor_data=factor_data,
            dates=dates,
            min_train_periods=min_train_periods,
            test_periods=test_periods,
            min_test_spread=min_test_spread,
        )
    )

    if not windows:
        failure_reasons.append("missing_walk_forward_windows")

    test_spreads = [
        window.test_average_spread
        for window in windows
        if window.test_average_spread is not None
    ]

    passed_window_count = sum(window.passed for window in windows)
    pass_rate = passed_window_count / len(windows) if windows else 0.0

    average_test_spread = (
        float(pd.Series(test_spreads, dtype="float64").mean()) if test_spreads else None
    )
    observed_min_test_spread = min(test_spreads) if test_spreads else None
    observed_max_test_spread = max(test_spreads) if test_spreads else None

    if pass_rate < min_pass_rate:
        failure_reasons.append("low_walk_forward_pass_rate")

    if average_test_spread is None or average_test_spread <= min_test_spread:
        failure_reasons.append("low_average_walk_forward_spread")

    if observed_min_test_spread is not None and observed_min_test_spread <= min_test_spread:
        failure_reasons.append("negative_or_zero_walk_forward_spread")

    for window in windows:
        failure_reasons.extend(window.failure_reasons)

    unique_failure_reasons = tuple(dict.fromkeys(failure_reasons))

    return FactorWalkForwardReport(
        case_name=case_name,
        row_count=row_count,
        date_count=date_count,
        asset_count=asset_count,
        window_count=len(windows),
        passed_window_count=passed_window_count,
        pass_rate=pass_rate,
        average_test_spread=average_test_spread,
        min_test_spread=observed_min_test_spread,
        max_test_spread=observed_max_test_spread,
        walk_forward_passed=not unique_failure_reasons,
        failure_reasons=unique_failure_reasons,
        windows=windows,
    )


def _build_walk_forward_windows(
    *,
    factor_data: pd.DataFrame,
    dates: list[pd.Timestamp],
    min_train_periods: int,
    test_periods: int,
    min_test_spread: float,
) -> list[FactorWalkForwardWindow]:
    windows: list[FactorWalkForwardWindow] = []

    for test_start_index in range(min_train_periods, len(dates), test_periods):
        train_dates = dates[:test_start_index]
        test_dates = dates[test_start_index : test_start_index + test_periods]

        if len(test_dates) < test_periods:
            continue

        train_data = factor_data[factor_data["date"].isin(train_dates)]
        test_data = factor_data[factor_data["date"].isin(test_dates)]

        train_spreads = _calculate_period_spreads(train_data)
        test_spreads = _calculate_period_spreads(test_data)

        train_average_spread = (
            float(pd.Series(train_spreads, dtype="float64").mean())
            if train_spreads
            else None
        )
        test_average_spread = (
            float(pd.Series(test_spreads, dtype="float64").mean())
            if test_spreads
            else None
        )

        window_failure_reasons: list[str] = []

        if train_average_spread is None:
            window_failure_reasons.append("missing_train_spread")

        if test_average_spread is None:
            window_failure_reasons.append("missing_test_spread")
        elif test_average_spread <= min_test_spread:
            window_failure_reasons.append("low_test_spread")

        if (
            train_average_spread is not None
            and test_average_spread is not None
            and train_average_spread > 0
            and test_average_spread < 0
        ):
            window_failure_reasons.append("train_test_direction_mismatch")

        windows.append(
            FactorWalkForwardWindow(
                train_start_date=train_dates[0].date().isoformat(),
                train_end_date=train_dates[-1].date().isoformat(),
                test_start_date=test_dates[0].date().isoformat(),
                test_end_date=test_dates[-1].date().isoformat(),
                train_period_count=len(train_dates),
                test_period_count=len(test_dates),
                train_average_spread=train_average_spread,
                test_average_spread=test_average_spread,
                passed=not window_failure_reasons,
                failure_reasons=tuple(dict.fromkeys(window_failure_reasons)),
            )
        )

    return windows


def _calculate_period_spreads(factor_data: pd.DataFrame) -> list[float]:
    clean_data = factor_data.dropna(subset=["date", "factor_rank", "forward_return"])

    spreads: list[float] = []

    for _, date_frame in clean_data.groupby("date"):
        midpoint = date_frame["factor_rank"].median()

        top = date_frame[date_frame["factor_rank"] > midpoint]
        bottom = date_frame[date_frame["factor_rank"] <= midpoint]

        if top.empty or bottom.empty:
            continue

        spread = float(top["forward_return"].mean() - bottom["forward_return"].mean())
        spreads.append(spread)

    return spreads


def _empty_report(
    *,
    case_name: str,
    row_count: int,
    date_count: int,
    asset_count: int,
    failure_reasons: tuple[str, ...],
) -> FactorWalkForwardReport:
    return FactorWalkForwardReport(
        case_name=case_name,
        row_count=row_count,
        date_count=date_count,
        asset_count=asset_count,
        window_count=0,
        passed_window_count=0,
        pass_rate=0.0,
        average_test_spread=None,
        min_test_spread=None,
        max_test_spread=None,
        walk_forward_passed=False,
        failure_reasons=failure_reasons,
        windows=(),
    )


def _safe_nunique(data: pd.DataFrame, column: str) -> int:
    if column not in data.columns:
        return 0

    return int(data[column].nunique())
