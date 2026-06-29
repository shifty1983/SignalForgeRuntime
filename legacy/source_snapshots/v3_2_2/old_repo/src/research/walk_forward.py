from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

import polars as pl

from src.research.validation import (
    ResearchValidationReport,
    ResearchValidationStatus,
    validate_research_output,
)


class WalkForwardMode(str, Enum):
    ROLLING = "rolling"
    EXPANDING = "expanding"


class WalkForwardWindowStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


class WalkForwardReportStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    MIXED = "mixed"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class WalkForwardWindow:
    name: str
    index: int
    train_start: Any
    train_end: Any
    test_start: Any
    test_end: Any
    mode: WalkForwardMode | str = WalkForwardMode.ROLLING
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(
            self,
            "mode",
            _coerce_enum(self.mode, WalkForwardMode, "mode"),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

        if not self.name:
            raise ValueError("Walk-forward window name cannot be empty.")

        if self.index < 0:
            raise ValueError("Walk-forward window index cannot be negative.")

        if self.train_start > self.train_end:
            raise ValueError("train_start cannot be after train_end.")

        if self.test_start > self.test_end:
            raise ValueError("test_start cannot be after test_end.")

        if self.train_end >= self.test_start:
            raise ValueError("train_end must be before test_start.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "index": self.index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "mode": self.mode.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class WalkForwardWindowResult:
    window: WalkForwardWindow
    status: WalkForwardWindowStatus
    validation_report: ResearchValidationReport | None = None
    train_rows: int = 0
    test_rows: int = 0
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == WalkForwardWindowStatus.PASSED

    @property
    def failed(self) -> bool:
        return self.status == WalkForwardWindowStatus.FAILED

    @property
    def insufficient_data(self) -> bool:
        return self.status == WalkForwardWindowStatus.INSUFFICIENT_DATA

    @property
    def errored(self) -> bool:
        return self.status == WalkForwardWindowStatus.ERROR

    def metric_value(self, name: str) -> float | int | None:
        if self.validation_report is None:
            return None

        return self.validation_report.metric_value(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window.to_dict(),
            "status": self.status.value,
            "train_rows": self.train_rows,
            "test_rows": self.test_rows,
            "error": self.error,
            "validation_report": (
                self.validation_report.to_dict()
                if self.validation_report is not None
                else None
            ),
        }


@dataclass(frozen=True)
class WalkForwardReport:
    status: WalkForwardReportStatus
    window_results: tuple[WalkForwardWindowResult, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == WalkForwardReportStatus.PASSED

    @property
    def failed(self) -> bool:
        return self.status == WalkForwardReportStatus.FAILED

    @property
    def mixed(self) -> bool:
        return self.status == WalkForwardReportStatus.MIXED

    @property
    def insufficient_data(self) -> bool:
        return self.status == WalkForwardReportStatus.INSUFFICIENT_DATA

    def pass_rate(self) -> float:
        if not self.window_results:
            return 0.0

        passed = sum(result.passed for result in self.window_results)

        return passed / len(self.window_results)

    def failed_windows(self) -> tuple[WalkForwardWindowResult, ...]:
        return tuple(
            result
            for result in self.window_results
            if result.status
            in {
                WalkForwardWindowStatus.FAILED,
                WalkForwardWindowStatus.ERROR,
                WalkForwardWindowStatus.INSUFFICIENT_DATA,
            }
        )

    def metric_values(self, metric_name: str) -> tuple[float | int, ...]:
        values: list[float | int] = []

        for result in self.window_results:
            value = result.metric_value(metric_name)

            if value is not None:
                values.append(value)

        return tuple(values)

    def metric_summary(self, metric_name: str) -> dict[str, float | int | None]:
        values = self.metric_values(metric_name)

        if not values:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
            }

        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "window_count": len(self.window_results),
            "passed_count": sum(result.passed for result in self.window_results),
            "failed_count": sum(result.failed for result in self.window_results),
            "insufficient_data_count": sum(
                result.insufficient_data for result in self.window_results
            ),
            "error_count": sum(result.errored for result in self.window_results),
            "pass_rate": self.pass_rate(),
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "window_results": [
                result.to_dict() for result in self.window_results
            ],
            "metadata": dict(self.metadata),
        }


def build_walk_forward_windows(
    dates: Iterable[Any],
    train_size: int,
    test_size: int,
    step_size: int | None = None,
    mode: WalkForwardMode | str = WalkForwardMode.ROLLING,
    name_prefix: str = "walk_forward",
) -> tuple[WalkForwardWindow, ...]:
    if train_size <= 0:
        raise ValueError("train_size must be greater than zero.")

    if test_size <= 0:
        raise ValueError("test_size must be greater than zero.")

    if step_size is not None and step_size <= 0:
        raise ValueError("step_size must be greater than zero when provided.")

    mode_value = _coerce_enum(mode, WalkForwardMode, "mode")
    step = step_size or test_size

    unique_dates = tuple(sorted(set(dates)))

    if len(unique_dates) < train_size + test_size:
        return ()

    windows: list[WalkForwardWindow] = []

    cursor = train_size
    window_index = 0

    while cursor + test_size <= len(unique_dates):
        if mode_value == WalkForwardMode.EXPANDING:
            train_start_index = 0
        else:
            train_start_index = cursor - train_size

        train_end_index = cursor - 1
        test_start_index = cursor
        test_end_index = cursor + test_size - 1

        windows.append(
            WalkForwardWindow(
                name=f"{name_prefix}_{window_index + 1}",
                index=window_index,
                train_start=unique_dates[train_start_index],
                train_end=unique_dates[train_end_index],
                test_start=unique_dates[test_start_index],
                test_end=unique_dates[test_end_index],
                mode=mode_value,
                metadata={
                    "train_size": train_size,
                    "test_size": test_size,
                    "step_size": step,
                },
            )
        )

        cursor += step
        window_index += 1

    return tuple(windows)


def build_walk_forward_windows_from_frame(
    df: pl.DataFrame,
    date_column: str = "date",
    train_size: int = 60,
    test_size: int = 20,
    step_size: int | None = None,
    mode: WalkForwardMode | str = WalkForwardMode.ROLLING,
    name_prefix: str = "walk_forward",
) -> tuple[WalkForwardWindow, ...]:
    _require_columns(df, [date_column], context="Walk-forward input")

    dates = df.select(pl.col(date_column).unique().sort()).to_series().to_list()

    return build_walk_forward_windows(
        dates=dates,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        mode=mode,
        name_prefix=name_prefix,
    )


def split_walk_forward_window(
    df: pl.DataFrame,
    window: WalkForwardWindow,
    date_column: str = "date",
) -> tuple[pl.DataFrame, pl.DataFrame]:
    _require_columns(df, [date_column], context="Walk-forward split input")

    train = df.filter(
        (pl.col(date_column) >= window.train_start)
        & (pl.col(date_column) <= window.train_end)
    )

    test = df.filter(
        (pl.col(date_column) >= window.test_start)
        & (pl.col(date_column) <= window.test_end)
    )

    return train, test


def run_walk_forward_window(
    df: pl.DataFrame,
    window: WalkForwardWindow,
    validation_kwargs: Mapping[str, Any] | None = None,
    date_column: str = "date",
) -> WalkForwardWindowResult:
    kwargs = dict(validation_kwargs or {})
    kwargs.setdefault("date_column", date_column)

    try:
        train, test = split_walk_forward_window(
            df=df,
            window=window,
            date_column=date_column,
        )

        report = validate_research_output(test, **kwargs)

        if report.status == ResearchValidationStatus.PASSED:
            status = WalkForwardWindowStatus.PASSED
        elif report.status == ResearchValidationStatus.INSUFFICIENT_DATA:
            status = WalkForwardWindowStatus.INSUFFICIENT_DATA
        else:
            status = WalkForwardWindowStatus.FAILED

        return WalkForwardWindowResult(
            window=window,
            status=status,
            validation_report=report,
            train_rows=train.height,
            test_rows=test.height,
        )

    except Exception as exc:
        return WalkForwardWindowResult(
            window=window,
            status=WalkForwardWindowStatus.ERROR,
            validation_report=None,
            train_rows=0,
            test_rows=0,
            error=str(exc),
        )


def run_walk_forward_validation(
    df: pl.DataFrame,
    windows: Iterable[WalkForwardWindow],
    validation_kwargs: Mapping[str, Any] | None = None,
    date_column: str = "date",
) -> WalkForwardReport:
    window_tuple = tuple(windows)

    if not window_tuple:
        raise ValueError("At least one walk-forward window must be provided.")

    results = tuple(
        run_walk_forward_window(
            df=df,
            window=window,
            validation_kwargs=validation_kwargs,
            date_column=date_column,
        )
        for window in window_tuple
    )

    return WalkForwardReport(
        status=_derive_report_status(results),
        window_results=results,
        metadata={
            "window_count": len(results),
            "date_column": date_column,
            "validation_kwargs": dict(validation_kwargs or {}),
        },
    )


def run_walk_forward_validation_from_frame(
    df: pl.DataFrame,
    date_column: str = "date",
    train_size: int = 60,
    test_size: int = 20,
    step_size: int | None = None,
    mode: WalkForwardMode | str = WalkForwardMode.ROLLING,
    validation_kwargs: Mapping[str, Any] | None = None,
    name_prefix: str = "walk_forward",
) -> WalkForwardReport:
    windows = build_walk_forward_windows_from_frame(
        df=df,
        date_column=date_column,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        mode=mode,
        name_prefix=name_prefix,
    )

    return run_walk_forward_validation(
        df=df,
        windows=windows,
        validation_kwargs=validation_kwargs,
        date_column=date_column,
    )


def _derive_report_status(
    results: Iterable[WalkForwardWindowResult],
) -> WalkForwardReportStatus:
    result_tuple = tuple(results)

    if all(result.passed for result in result_tuple):
        return WalkForwardReportStatus.PASSED

    if all(result.insufficient_data for result in result_tuple):
        return WalkForwardReportStatus.INSUFFICIENT_DATA

    if all(result.failed or result.errored for result in result_tuple):
        return WalkForwardReportStatus.FAILED

    return WalkForwardReportStatus.MIXED


def _require_columns(
    df: pl.DataFrame,
    columns: Iterable[str],
    context: str,
) -> None:
    missing = [column for column in columns if column not in df.columns]

    if missing:
        raise ValueError(
            f"{context} missing required columns: {', '.join(missing)}"
        )


def _coerce_enum(value: Any, enum_type: type[Enum], field_name: str) -> Enum:
    if isinstance(value, enum_type):
        return value

    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(
            f"Invalid {field_name}: {value!r}. Allowed values: {allowed}"
        ) from exc
