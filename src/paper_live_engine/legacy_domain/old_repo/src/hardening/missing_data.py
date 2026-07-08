from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


VALID_SEVERITIES = {"INFO", "WARN", "BLOCK", "FAIL"}


@dataclass(frozen=True)
class MissingDataRule:
    """
    Rule for checking missing values in a single column.

    severity:
        INFO  - informational only
        WARN  - suspicious but not blocking
        BLOCK - blocks downstream usage
        FAIL  - invalid data

    max_missing_fraction:
        Maximum allowed missing fraction before the rule triggers.
        Example:
            0.0  means no missing values allowed.
            0.05 means up to 5% missing values allowed.
    """

    column: str
    severity: str = "WARN"
    max_missing_fraction: float = 0.0
    required: bool = True
    description: str | None = None


@dataclass(frozen=True)
class MissingDataIssue:
    severity: str
    message: str
    column: str | None = None
    missing_count: int | None = None
    total_count: int | None = None
    missing_fraction: float | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class MissingDataResult:
    passed: bool
    total_rows: int
    issues: tuple[MissingDataIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[MissingDataIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[MissingDataIssue, ...]:
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


def _missing_count_for_column(df: Any, column: str) -> int:
    """
    Supports Polars and most pandas-like dataframe objects.
    """
    series = df[column]

    if hasattr(series, "null_count"):
        return int(series.null_count())

    if hasattr(series, "isna"):
        return int(series.isna().sum())

    if hasattr(series, "is_null"):
        null_result = series.is_null()

        if hasattr(null_result, "sum"):
            return int(null_result.sum())

    return int(sum(value is None for value in series))


def check_missing_data(
    df: Any,
    rules: Sequence[MissingDataRule],
    *,
    empty_frame_severity: str = "FAIL",
) -> MissingDataResult:
    """
    Check dataframe-like input for missing values according to explicit rules.

    This function classifies missing data. It does not impute, drop, forward-fill,
    or otherwise modify data.
    """
    _validate_severity(empty_frame_severity)

    issues: list[MissingDataIssue] = []
    columns = set(_get_columns(df))
    total_rows = _row_count(df)

    if total_rows == 0:
        issues.append(
            MissingDataIssue(
                severity=empty_frame_severity,
                message="Dataframe contains zero rows.",
                total_count=0,
            )
        )

        return MissingDataResult(
            passed=empty_frame_severity not in {"BLOCK", "FAIL"},
            total_rows=total_rows,
            issues=tuple(issues),
        )

    for rule in rules:
        _validate_severity(rule.severity)

        if not 0.0 <= rule.max_missing_fraction <= 1.0:
            raise ValueError(
                f"Invalid max_missing_fraction for column '{rule.column}': "
                f"{rule.max_missing_fraction}. Expected value between 0.0 and 1.0."
            )

        if rule.column not in columns:
            if rule.required:
                issues.append(
                    MissingDataIssue(
                        severity="FAIL",
                        column=rule.column,
                        message=f"Required column is missing: {rule.column}",
                        missing_count=total_rows,
                        total_count=total_rows,
                        missing_fraction=1.0,
                        threshold=rule.max_missing_fraction,
                    )
                )

            continue

        missing_count = _missing_count_for_column(df, rule.column)
        missing_fraction = missing_count / total_rows

        if missing_fraction > rule.max_missing_fraction:
            description = f" {rule.description}" if rule.description else ""

            issues.append(
                MissingDataIssue(
                    severity=rule.severity,
                    column=rule.column,
                    message=(
                        f"Column '{rule.column}' missing fraction "
                        f"{missing_fraction:.2%} exceeds allowed threshold "
                        f"{rule.max_missing_fraction:.2%}.{description}"
                    ),
                    missing_count=missing_count,
                    total_count=total_rows,
                    missing_fraction=missing_fraction,
                    threshold=rule.max_missing_fraction,
                )
            )

    passed = not any(issue.severity in {"BLOCK", "FAIL"} for issue in issues)

    return MissingDataResult(
        passed=passed,
        total_rows=total_rows,
        issues=tuple(issues),
    )


def require_no_blocking_missing_data(
    df: Any,
    rules: Sequence[MissingDataRule],
    *,
    empty_frame_severity: str = "FAIL",
) -> None:
    """
    Raise ValueError if missing data creates a BLOCK or FAIL condition.
    """
    result = check_missing_data(
        df=df,
        rules=rules,
        empty_frame_severity=empty_frame_severity,
    )

    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise ValueError(f"Missing data validation failed: {issue_messages}")


MARKET_DATA_MISSING_RULES: tuple[MissingDataRule, ...] = (
    MissingDataRule("symbol", severity="FAIL"),
    MissingDataRule("date", severity="FAIL"),
    MissingDataRule("open", severity="BLOCK"),
    MissingDataRule("high", severity="BLOCK"),
    MissingDataRule("low", severity="BLOCK"),
    MissingDataRule("close", severity="FAIL"),
    MissingDataRule("volume", severity="WARN", max_missing_fraction=0.05),
)


FEATURE_MISSING_RULES: tuple[MissingDataRule, ...] = (
    MissingDataRule("symbol", severity="FAIL"),
    MissingDataRule("date", severity="FAIL"),
    MissingDataRule("return", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("returns", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("volatility", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("momentum", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("drawdown", severity="WARN", max_missing_fraction=0.05, required=False),
)


SIGNAL_MISSING_RULES: tuple[MissingDataRule, ...] = (
    MissingDataRule("symbol", severity="FAIL"),
    MissingDataRule("date", severity="FAIL"),
    MissingDataRule("signal", severity="FAIL"),
    MissingDataRule("score", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("confidence", severity="WARN", max_missing_fraction=0.10, required=False),
)


OPTIONS_MISSING_RULES: tuple[MissingDataRule, ...] = (
    MissingDataRule("symbol", severity="FAIL"),
    MissingDataRule("date", severity="FAIL"),
    MissingDataRule("expiration", severity="FAIL"),
    MissingDataRule("strike", severity="FAIL"),
    MissingDataRule("option_type", severity="FAIL"),
    MissingDataRule("bid", severity="BLOCK"),
    MissingDataRule("ask", severity="BLOCK"),
    MissingDataRule("implied_volatility", severity="BLOCK", required=False),
    MissingDataRule("delta", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("gamma", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("theta", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("vega", severity="WARN", max_missing_fraction=0.05, required=False),
)


OPTIMIZER_INPUT_MISSING_RULES: tuple[MissingDataRule, ...] = (
    MissingDataRule("candidate_id", severity="FAIL"),
    MissingDataRule("expected_return", severity="BLOCK", required=False),
    MissingDataRule("expected_value", severity="BLOCK", required=False),
    MissingDataRule("risk", severity="BLOCK", required=False),
    MissingDataRule("risk_score", severity="BLOCK", required=False),
    MissingDataRule("delta", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("gamma", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("theta", severity="WARN", max_missing_fraction=0.05, required=False),
    MissingDataRule("vega", severity="WARN", max_missing_fraction=0.05, required=False),
)
