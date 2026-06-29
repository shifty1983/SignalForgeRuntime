from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from math import isnan
from typing import Any

from src.pipeline.validation import (
    ValidationResult,
    ValidationSeverity,
    fail_result,
    pass_result,
)


PipelineCheck = Callable[[Any], ValidationResult]


def _named_check(check: PipelineCheck, check_name: str) -> PipelineCheck:
    check.__name__ = check_name
    return check


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _is_missing(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, float):
        return isnan(value)

    return False


def _row_count(data: Any) -> int | None:
    if data is None:
        return 0

    height = getattr(data, "height", None)
    if isinstance(height, int):
        return height

    shape = getattr(data, "shape", None)
    if isinstance(shape, tuple) and shape:
        return int(shape[0])

    try:
        return len(data)
    except TypeError:
        return None


def _columns(data: Any) -> tuple[str, ...]:
    columns = getattr(data, "columns", None)

    if columns is None:
        return ()

    return tuple(str(column) for column in columns)


def _missing_counts_from_mapping(
    data: Mapping[Any, Any],
    columns: tuple[str, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for column in columns:
        value = data.get(column)

        if _is_sequence(value):
            counts[column] = sum(1 for item in value if _is_missing(item))
        else:
            counts[column] = int(_is_missing(value))

    return counts


def _missing_counts_from_rows(
    rows: Sequence[Any],
    columns: tuple[str, ...],
) -> dict[str, int]:
    counts = {column: 0 for column in columns}

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        for column in columns:
            if _is_missing(row.get(column)):
                counts[column] += 1

    return counts


def _missing_counts_from_dataframe(
    data: Any,
    columns: tuple[str, ...],
) -> dict[str, int]:
    """
    Supports pandas-like and polars-like DataFrames without requiring either
    dependency directly.
    """

    if hasattr(data, "isna"):
        try:
            missing = data[list(columns)].isna().sum()
            return {column: int(missing[column]) for column in columns}
        except Exception:
            pass

    if hasattr(data, "null_count") and hasattr(data, "to_dicts"):
        try:
            null_counts = data.select(list(columns)).null_count().to_dicts()[0]
            counts = {column: int(null_counts[column]) for column in columns}

            try:
                import polars as pl

                for column in columns:
                    try:
                        nan_count = (
                            data.select(pl.col(column).is_nan().sum())
                            .to_series()
                            .item()
                        )
                        counts[column] += int(nan_count)
                    except Exception:
                        continue
            except Exception:
                pass

            return counts
        except Exception:
            pass

    return {}


def _missing_counts(
    data: Any,
    columns: tuple[str, ...],
) -> dict[str, int]:
    if isinstance(data, Mapping):
        return _missing_counts_from_mapping(data, columns)

    if _is_sequence(data):
        return _missing_counts_from_rows(data, columns)

    return _missing_counts_from_dataframe(data, columns)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    raise TypeError(f"Unsupported timestamp type: {type(value).__name__}")


def make_not_none_check(
    *,
    layer: str,
    check_name: str = "not_none_check",
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> PipelineCheck:
    def check(data: Any) -> ValidationResult:
        if data is None:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Payload is None.",
                severity=severity,
            )

        return pass_result(
            layer=layer,
            check_name=check_name,
            message="Payload is not None.",
        )

    return _named_check(check, check_name)


def make_non_empty_check(
    *,
    layer: str,
    check_name: str = "non_empty_check",
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> PipelineCheck:
    def check(data: Any) -> ValidationResult:
        size = _row_count(data)

        if size is None:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Could not determine whether payload is empty.",
                severity=ValidationSeverity.CRITICAL,
                metadata={"payload_type": type(data).__name__},
            )

        if size <= 0:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Payload is empty.",
                severity=severity,
                metadata={"row_count": size},
            )

        return pass_result(
            layer=layer,
            check_name=check_name,
            message="Payload is non-empty.",
            metadata={"row_count": size},
        )

    return _named_check(check, check_name)


def make_required_keys_check(
    *,
    layer: str,
    required_keys: Sequence[str],
    check_name: str = "required_keys_check",
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> PipelineCheck:
    expected_keys = tuple(required_keys)

    def check(data: Any) -> ValidationResult:
        if not isinstance(data, Mapping):
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Payload does not support key validation.",
                severity=ValidationSeverity.CRITICAL,
                metadata={"payload_type": type(data).__name__},
            )

        missing_keys = tuple(key for key in expected_keys if key not in data)

        if missing_keys:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Required keys are missing.",
                severity=severity,
                metadata={"missing_keys": missing_keys},
            )

        return pass_result(
            layer=layer,
            check_name=check_name,
            message="Required keys are present.",
            metadata={"required_keys": expected_keys},
        )

    return _named_check(check, check_name)


def make_required_columns_check(
    *,
    layer: str,
    required_columns: Sequence[str],
    check_name: str = "required_columns_check",
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> PipelineCheck:
    expected_columns = tuple(required_columns)

    def check(data: Any) -> ValidationResult:
        available_columns = _columns(data)

        if not available_columns:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Payload does not expose columns.",
                severity=ValidationSeverity.CRITICAL,
                metadata={"payload_type": type(data).__name__},
            )

        missing_columns = tuple(
            column for column in expected_columns if column not in available_columns
        )

        if missing_columns:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Required columns are missing.",
                severity=severity,
                metadata={
                    "missing_columns": missing_columns,
                    "available_columns": available_columns,
                },
            )

        return pass_result(
            layer=layer,
            check_name=check_name,
            message="Required columns are present.",
            metadata={"required_columns": expected_columns},
        )

    return _named_check(check, check_name)


def make_no_missing_values_check(
    *,
    layer: str,
    columns: Sequence[str] | None = None,
    check_name: str = "no_missing_values_check",
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> PipelineCheck:
    selected_columns = tuple(columns) if columns is not None else None

    def check(data: Any) -> ValidationResult:
        if selected_columns is None:
            if isinstance(data, Mapping):
                active_columns = tuple(str(key) for key in data.keys())
            elif _is_sequence(data) and data and isinstance(data[0], Mapping):
                active_columns = tuple(str(key) for key in data[0].keys())
            else:
                active_columns = _columns(data)
        else:
            active_columns = selected_columns

        if not active_columns:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Could not determine columns for missing value validation.",
                severity=ValidationSeverity.CRITICAL,
                metadata={"payload_type": type(data).__name__},
            )

        counts = _missing_counts(data, active_columns)
        total_missing = sum(counts.values())

        if total_missing > 0:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Missing values detected.",
                severity=severity,
                metadata={
                    "missing_count": total_missing,
                    "missing_by_column": counts,
                },
            )

        return pass_result(
            layer=layer,
            check_name=check_name,
            message="No missing values detected.",
            metadata={
                "missing_count": 0,
                "checked_columns": active_columns,
            },
        )

    return _named_check(check, check_name)


def make_timestamp_freshness_check(
    *,
    layer: str,
    timestamp_key: str,
    max_age: timedelta,
    check_name: str = "timestamp_freshness_check",
    severity: ValidationSeverity = ValidationSeverity.ERROR,
    now: datetime | None = None,
) -> PipelineCheck:
    def check(data: Any) -> ValidationResult:
        if isinstance(data, Mapping):
            timestamp_value = data.get(timestamp_key)
        else:
            timestamp_value = getattr(data, timestamp_key, None)

        if timestamp_value is None:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Freshness timestamp is missing.",
                severity=severity,
                metadata={"timestamp_key": timestamp_key},
            )

        try:
            timestamp = _coerce_datetime(timestamp_value)
        except Exception as error:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message=f"Freshness timestamp is invalid: {error}",
                severity=ValidationSeverity.CRITICAL,
                metadata={
                    "timestamp_key": timestamp_key,
                    "timestamp_type": type(timestamp_value).__name__,
                },
            )

        current_time = now or datetime.now(
            timestamp.tzinfo if timestamp.tzinfo is not None else timezone.utc
        )

        if timestamp.tzinfo is None and current_time.tzinfo is not None:
            current_time = current_time.replace(tzinfo=None)

        if timestamp.tzinfo is not None and current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        age = current_time - timestamp

        if age < timedelta(0):
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Freshness timestamp is in the future.",
                severity=severity,
                metadata={
                    "timestamp_key": timestamp_key,
                    "age_seconds": age.total_seconds(),
                },
            )

        if age > max_age:
            return fail_result(
                layer=layer,
                check_name=check_name,
                message="Payload is stale.",
                severity=severity,
                metadata={
                    "timestamp_key": timestamp_key,
                    "age_seconds": age.total_seconds(),
                    "max_age_seconds": max_age.total_seconds(),
                },
            )

        return pass_result(
            layer=layer,
            check_name=check_name,
            message="Payload is fresh.",
            metadata={
                "timestamp_key": timestamp_key,
                "age_seconds": age.total_seconds(),
                "max_age_seconds": max_age.total_seconds(),
            },
        )

    return _named_check(check, check_name)
