from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence


VALID_SEVERITIES = {"INFO", "WARN", "BLOCK", "FAIL"}


@dataclass(frozen=True)
class NaNCheckRule:
    """
    Rule for detecting NaN and infinite values in numeric columns.

    This is intentionally separate from missing data checks.

    Missing data:
        None / null

    Numeric anomalies:
        NaN
        inf
        -inf
    """

    column: str
    severity: str = "FAIL"
    max_nan_fraction: float = 0.0
    max_infinite_fraction: float = 0.0
    required: bool = True
    description: str | None = None


@dataclass(frozen=True)
class NaNCheckIssue:
    severity: str
    message: str
    column: str | None = None
    anomaly_type: str | None = None
    anomaly_count: int | None = None
    total_count: int | None = None
    anomaly_fraction: float | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class NaNCheckResult:
    passed: bool
    total_rows: int
    issues: tuple[NaNCheckIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[NaNCheckIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[NaNCheckIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


def _validate_severity(severity: str) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Expected one of {sorted(VALID_SEVERITIES)}."
        )


def _validate_fraction(value: float, field_name: str, column: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"Invalid {field_name} for column '{column}': {value}. "
            "Expected value between 0.0 and 1.0."
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


def _is_nan(value: Any) -> bool:
    if value is None:
        return False

    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        return False


def _is_infinite(value: Any) -> bool:
    if value is None:
        return False

    try:
        return bool(math.isinf(value))
    except (TypeError, ValueError):
        return False


def _count_nan_and_infinite(values: Sequence[Any]) -> tuple[int, int]:
    nan_count = 0
    infinite_count = 0

    for value in values:
        if _is_nan(value):
            nan_count += 1
        elif _is_infinite(value):
            infinite_count += 1

    return nan_count, infinite_count


def check_nan_values(
    df: Any,
    rules: Sequence[NaNCheckRule],
    *,
    empty_frame_severity: str = "FAIL",
) -> NaNCheckResult:
    """
    Check dataframe-like input for NaN and infinite values.

    This function does not repair data. It only classifies numeric anomalies.
    """
    _validate_severity(empty_frame_severity)

    issues: list[NaNCheckIssue] = []
    columns = set(_get_columns(df))
    total_rows = _row_count(df)

    if total_rows == 0:
        issues.append(
            NaNCheckIssue(
                severity=empty_frame_severity,
                message="Dataframe contains zero rows.",
                total_count=0,
            )
        )

        return NaNCheckResult(
            passed=empty_frame_severity not in {"BLOCK", "FAIL"},
            total_rows=total_rows,
            issues=tuple(issues),
        )

    for rule in rules:
        _validate_severity(rule.severity)
        _validate_fraction(rule.max_nan_fraction, "max_nan_fraction", rule.column)
        _validate_fraction(
            rule.max_infinite_fraction,
            "max_infinite_fraction",
            rule.column,
        )

        if rule.column not in columns:
            if rule.required:
                issues.append(
                    NaNCheckIssue(
                        severity="FAIL",
                        column=rule.column,
                        anomaly_type="missing_column",
                        message=f"Required column is missing: {rule.column}",
                        anomaly_count=total_rows,
                        total_count=total_rows,
                        anomaly_fraction=1.0,
                        threshold=0.0,
                    )
                )

            continue

        values = _to_values(df[rule.column])
        nan_count, infinite_count = _count_nan_and_infinite(values)

        nan_fraction = nan_count / total_rows
        infinite_fraction = infinite_count / total_rows

        if nan_fraction > rule.max_nan_fraction:
            description = f" {rule.description}" if rule.description else ""

            issues.append(
                NaNCheckIssue(
                    severity=rule.severity,
                    column=rule.column,
                    anomaly_type="nan",
                    message=(
                        f"Column '{rule.column}' NaN fraction "
                        f"{nan_fraction:.2%} exceeds allowed threshold "
                        f"{rule.max_nan_fraction:.2%}.{description}"
                    ),
                    anomaly_count=nan_count,
                    total_count=total_rows,
                    anomaly_fraction=nan_fraction,
                    threshold=rule.max_nan_fraction,
                )
            )

        if infinite_fraction > rule.max_infinite_fraction:
            description = f" {rule.description}" if rule.description else ""

            issues.append(
                NaNCheckIssue(
                    severity=rule.severity,
                    column=rule.column,
                    anomaly_type="infinite",
                    message=(
                        f"Column '{rule.column}' infinite fraction "
                        f"{infinite_fraction:.2%} exceeds allowed threshold "
                        f"{rule.max_infinite_fraction:.2%}.{description}"
                    ),
                    anomaly_count=infinite_count,
                    total_count=total_rows,
                    anomaly_fraction=infinite_fraction,
                    threshold=rule.max_infinite_fraction,
                )
            )

    passed = not any(issue.severity in {"BLOCK", "FAIL"} for issue in issues)

    return NaNCheckResult(
        passed=passed,
        total_rows=total_rows,
        issues=tuple(issues),
    )


def require_no_nan_failures(
    df: Any,
    rules: Sequence[NaNCheckRule],
    *,
    empty_frame_severity: str = "FAIL",
) -> None:
    """
    Raise ValueError if NaN or infinite values create a BLOCK or FAIL condition.
    """
    result = check_nan_values(
        df=df,
        rules=rules,
        empty_frame_severity=empty_frame_severity,
    )

    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise ValueError(f"NaN validation failed: {issue_messages}")


FEATURE_NAN_RULES: tuple[NaNCheckRule, ...] = (
    NaNCheckRule("return", severity="WARN", required=False),
    NaNCheckRule("returns", severity="WARN", required=False),
    NaNCheckRule("volatility", severity="WARN", required=False),
    NaNCheckRule("momentum", severity="WARN", required=False),
    NaNCheckRule("drawdown", severity="WARN", required=False),
    NaNCheckRule("moving_average", severity="WARN", required=False),
    NaNCheckRule("z_score", severity="WARN", required=False),
    NaNCheckRule("rank", severity="WARN", required=False),
)


SIGNAL_NAN_RULES: tuple[NaNCheckRule, ...] = (
    NaNCheckRule("signal", severity="FAIL"),
    NaNCheckRule("score", severity="BLOCK", required=False),
    NaNCheckRule("confidence", severity="WARN", required=False),
    NaNCheckRule("rank", severity="WARN", required=False),
)


EXPECTED_VALUE_NAN_RULES: tuple[NaNCheckRule, ...] = (
    NaNCheckRule("expected_value", severity="FAIL", required=False),
    NaNCheckRule("expected_return", severity="FAIL", required=False),
    NaNCheckRule("probability", severity="BLOCK", required=False),
    NaNCheckRule("payoff", severity="BLOCK", required=False),
    NaNCheckRule("risk_reward", severity="BLOCK", required=False),
    NaNCheckRule("opportunity_score", severity="BLOCK", required=False),
)


OPTIONS_NAN_RULES: tuple[NaNCheckRule, ...] = (
    NaNCheckRule("bid", severity="BLOCK", required=False),
    NaNCheckRule("ask", severity="BLOCK", required=False),
    NaNCheckRule("mid", severity="BLOCK", required=False),
    NaNCheckRule("implied_volatility", severity="BLOCK", required=False),
    NaNCheckRule("delta", severity="WARN", required=False),
    NaNCheckRule("gamma", severity="WARN", required=False),
    NaNCheckRule("theta", severity="WARN", required=False),
    NaNCheckRule("vega", severity="WARN", required=False),
)


OPTIMIZER_NAN_RULES: tuple[NaNCheckRule, ...] = (
    NaNCheckRule("expected_return", severity="BLOCK", required=False),
    NaNCheckRule("expected_value", severity="BLOCK", required=False),
    NaNCheckRule("risk", severity="BLOCK", required=False),
    NaNCheckRule("risk_score", severity="BLOCK", required=False),
    NaNCheckRule("weight", severity="FAIL", required=False),
    NaNCheckRule("delta", severity="WARN", required=False),
    NaNCheckRule("gamma", severity="WARN", required=False),
    NaNCheckRule("theta", severity="WARN", required=False),
    NaNCheckRule("vega", severity="WARN", required=False),
)
