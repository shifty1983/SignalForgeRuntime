from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from src.hardening.missing_data import MissingDataRule, check_missing_data
from src.hardening.nan_checks import NaNCheckRule, check_nan_values
from src.hardening.optimizer_guards import (
    OptimizerGuardConfig,
    check_optimizer_guards,
)
from src.hardening.schema_validation import SchemaSpec, validate_schema
from src.hardening.stale_data import StaleDataRule, check_stale_data


VALID_SEVERITIES = {"INFO", "WARN", "BLOCK", "FAIL"}


class PipelineHealthError(RuntimeError):
    """Raised when pipeline health checks fail."""


@dataclass(frozen=True)
class LayerHealthConfig:
    """
    Configuration for validating one pipeline layer.

    dataframe_key:
        Key used when checking a mapping of pipeline artifacts.

    layer_name:
        Human-readable layer name.

    schema:
        Optional SchemaSpec for column/type validation.

    missing_rules:
        Optional missing data rules.

    nan_rules:
        Optional NaN / infinite value rules.

    staleness_rules:
        Optional stale data rules.

    optimizer_guard_config:
        Optional optimizer safety guard config.

    required:
        If True, missing dataframe input is a failure.
        If False, missing dataframe input is a warning.
    """

    dataframe_key: str
    layer_name: str
    schema: SchemaSpec | None = None
    missing_rules: Sequence[MissingDataRule] = field(default_factory=tuple)
    nan_rules: Sequence[NaNCheckRule] = field(default_factory=tuple)
    staleness_rules: Sequence[StaleDataRule] = field(default_factory=tuple)
    optimizer_guard_config: OptimizerGuardConfig | None = None
    required: bool = True
    allow_extra_columns: bool = True
    strict_dtypes: bool = True


@dataclass(frozen=True)
class PipelineHealthIssue:
    severity: str
    layer: str
    check_name: str
    message: str
    source: str | None = None
    column: str | None = None
    expected: Any | None = None
    actual: Any | None = None


@dataclass(frozen=True)
class LayerHealthResult:
    layer: str
    dataframe_key: str
    passed: bool
    checks_run: tuple[str, ...]
    issues: tuple[PipelineHealthIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[PipelineHealthIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[PipelineHealthIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


@dataclass(frozen=True)
class PipelineHealthResult:
    passed: bool
    total_layers: int
    failed_layers: int
    warning_layers: int
    layer_results: tuple[LayerHealthResult, ...]
    issues: tuple[PipelineHealthIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[PipelineHealthIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[PipelineHealthIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")

    @property
    def checks_run(self) -> int:
        return sum(len(result.checks_run) for result in self.layer_results)


def _validate_severity(severity: str) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Expected one of {sorted(VALID_SEVERITIES)}."
        )


def _to_pipeline_issue(
    *,
    layer: str,
    check_name: str,
    issue: Any,
    source: str,
) -> PipelineHealthIssue:
    severity = getattr(issue, "severity", "FAIL")
    _validate_severity(severity)

    return PipelineHealthIssue(
        severity=severity,
        layer=layer,
        check_name=check_name,
        message=getattr(issue, "message", str(issue)),
        source=source,
        column=getattr(issue, "column", None),
        expected=getattr(issue, "expected", None),
        actual=getattr(issue, "actual", None),
    )


def check_layer_health(
    df: Any,
    config: LayerHealthConfig,
    *,
    as_of: date | datetime | str | None = None,
) -> LayerHealthResult:
    """
    Run all configured hardening checks for a single layer.
    """
    issues: list[PipelineHealthIssue] = []
    checks_run: list[str] = []

    if config.schema is not None:
        checks_run.append("schema")

        schema_result = validate_schema(
            df,
            config.schema,
            allow_extra_columns=config.allow_extra_columns,
            strict_dtypes=config.strict_dtypes,
        )

        for issue in schema_result.issues:
            issues.append(
                _to_pipeline_issue(
                    layer=config.layer_name,
                    check_name="schema",
                    issue=issue,
                    source="schema_validation",
                )
            )

    if config.missing_rules:
        checks_run.append("missing_data")

        missing_result = check_missing_data(df, config.missing_rules)

        for issue in missing_result.issues:
            issues.append(
                _to_pipeline_issue(
                    layer=config.layer_name,
                    check_name="missing_data",
                    issue=issue,
                    source="missing_data",
                )
            )

    if config.nan_rules:
        checks_run.append("nan_checks")

        nan_result = check_nan_values(df, config.nan_rules)

        for issue in nan_result.issues:
            issues.append(
                _to_pipeline_issue(
                    layer=config.layer_name,
                    check_name="nan_checks",
                    issue=issue,
                    source="nan_checks",
                )
            )

    if config.staleness_rules:
        checks_run.append("stale_data")

        stale_result = check_stale_data(
            df,
            config.staleness_rules,
            as_of=as_of,
        )

        for issue in stale_result.issues:
            issues.append(
                _to_pipeline_issue(
                    layer=config.layer_name,
                    check_name="stale_data",
                    issue=issue,
                    source="stale_data",
                )
            )

    if config.optimizer_guard_config is not None:
        checks_run.append("optimizer_guards")

        optimizer_result = check_optimizer_guards(
            df,
            config.optimizer_guard_config,
        )

        for issue in optimizer_result.issues:
            issues.append(
                _to_pipeline_issue(
                    layer=config.layer_name,
                    check_name="optimizer_guards",
                    issue=issue,
                    source="optimizer_guards",
                )
            )

    passed = not any(issue.severity in {"BLOCK", "FAIL"} for issue in issues)

    return LayerHealthResult(
        layer=config.layer_name,
        dataframe_key=config.dataframe_key,
        passed=passed,
        checks_run=tuple(checks_run),
        issues=tuple(issues),
    )


def check_pipeline_health(
    artifacts: Mapping[str, Any],
    configs: Sequence[LayerHealthConfig],
    *,
    as_of: date | datetime | str | None = None,
) -> PipelineHealthResult:
    """
    Run hardening checks across multiple pipeline artifacts.

    Example:
        artifacts = {
            "market_data": market_df,
            "features": feature_df,
            "signals": signal_df,
            "optimizer_output": portfolio_df,
        }
    """
    layer_results: list[LayerHealthResult] = []
    all_issues: list[PipelineHealthIssue] = []

    for config in configs:
        if config.dataframe_key not in artifacts:
            severity = "FAIL" if config.required else "WARN"

            issue = PipelineHealthIssue(
                severity=severity,
                layer=config.layer_name,
                check_name="artifact_present",
                source="pipeline_health",
                message=f"Pipeline artifact is missing: {config.dataframe_key}",
                expected="present",
                actual="missing",
            )

            result = LayerHealthResult(
                layer=config.layer_name,
                dataframe_key=config.dataframe_key,
                passed=severity not in {"BLOCK", "FAIL"},
                checks_run=("artifact_present",),
                issues=(issue,),
            )

            layer_results.append(result)
            all_issues.append(issue)
            continue

        result = check_layer_health(
            artifacts[config.dataframe_key],
            config,
            as_of=as_of,
        )

        layer_results.append(result)
        all_issues.extend(result.issues)

    failed_layers = sum(1 for result in layer_results if result.failed)
    warning_layers = sum(1 for result in layer_results if result.warnings)
    passed = failed_layers == 0 and not any(
        issue.severity in {"BLOCK", "FAIL"} for issue in all_issues
    )

    return PipelineHealthResult(
        passed=passed,
        total_layers=len(layer_results),
        failed_layers=failed_layers,
        warning_layers=warning_layers,
        layer_results=tuple(layer_results),
        issues=tuple(all_issues),
    )


def require_pipeline_healthy(result: PipelineHealthResult) -> None:
    """
    Raise if pipeline health contains blocking or failing issues.
    """
    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise PipelineHealthError(f"Pipeline health validation failed: {issue_messages}")


def health_status_label(result: PipelineHealthResult) -> str:
    """
    Convert a health result into a simple status label.
    """
    if result.failed:
        return "FAIL"

    if result.warnings:
        return "WARN"

    return "PASS"
