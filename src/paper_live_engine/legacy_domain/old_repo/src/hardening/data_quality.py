from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Sequence

from src.hardening.missing_data import MissingDataRule, check_missing_data
from src.hardening.nan_checks import NaNCheckRule, check_nan_values
from src.hardening.schema_validation import SchemaSpec, validate_schema
from src.hardening.stale_data import StaleDataRule, check_stale_data


@dataclass(frozen=True)
class DataQualityConfig:
    name: str
    schema: SchemaSpec | None = None
    missing_rules: Sequence[MissingDataRule] = field(default_factory=tuple)
    nan_rules: Sequence[NaNCheckRule] = field(default_factory=tuple)
    staleness_rules: Sequence[StaleDataRule] = field(default_factory=tuple)
    allow_extra_columns: bool = True
    strict_dtypes: bool = True


@dataclass(frozen=True)
class DataQualityIssue:
    severity: str
    check_name: str
    message: str
    column: str | None = None
    expected: Any | None = None
    actual: Any | None = None


@dataclass(frozen=True)
class DataQualityResult:
    name: str
    passed: bool
    checks_run: tuple[str, ...]
    issues: tuple[DataQualityIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[DataQualityIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[DataQualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


def _to_quality_issue(*, check_name: str, issue: Any) -> DataQualityIssue:
    return DataQualityIssue(
        severity=getattr(issue, "severity", "FAIL"),
        check_name=check_name,
        message=getattr(issue, "message", str(issue)),
        column=getattr(issue, "column", None),
        expected=getattr(issue, "expected", None),
        actual=getattr(issue, "actual", None),
    )


def check_data_quality(
    df: Any,
    config: DataQualityConfig,
    *,
    as_of: date | datetime | str | None = None,
) -> DataQualityResult:
    """
    Run common data-quality checks against one dataframe-like object.

    This is the lightweight facade for:
        - schema validation
        - missing data
        - NaN / infinite values
        - staleness
    """
    checks_run: list[str] = []
    issues: list[DataQualityIssue] = []

    if config.schema is not None:
        checks_run.append("schema")

        result = validate_schema(
            df,
            config.schema,
            allow_extra_columns=config.allow_extra_columns,
            strict_dtypes=config.strict_dtypes,
        )

        for issue in result.issues:
            issues.append(_to_quality_issue(check_name="schema", issue=issue))

    if config.missing_rules:
        checks_run.append("missing_data")

        result = check_missing_data(df, config.missing_rules)

        for issue in result.issues:
            issues.append(_to_quality_issue(check_name="missing_data", issue=issue))

    if config.nan_rules:
        checks_run.append("nan_checks")

        result = check_nan_values(df, config.nan_rules)

        for issue in result.issues:
            issues.append(_to_quality_issue(check_name="nan_checks", issue=issue))

    if config.staleness_rules:
        checks_run.append("stale_data")

        result = check_stale_data(
            df,
            config.staleness_rules,
            as_of=as_of,
        )

        for issue in result.issues:
            issues.append(_to_quality_issue(check_name="stale_data", issue=issue))

    passed = not any(issue.severity in {"BLOCK", "FAIL"} for issue in issues)

    return DataQualityResult(
        name=config.name,
        passed=passed,
        checks_run=tuple(checks_run),
        issues=tuple(issues),
    )


def require_data_quality(
    df: Any,
    config: DataQualityConfig,
    *,
    as_of: date | datetime | str | None = None,
) -> None:
    """
    Raise if data quality has blocking or failing issues.
    """
    result = check_data_quality(df, config, as_of=as_of)

    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise ValueError(f"Data quality validation failed for {config.name}: {issue_messages}")
