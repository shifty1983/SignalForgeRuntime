from __future__ import annotations

import traceback as traceback_module
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence


VALID_SEVERITIES = {"INFO", "WARN", "BLOCK", "FAIL"}
VALID_ACTIONS = {"CONTINUE", "WARN", "SKIP", "RETRY", "BLOCK", "FAIL"}


class FailureHandlingError(RuntimeError):
    """Raised when a handled pipeline failure should stop execution."""


@dataclass(frozen=True)
class FailurePolicy:
    """
    Defines how to classify and handle a failure.

    severity:
        INFO  - informational only
        WARN  - suspicious but not blocking
        BLOCK - blocks downstream use
        FAIL  - invalid execution state

    action:
        CONTINUE - continue execution
        WARN     - continue with warning
        SKIP     - skip this operation
        RETRY    - retry before failing
        BLOCK    - block downstream use
        FAIL     - fail execution
    """

    name: str
    exception_types: tuple[type[BaseException], ...] = field(default_factory=lambda: (Exception,))
    severity: str = "FAIL"
    action: str = "FAIL"
    retryable: bool = False
    fallback_value: Any | None = None
    message: str | None = None


@dataclass(frozen=True)
class FailureIssue:
    severity: str
    message: str
    layer: str
    operation: str
    policy_name: str
    exception_type: str
    exception_message: str
    action: str
    retryable: bool
    attempt: int
    traceback: str | None = None


@dataclass(frozen=True)
class FailureHandlingResult:
    passed: bool
    layer: str
    operation: str
    attempts: int
    value: Any | None = None
    issues: tuple[FailureIssue, ...] = ()

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[FailureIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[FailureIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


@dataclass(frozen=True)
class FailureSummary:
    passed: bool
    total_operations: int
    failed_operations: int
    warning_operations: int
    issues: tuple[FailureIssue, ...]

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_issues(self) -> tuple[FailureIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity in {"BLOCK", "FAIL"}
        )

    @property
    def warnings(self) -> tuple[FailureIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARN")


DEFAULT_FAILURE_POLICIES: tuple[FailurePolicy, ...] = (
    FailurePolicy(
        name="value_error",
        exception_types=(ValueError,),
        severity="FAIL",
        action="FAIL",
        retryable=False,
    ),
    FailurePolicy(
        name="type_error",
        exception_types=(TypeError,),
        severity="FAIL",
        action="FAIL",
        retryable=False,
    ),
    FailurePolicy(
        name="file_not_found",
        exception_types=(FileNotFoundError,),
        severity="BLOCK",
        action="BLOCK",
        retryable=False,
    ),
    FailurePolicy(
        name="runtime_error",
        exception_types=(RuntimeError,),
        severity="BLOCK",
        action="BLOCK",
        retryable=False,
    ),
    FailurePolicy(
        name="generic_exception",
        exception_types=(Exception,),
        severity="FAIL",
        action="FAIL",
        retryable=False,
    ),
)


def _validate_severity(severity: str) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Expected one of {sorted(VALID_SEVERITIES)}."
        )


def _validate_action(action: str) -> None:
    if action not in VALID_ACTIONS:
        raise ValueError(
            f"Invalid action '{action}'. Expected one of {sorted(VALID_ACTIONS)}."
        )


def _validate_policy(policy: FailurePolicy) -> None:
    _validate_severity(policy.severity)
    _validate_action(policy.action)

    if not policy.exception_types:
        raise ValueError(f"FailurePolicy '{policy.name}' must define exception_types.")

    for exception_type in policy.exception_types:
        if not issubclass(exception_type, BaseException):
            raise TypeError(
                f"FailurePolicy '{policy.name}' has invalid exception type: "
                f"{exception_type!r}"
            )


def classify_exception(
    exc: BaseException,
    policies: Sequence[FailurePolicy] | None = None,
) -> FailurePolicy:
    """
    Match an exception to the first applicable failure policy.
    """
    active_policies = policies or DEFAULT_FAILURE_POLICIES

    for policy in active_policies:
        _validate_policy(policy)

        if isinstance(exc, policy.exception_types):
            return policy

    return FailurePolicy(
        name="unclassified_exception",
        exception_types=(Exception,),
        severity="FAIL",
        action="FAIL",
        retryable=False,
    )


def _issue_from_exception(
    exc: BaseException,
    *,
    policy: FailurePolicy,
    layer: str,
    operation: str,
    attempt: int,
    severity: str | None = None,
    include_traceback: bool = False,
) -> FailureIssue:
    selected_severity = severity or policy.severity
    _validate_severity(selected_severity)

    exception_type = type(exc).__name__
    exception_message = str(exc)

    message = policy.message or (
        f"{operation} failed with {exception_type}: {exception_message}"
    )

    traceback_text = traceback_module.format_exc() if include_traceback else None

    return FailureIssue(
        severity=selected_severity,
        message=message,
        layer=layer,
        operation=operation,
        policy_name=policy.name,
        exception_type=exception_type,
        exception_message=exception_message,
        action=policy.action,
        retryable=policy.retryable or policy.action == "RETRY",
        attempt=attempt,
        traceback=traceback_text,
    )


def execute_with_failure_handling(
    func: Callable[..., Any],
    *args: Any,
    layer: str = "unknown",
    operation_name: str | None = None,
    policies: Sequence[FailurePolicy] | None = None,
    max_attempts: int = 1,
    fallback_value: Any | None = None,
    raise_on_failure: bool = False,
    include_traceback: bool = False,
    **kwargs: Any,
) -> FailureHandlingResult:
    """
    Execute an operation and return a structured failure result instead of
    letting errors escape randomly.

    This is useful at layer boundaries:

        data ingestion
        feature generation
        signal generation
        optimizer execution
        report export
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1.")

    operation = operation_name or getattr(func, "__name__", "anonymous_operation")
    issues: list[FailureIssue] = []

    for attempt in range(1, max_attempts + 1):
        try:
            value = func(*args, **kwargs)

            return FailureHandlingResult(
                passed=True,
                layer=layer,
                operation=operation,
                attempts=attempt,
                value=value,
                issues=tuple(issues),
            )

        except Exception as exc:
            policy = classify_exception(exc, policies)
            retryable = policy.retryable or policy.action == "RETRY"
            can_retry = retryable and attempt < max_attempts

            if can_retry:
                issues.append(
                    _issue_from_exception(
                        exc,
                        policy=policy,
                        layer=layer,
                        operation=operation,
                        attempt=attempt,
                        severity="WARN",
                        include_traceback=include_traceback,
                    )
                )
                continue

            final_issue = _issue_from_exception(
                exc,
                policy=policy,
                layer=layer,
                operation=operation,
                attempt=attempt,
                include_traceback=include_traceback,
            )

            issues.append(final_issue)

            passed = final_issue.severity not in {"BLOCK", "FAIL"}
            selected_fallback = (
                policy.fallback_value
                if policy.fallback_value is not None
                else fallback_value
            )

            result = FailureHandlingResult(
                passed=passed,
                layer=layer,
                operation=operation,
                attempts=attempt,
                value=selected_fallback,
                issues=tuple(issues),
            )

            if raise_on_failure and result.failed:
                raise FailureHandlingError(
                    f"{operation} failed after {attempt} attempt(s): "
                    f"{final_issue.message}"
                ) from exc

            return result

    raise FailureHandlingError("Unexpected failure handling state reached.")


def require_success(result: FailureHandlingResult) -> None:
    """
    Raise if a failure-handling result contains a blocking or failing issue.
    """
    if result.failed:
        issue_messages = "; ".join(issue.message for issue in result.blocking_issues)
        raise FailureHandlingError(f"Operation failed: {issue_messages}")


def summarize_failure_results(
    results: Iterable[FailureHandlingResult],
) -> FailureSummary:
    """
    Combine multiple operation results into a single summary.
    """
    result_list = list(results)
    all_issues: list[FailureIssue] = []

    failed_operations = 0
    warning_operations = 0

    for result in result_list:
        all_issues.extend(result.issues)

        if result.failed:
            failed_operations += 1

        if result.warnings:
            warning_operations += 1

    passed = failed_operations == 0 and not any(
        issue.severity in {"BLOCK", "FAIL"} for issue in all_issues
    )

    return FailureSummary(
        passed=passed,
        total_operations=len(result_list),
        failed_operations=failed_operations,
        warning_operations=warning_operations,
        issues=tuple(all_issues),
    )


INGESTION_FAILURE_POLICIES: tuple[FailurePolicy, ...] = (
    FailurePolicy(
        name="missing_file",
        exception_types=(FileNotFoundError,),
        severity="BLOCK",
        action="BLOCK",
        retryable=False,
    ),
    FailurePolicy(
        name="temporary_ingestion_runtime_error",
        exception_types=(RuntimeError,),
        severity="BLOCK",
        action="RETRY",
        retryable=True,
    ),
    FailurePolicy(
        name="bad_ingestion_value",
        exception_types=(ValueError,),
        severity="FAIL",
        action="FAIL",
        retryable=False,
    ),
)


OPTIMIZER_FAILURE_POLICIES: tuple[FailurePolicy, ...] = (
    FailurePolicy(
        name="optimizer_infeasible",
        exception_types=(ValueError,),
        severity="BLOCK",
        action="BLOCK",
        retryable=False,
        message="Optimizer failed because the candidate set or constraints are infeasible.",
    ),
    FailurePolicy(
        name="optimizer_runtime_error",
        exception_types=(RuntimeError,),
        severity="BLOCK",
        action="BLOCK",
        retryable=False,
    ),
)


REPORTING_FAILURE_POLICIES: tuple[FailurePolicy, ...] = (
    FailurePolicy(
        name="report_export_failure",
        exception_types=(OSError, RuntimeError),
        severity="WARN",
        action="WARN",
        retryable=False,
    ),
    FailurePolicy(
        name="report_value_error",
        exception_types=(ValueError,),
        severity="FAIL",
        action="FAIL",
        retryable=False,
    ),
)
