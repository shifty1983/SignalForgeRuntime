from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Sequence


VALID_SEVERITIES = {"INFO", "WARN", "BLOCK", "FAIL"}


@dataclass(frozen=True)
class StaleDataRule:
    """
    Rule for checking whether a date-like column is too old.

    Example:
        StaleDataRule("date", max_age_days=3, severity="BLOCK")

    This means the most recent valid date in the column must be no more than
    3 calendar days older than the as_of date.
    """

    column: str
    max_age_days: int
    severity: str = "WARN"
    required: bool = True
    description: str | None = None


@dataclass(frozen=True)
class StaleDataIssue:
    severity: str
    message: str
    column: str | None = None
    latest_date: date | None = None
    as_of: date | None = None
    age_days: int | None = None
    max_age_days: int | None = None


@dataclass(frozen=True)
class StaleDataResult:
    passed: bool
    total_rows: int
    issues: tuple[StaleDataIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[StaleDataIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[StaleDataIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


def _validate_severity(severity: str) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Expected one of {sorted(VALID_SEVERITIES)}."
        )


def _get_columns(df: Any) -> list[str]:
    if hasattr(df, "columns"):
        return list(df.columns)

    raise TypeError("Object does not expose a columns attribute.")


def _row_count(df: Any) -> int:
    if hasattr(df, "height"):
        return int(df.height)

    try:
        return len(df)
    except TypeError as exc:
        raise TypeError("Object does not expose a usable row count.") from exc


def _to_values(series: Any) -> list[Any]:
    if hasattr(series, "to_list"):
        return list(series.to_list())

    if hasattr(series, "tolist"):
        return list(series.tolist())

    return list(series)


def _coerce_to_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        cleaned = value.strip()

        if not cleaned:
            return None

        try:
            return datetime.fromisoformat(cleaned).date()
        except ValueError:
            pass

        try:
            return date.fromisoformat(cleaned[:10])
        except ValueError:
            return None

    if hasattr(value, "date"):
        try:
            converted = value.date()
            if isinstance(converted, date):
                return converted
        except Exception:
            return None

    return None


def _coerce_as_of(as_of: date | datetime | str | None) -> date:
    if as_of is None:
        return date.today()

    coerced = _coerce_to_date(as_of)

    if coerced is None:
        raise ValueError(f"Could not parse as_of date: {as_of!r}")

    return coerced


def check_stale_data(
    df: Any,
    rules: Sequence[StaleDataRule],
    *,
    as_of: date | datetime | str | None = None,
    empty_frame_severity: str = "FAIL",
    future_date_severity: str = "WARN",
) -> StaleDataResult:
    """
    Check dataframe-like input for stale date columns.

    This function does not update data. It only classifies freshness issues.
    """
    _validate_severity(empty_frame_severity)
    _validate_severity(future_date_severity)

    issues: list[StaleDataIssue] = []
    columns = set(_get_columns(df))
    total_rows = _row_count(df)
    as_of_date = _coerce_as_of(as_of)

    if total_rows == 0:
        issues.append(
            StaleDataIssue(
                severity=empty_frame_severity,
                message="Dataframe contains zero rows.",
                as_of=as_of_date,
            )
        )

        return StaleDataResult(
            passed=empty_frame_severity not in {"BLOCK", "FAIL"},
            total_rows=total_rows,
            issues=tuple(issues),
        )

    for rule in rules:
        _validate_severity(rule.severity)

        if rule.max_age_days < 0:
            raise ValueError(
                f"Invalid max_age_days for column '{rule.column}': "
                f"{rule.max_age_days}. Expected value >= 0."
            )

        if rule.column not in columns:
            if rule.required:
                issues.append(
                    StaleDataIssue(
                        severity="FAIL",
                        column=rule.column,
                        message=f"Required date column is missing: {rule.column}",
                        as_of=as_of_date,
                        max_age_days=rule.max_age_days,
                    )
                )

            continue

        values = _to_values(df[rule.column])
        dates = [
            coerced
            for coerced in (_coerce_to_date(value) for value in values)
            if coerced is not None
        ]

        if not dates:
            issues.append(
                StaleDataIssue(
                    severity=rule.severity,
                    column=rule.column,
                    message=f"Column '{rule.column}' contains no valid dates.",
                    as_of=as_of_date,
                    max_age_days=rule.max_age_days,
                )
            )
            continue

        latest_date = max(dates)
        age_days = (as_of_date - latest_date).days

        if age_days < 0:
            issues.append(
                StaleDataIssue(
                    severity=future_date_severity,
                    column=rule.column,
                    message=(
                        f"Column '{rule.column}' contains future-dated values. "
                        f"Latest date is {latest_date.isoformat()}, "
                        f"as_of date is {as_of_date.isoformat()}."
                    ),
                    latest_date=latest_date,
                    as_of=as_of_date,
                    age_days=age_days,
                    max_age_days=rule.max_age_days,
                )
            )
            continue

        if age_days > rule.max_age_days:
            description = f" {rule.description}" if rule.description else ""

            issues.append(
                StaleDataIssue(
                    severity=rule.severity,
                    column=rule.column,
                    message=(
                        f"Column '{rule.column}' is stale. Latest date is "
                        f"{latest_date.isoformat()}, age is {age_days} days, "
                        f"allowed max age is {rule.max_age_days} days.{description}"
                    ),
                    latest_date=latest_date,
                    as_of=as_of_date,
                    age_days=age_days,
                    max_age_days=rule.max_age_days,
                )
            )

    passed = not any(issue.severity in {"BLOCK", "FAIL"} for issue in issues)

    return StaleDataResult(
        passed=passed,
        total_rows=total_rows,
        issues=tuple(issues),
    )


def require_fresh_data(
    df: Any,
    rules: Sequence[StaleDataRule],
    *,
    as_of: date | datetime | str | None = None,
    empty_frame_severity: str = "FAIL",
    future_date_severity: str = "WARN",
) -> None:
    """
    Raise ValueError if stale data creates a BLOCK or FAIL condition.
    """
    result = check_stale_data(
        df=df,
        rules=rules,
        as_of=as_of,
        empty_frame_severity=empty_frame_severity,
        future_date_severity=future_date_severity,
    )

    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise ValueError(f"Stale data validation failed: {issue_messages}")


MARKET_DATA_STALENESS_RULES: tuple[StaleDataRule, ...] = (
    StaleDataRule(
        column="date",
        max_age_days=3,
        severity="BLOCK",
        description="Market data should usually be current within a few trading days.",
    ),
)


FEATURE_STALENESS_RULES: tuple[StaleDataRule, ...] = (
    StaleDataRule(
        column="date",
        max_age_days=3,
        severity="BLOCK",
        description="Features should not lag raw market data materially.",
    ),
)


SIGNAL_STALENESS_RULES: tuple[StaleDataRule, ...] = (
    StaleDataRule(
        column="date",
        max_age_days=3,
        severity="BLOCK",
        description="Signals should be regenerated when features update.",
    ),
)


OPTIONS_STALENESS_RULES: tuple[StaleDataRule, ...] = (
    StaleDataRule(
        column="date",
        max_age_days=1,
        severity="BLOCK",
        description="Options chains become stale quickly because IV, Greeks, and liquidity change intraday.",
    ),
)


MACRO_STALENESS_RULES: tuple[StaleDataRule, ...] = (
    StaleDataRule(
        column="date",
        max_age_days=45,
        severity="WARN",
        description="Macro series may update monthly or quarterly depending on the dataset.",
    ),
)


REPORT_STALENESS_RULES: tuple[StaleDataRule, ...] = (
    StaleDataRule(
        column="generated_at",
        max_age_days=7,
        severity="WARN",
        description="Reports should be regenerated periodically even if the pipeline is otherwise healthy.",
    ),
)
