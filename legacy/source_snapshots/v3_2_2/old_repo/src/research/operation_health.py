from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from src.research.model_quality_operation import (
    model_quality_failed,
    model_quality_failure_messages,
)
from src.research.operation_audit import (
    ResearchOperationAuditResult,
    audit_research_operation_log,
    audit_research_operation_records,
)


class ResearchOperationHealthStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class ResearchOperationHealthCheck:
    name: str
    passed: bool
    status: ResearchOperationHealthStatus
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchOperationHealthConfig:
    require_records: bool = True
    require_audit_passed: bool = False
    require_latest_passed: bool = True
    require_latest_promoted: bool = False
    min_pass_rate: float | None = None
    max_failures_allowed: int | None = None
    max_gate_failures_allowed: int | None = None
    min_promoted_records: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    require_latest_backtest_attached: bool = False
    require_latest_backtest_passed: bool = False
    require_latest_backtest_handoff_attached: bool = False
    require_latest_backtest_handoff_passed: bool = False
    max_backtest_handoff_failures_allowed: int | None = None
    require_latest_model_readiness_attached: bool = False
    require_latest_model_readiness_passed: bool = False
    max_model_readiness_failures_allowed: int | None = None
    max_model_readiness_warnings_allowed: int | None = None
    require_latest_model_quality_attached: bool = False
    require_latest_model_quality_passed: bool = False
    max_model_quality_failures_allowed: int | None = None
    require_latest_model_testing_attached: bool = False
    require_latest_model_testing_passed: bool = False
    max_model_testing_failures_allowed: int | None = None
    require_latest_experiment_regression_attached: bool = False
    require_latest_experiment_regression_passed: bool = False

    def __post_init__(self) -> None:
        if self.min_pass_rate is not None and not 0 <= self.min_pass_rate <= 1:
            raise ValueError("min_pass_rate must be between 0 and 1.")

        if self.max_failures_allowed is not None and self.max_failures_allowed < 0:
            raise ValueError("max_failures_allowed cannot be negative.")

        if (
            self.max_gate_failures_allowed is not None
            and self.max_gate_failures_allowed < 0
        ):
            raise ValueError("max_gate_failures_allowed cannot be negative.")

        if self.min_promoted_records is not None and self.min_promoted_records < 0:
            raise ValueError("min_promoted_records cannot be negative.")

        if (
            self.max_backtest_handoff_failures_allowed is not None
            and self.max_backtest_handoff_failures_allowed < 0
        ):
            raise ValueError(
                "max_backtest_handoff_failures_allowed cannot be negative."
            )

        if (
            self.max_model_readiness_failures_allowed is not None
            and self.max_model_readiness_failures_allowed < 0
        ):
            raise ValueError(
                "max_model_readiness_failures_allowed cannot be negative."
            )

        if (
            self.max_model_readiness_warnings_allowed is not None
            and self.max_model_readiness_warnings_allowed < 0
        ):
            raise ValueError(
                "max_model_readiness_warnings_allowed cannot be negative."
            )

        if (
            self.max_model_quality_failures_allowed is not None
            and self.max_model_quality_failures_allowed < 0
        ):
            raise ValueError(
                "max_model_quality_failures_allowed cannot be negative."
            )

        if (
            self.max_model_testing_failures_allowed is not None
            and self.max_model_testing_failures_allowed < 0
        ):
            raise ValueError(
                "max_model_testing_failures_allowed cannot be negative."
            )

        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ResearchOperationHealthResult:
    checks: tuple[ResearchOperationHealthCheck, ...]
    audit_result: ResearchOperationAuditResult
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(
            check.status == ResearchOperationHealthStatus.FAIL
            for check in self.checks
        )

    @property
    def failures(self) -> tuple[ResearchOperationHealthCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status == ResearchOperationHealthStatus.FAIL
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "status": check.status.value,
                    "message": check.message,
                    "details": dict(check.details),
                }
                for check in self.checks
            ],
            "audit": self.audit_result.to_dict(),
            "metadata": dict(self.metadata),
        }


class ResearchOperationHealthError(ValueError):
    """Raised when research operation health checks fail."""


def evaluate_research_operation_health(
    audit_result: ResearchOperationAuditResult,
    config: ResearchOperationHealthConfig | None = None,
) -> ResearchOperationHealthResult:
    config = config or ResearchOperationHealthConfig()
    checks: list[ResearchOperationHealthCheck] = []

    checks.append(
        _build_check(
            name="records_present",
            passed=not config.require_records or audit_result.total_records > 0,
            pass_message="Research operation records are present.",
            fail_message="Research operation records are required but missing.",
            details={
                "require_records": config.require_records,
                "total_records": audit_result.total_records,
            },
        )
    )

    if config.require_audit_passed:
        checks.append(
            _build_check(
                name="audit_passed",
                passed=audit_result.passed,
                pass_message="Research operation audit passed.",
                fail_message="Research operation audit failed.",
                details={"audit_passed": audit_result.passed},
            )
        )

    if config.require_latest_passed:
        latest_status = (
            audit_result.latest_record.get("status")
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="latest_run_passed",
                passed=latest_status == "pass",
                pass_message="Latest research operation run passed.",
                fail_message="Latest research operation run did not pass.",
                details={"latest_status": latest_status},
            )
        )

    if config.require_latest_promoted:
        latest_promoted = (
            audit_result.latest_record.get("evaluation_promoted")
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="latest_run_promoted",
                passed=latest_promoted is True,
                pass_message="Latest research operation run was promoted.",
                fail_message="Latest research operation run was not promoted.",
                details={"latest_promoted": latest_promoted},
            )
        )

    if config.require_latest_backtest_attached:
        latest_backtest_attached = (
            audit_result.latest_record.get("backtest_report_attached")
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="latest_backtest_attached",
                passed=latest_backtest_attached is True,
                pass_message="Latest research operation has a backtest report attached.",
                fail_message="Latest research operation does not have a backtest report attached.",
                details={
                    "latest_backtest_attached": latest_backtest_attached,
                },
            )
        )

    if config.require_latest_backtest_passed:
        latest_backtest_passed = (
            audit_result.latest_record.get("backtest_attachment_passed")
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="latest_backtest_passed",
                passed=latest_backtest_passed is True,
                pass_message="Latest research operation backtest attachment passed.",
                fail_message="Latest research operation backtest attachment did not pass.",
                details={
                    "latest_backtest_passed": latest_backtest_passed,
                },
            )
        )

    latest_backtest_handoff_summary = _latest_backtest_handoff_summary(
        audit_result
    )
    latest_backtest_handoff_failures = _backtest_handoff_failures(
        latest_backtest_handoff_summary
    )
    latest_backtest_handoff_failed = _backtest_handoff_failed(
        latest_backtest_handoff_summary
    )

    if latest_backtest_handoff_failed:
        checks.append(
            _build_check(
                name="latest_backtest_handoff_failures",
                passed=False,
                pass_message="Latest research operation backtest handoff passed.",
                fail_message=(
                    "Latest research operation backtest handoff failed: "
                    + ", ".join(latest_backtest_handoff_failures)
                ),
                details={
                    "backtest_handoff_summary": latest_backtest_handoff_summary,
                    "backtest_handoff_failures": list(
                        latest_backtest_handoff_failures
                    ),
                },
            )
        )

    if config.require_latest_backtest_handoff_attached:
        checks.append(
            _build_check(
                name="latest_backtest_handoff_attached",
                passed=latest_backtest_handoff_summary is not None,
                pass_message="Latest research operation has a backtest handoff summary attached.",
                fail_message="Latest research operation does not have a backtest handoff summary attached.",
                details={
                    "latest_backtest_handoff_attached": latest_backtest_handoff_summary
                    is not None,
                },
            )
        )

    if config.require_latest_backtest_handoff_passed:
        latest_backtest_handoff_passed = _backtest_handoff_passed(
            latest_backtest_handoff_summary,
            latest_backtest_handoff_failures,
        )

        checks.append(
            _build_check(
                name="latest_backtest_handoff_passed",
                passed=latest_backtest_handoff_passed,
                pass_message="Latest research operation backtest handoff passed.",
                fail_message="Latest research operation backtest handoff did not pass.",
                details={
                    "latest_backtest_handoff_passed": latest_backtest_handoff_passed,
                    "backtest_handoff_failures": list(
                        latest_backtest_handoff_failures
                    ),
                },
            )
        )

    if config.max_backtest_handoff_failures_allowed is not None:
        backtest_handoff_failure_count = len(latest_backtest_handoff_failures)

        checks.append(
            _build_check(
                name="max_backtest_handoff_failures_allowed",
                passed=(
                    latest_backtest_handoff_summary is not None
                    and backtest_handoff_failure_count
                    <= config.max_backtest_handoff_failures_allowed
                ),
                pass_message="Latest backtest handoff failure count is within requirement.",
                fail_message="Latest backtest handoff failure count exceeds requirement.",
                details={
                    "backtest_handoff_failure_count": backtest_handoff_failure_count,
                    "backtest_handoff_failures": list(
                        latest_backtest_handoff_failures
                    ),
                    "max_backtest_handoff_failures_allowed": config.max_backtest_handoff_failures_allowed,
                },
            )
        )

    if config.require_latest_model_readiness_attached:
        latest_model_readiness_attached = (
            audit_result.latest_record.get("model_readiness_attached")
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="latest_model_readiness_attached",
                passed=latest_model_readiness_attached is True,
                pass_message="Latest research operation has a model readiness report attached.",
                fail_message="Latest research operation does not have a model readiness report attached.",
                details={
                    "latest_model_readiness_attached": latest_model_readiness_attached,
                },
            )
        )

    if config.require_latest_model_readiness_passed:
        latest_model_readiness_passed = (
            audit_result.latest_record.get("model_readiness_passed")
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="latest_model_readiness_passed",
                passed=latest_model_readiness_passed is True,
                pass_message="Latest research operation model readiness passed.",
                fail_message="Latest research operation model readiness did not pass.",
                details={
                    "latest_model_readiness_passed": latest_model_readiness_passed,
                },
            )
        )

    if config.max_model_readiness_failures_allowed is not None:
        latest_model_readiness_failure_count = (
            int(
                audit_result.latest_record.get(
                    "model_readiness_failure_count",
                    0,
                )
                or 0
            )
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="max_model_readiness_failures_allowed",
                passed=(
                    latest_model_readiness_failure_count is not None
                    and latest_model_readiness_failure_count
                    <= config.max_model_readiness_failures_allowed
                ),
                pass_message="Latest model readiness failure count is within requirement.",
                fail_message="Latest model readiness failure count exceeds requirement.",
                details={
                    "model_readiness_failure_count": latest_model_readiness_failure_count,
                    "max_model_readiness_failures_allowed": config.max_model_readiness_failures_allowed,
                },
            )
        )

    if config.max_model_readiness_warnings_allowed is not None:
        latest_model_readiness_warning_count = (
            int(
                audit_result.latest_record.get(
                    "model_readiness_warning_count",
                    0,
                )
                or 0
            )
            if audit_result.latest_record is not None
            else None
        )

        checks.append(
            _build_check(
                name="max_model_readiness_warnings_allowed",
                passed=(
                    latest_model_readiness_warning_count is not None
                    and latest_model_readiness_warning_count
                    <= config.max_model_readiness_warnings_allowed
                ),
                pass_message="Latest model readiness warning count is within requirement.",
                fail_message="Latest model readiness warning count exceeds requirement.",
                details={
                    "model_readiness_warning_count": latest_model_readiness_warning_count,
                    "max_model_readiness_warnings_allowed": config.max_model_readiness_warnings_allowed,
                },
            )
        )

    latest_model_quality_summary = _latest_model_quality_summary(audit_result)
    latest_model_quality_failures = _latest_model_quality_failure_messages(
        audit_result
    )
    latest_model_quality_failed = (
        model_quality_failed(latest_model_quality_summary)
        or bool(latest_model_quality_failures)
    )

    if latest_model_quality_failed:
        prefixed_failures = _prefixed_model_quality_failures(
            latest_model_quality_failures
        )
        checks.append(
            _build_check(
                name="latest_model_quality_failures",
                passed=False,
                pass_message="Latest research operation model quality passed.",
                fail_message=(
                    "Latest research operation model quality failed: "
                    + ", ".join(prefixed_failures)
                ),
                details={
                    "model_quality_summary": latest_model_quality_summary,
                    "model_quality_failures": prefixed_failures,
                },
            )
        )

    if config.require_latest_model_quality_attached:
        checks.append(
            _build_check(
                name="latest_model_quality_attached",
                passed=latest_model_quality_summary is not None,
                pass_message="Latest research operation has a model quality report attached.",
                fail_message="Latest research operation does not have a model quality report attached.",
                details={
                    "latest_model_quality_attached": latest_model_quality_summary is not None,
                },
            )
        )

    if config.require_latest_model_quality_passed:
        latest_model_quality_passed = (
            latest_model_quality_summary.get("passed")
            if latest_model_quality_summary is not None
            else None
        )

        checks.append(
            _build_check(
                name="latest_model_quality_passed",
                passed=(
                    latest_model_quality_summary is not None
                    and latest_model_quality_passed is True
                    and not latest_model_quality_failed
                ),
                pass_message="Latest research operation model quality passed.",
                fail_message="Latest research operation model quality did not pass.",
                details={
                    "latest_model_quality_passed": latest_model_quality_passed,
                    "model_quality_failures": _prefixed_model_quality_failures(
                        latest_model_quality_failures
                    ),
                },
            )
        )

    if config.max_model_quality_failures_allowed is not None:
        model_quality_failure_count = len(latest_model_quality_failures)

        checks.append(
            _build_check(
                name="max_model_quality_failures_allowed",
                passed=(
                    latest_model_quality_summary is not None
                    and model_quality_failure_count
                    <= config.max_model_quality_failures_allowed
                ),
                pass_message="Latest model quality failure count is within requirement.",
                fail_message="Latest model quality failure count exceeds requirement.",
                details={
                    "model_quality_failure_count": model_quality_failure_count,
                    "model_quality_failures": _prefixed_model_quality_failures(
                        latest_model_quality_failures
                    ),
                    "max_model_quality_failures_allowed": config.max_model_quality_failures_allowed,
                },
            )
        )

    latest_model_testing_summary = _latest_model_testing_summary(audit_result)
    latest_model_testing_failures = _model_testing_failures(
        latest_model_testing_summary
    )

    if latest_model_testing_summary is not None and latest_model_testing_failures:
        checks.append(
            _build_check(
                name="latest_model_testing_failures",
                passed=False,
                pass_message="Latest research operation model testing passed.",
                fail_message=(
                    "Latest research operation model testing failed: "
                    + ", ".join(latest_model_testing_failures)
                ),
                details={
                    "model_testing_summary": latest_model_testing_summary,
                    "model_testing_failures": list(latest_model_testing_failures),
                },
            )
        )


    
    if config.require_latest_model_testing_attached:
        checks.append(
            _build_check(
                name="latest_model_testing_attached",
                passed=latest_model_testing_summary is not None,
                pass_message="Latest research operation has a model testing summary attached.",
                fail_message="Latest research operation does not have a model testing summary attached.",
                details={
                    "latest_model_testing_attached": latest_model_testing_summary is not None,
                },
            )
        )

    if config.require_latest_model_testing_passed:
        latest_model_testing_passed = _model_testing_passed(
            latest_model_testing_summary,
            latest_model_testing_failures,
        )

        checks.append(
            _build_check(
                name="latest_model_testing_passed",
                passed=latest_model_testing_passed,
                pass_message="Latest research operation model testing passed.",
                fail_message="Latest research operation model testing did not pass.",
                details={
                    "latest_model_testing_passed": latest_model_testing_passed,
                    "model_testing_failures": list(latest_model_testing_failures),
                },
            )
        )

    if config.max_model_testing_failures_allowed is not None:
        model_testing_failure_count = len(latest_model_testing_failures)

        checks.append(
            _build_check(
                name="max_model_testing_failures_allowed",
                passed=(
                    latest_model_testing_summary is not None
                    and model_testing_failure_count
                    <= config.max_model_testing_failures_allowed
                ),
                pass_message="Latest model testing failure count is within requirement.",
                fail_message="Latest model testing failure count exceeds requirement.",
                details={
                    "model_testing_failure_count": model_testing_failure_count,
                    "model_testing_failures": list(latest_model_testing_failures),
                    "max_model_testing_failures_allowed": config.max_model_testing_failures_allowed,
                },
            )
        )

    latest_experiment_regression_report = _latest_experiment_regression_report(
        audit_result
    )
    latest_experiment_regression_failed = _experiment_regression_failed(
        latest_experiment_regression_report
    )
    latest_experiment_regression_failures = _experiment_regression_failures(
        latest_experiment_regression_report
    )

    if latest_experiment_regression_failed:
        checks.append(
            _build_check(
                name="latest_experiment_regression_failures",
                passed=False,
                pass_message="Latest research operation experiment regression passed.",
                fail_message=(
                    "Latest research operation experiment regression failed: "
                    + ", ".join(latest_experiment_regression_failures)
                ),
                details={
                    "experiment_regression_report": latest_experiment_regression_report,
                    "experiment_regression_failures": list(
                        latest_experiment_regression_failures
                    ),
                },
            )
        )

    if config.require_latest_experiment_regression_attached:
        checks.append(
            _build_check(
                name="latest_experiment_regression_attached",
                passed=latest_experiment_regression_report is not None,
                pass_message="Latest research operation has an experiment regression report attached.",
                fail_message="Latest research operation does not have an experiment regression report attached.",
                details={
                    "latest_experiment_regression_attached": latest_experiment_regression_report
                    is not None,
                },
            )
        )

    if config.require_latest_experiment_regression_passed:
        latest_experiment_regression_passed = (
            latest_experiment_regression_report is not None
            and not latest_experiment_regression_failed
        )

        checks.append(
            _build_check(
                name="latest_experiment_regression_passed",
                passed=latest_experiment_regression_passed,
                pass_message="Latest research operation experiment regression passed.",
                fail_message="Latest research operation experiment regression did not pass.",
                details={
                    "latest_experiment_regression_passed": latest_experiment_regression_passed,
                    "experiment_regression_failures": list(
                        latest_experiment_regression_failures
                    ),
                },
            )
        )

    if config.min_pass_rate is not None:
        checks.append(
            _build_check(
                name="min_pass_rate",
                passed=audit_result.pass_rate >= config.min_pass_rate,
                pass_message="Research operation pass rate meets requirement.",
                fail_message="Research operation pass rate is below requirement.",
                details={
                    "pass_rate": audit_result.pass_rate,
                    "min_pass_rate": config.min_pass_rate,
                },
            )
        )

    if config.max_failures_allowed is not None:
        checks.append(
            _build_check(
                name="max_failures_allowed",
                passed=audit_result.fail_count <= config.max_failures_allowed,
                pass_message="Research operation failure count is within requirement.",
                fail_message="Research operation failure count exceeds requirement.",
                details={
                    "fail_count": audit_result.fail_count,
                    "max_failures_allowed": config.max_failures_allowed,
                },
            )
        )

    if config.max_gate_failures_allowed is not None:
        checks.append(
            _build_check(
                name="max_gate_failures_allowed",
                passed=(
                    audit_result.gate_failure_count
                    <= config.max_gate_failures_allowed
                ),
                pass_message="Research model gate failures are within requirement.",
                fail_message="Research model gate failures exceed requirement.",
                details={
                    "gate_failure_count": audit_result.gate_failure_count,
                    "max_gate_failures_allowed": config.max_gate_failures_allowed,
                },
            )
        )

    if config.min_promoted_records is not None:
        promoted_count = len(audit_result.promoted_records)

        checks.append(
            _build_check(
                name="min_promoted_records",
                passed=promoted_count >= config.min_promoted_records,
                pass_message="Promoted research operation count meets requirement.",
                fail_message="Promoted research operation count is below requirement.",
                details={
                    "promoted_count": promoted_count,
                    "min_promoted_records": config.min_promoted_records,
                },
            )
        )

    metadata = {
        "source": "research_operation_health",
        **dict(config.metadata),
    }

    return ResearchOperationHealthResult(
        checks=tuple(checks),
        audit_result=audit_result,
        metadata=metadata,
    )


def evaluate_research_operation_records_health(
    records: Sequence[Mapping[str, Any]],
    config: ResearchOperationHealthConfig | None = None,
) -> ResearchOperationHealthResult:
    audit_result = audit_research_operation_records(records)
    return evaluate_research_operation_health(
        audit_result=audit_result,
        config=config,
    )


def evaluate_research_operation_log_health(
    path: str,
    config: ResearchOperationHealthConfig | None = None,
) -> ResearchOperationHealthResult:
    audit_result = audit_research_operation_log(path)
    return evaluate_research_operation_health(
        audit_result=audit_result,
        config=config,
    )


def enforce_research_operation_health(
    health_result: ResearchOperationHealthResult,
) -> ResearchOperationHealthResult:
    if not health_result.passed:
        messages = "; ".join(check.message for check in health_result.failures)
        raise ResearchOperationHealthError(
            f"Research operation health gate failed: {messages}"
        )

    return health_result


def _latest_backtest_handoff_summary(
    audit_result: ResearchOperationAuditResult,
) -> dict[str, Any] | None:
    if audit_result.latest_record is None:
        return None

    summary = audit_result.latest_record.get("backtest_handoff_summary")

    if isinstance(summary, Mapping):
        return dict(summary)

    return None


def _backtest_handoff_failed(
    backtest_handoff_summary: Mapping[str, Any] | None,
) -> bool:
    if backtest_handoff_summary is None:
        return False

    return not _backtest_handoff_passed(
        backtest_handoff_summary,
        _backtest_handoff_failures(backtest_handoff_summary),
    )


def _backtest_handoff_passed(
    backtest_handoff_summary: Mapping[str, Any] | None,
    backtest_handoff_failures: Sequence[str],
) -> bool:
    if backtest_handoff_summary is None:
        return False

    if backtest_handoff_failures:
        return False

    if "passed" in backtest_handoff_summary:
        return backtest_handoff_summary.get("passed") is True

    return backtest_handoff_summary.get("status") == "passed"


def _backtest_handoff_failures(
    backtest_handoff_summary: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if backtest_handoff_summary is None:
        return ()

    explicit_failures = backtest_handoff_summary.get("failures")

    if isinstance(explicit_failures, str):
        return (explicit_failures,)

    if isinstance(explicit_failures, Sequence):
        return tuple(str(failure) for failure in explicit_failures)

    failure_reason = backtest_handoff_summary.get("failure_reason")

    if failure_reason:
        return (str(failure_reason),)

    if backtest_handoff_summary.get("status") == "failed":
        return ("backtest_handoff_failed",)

    return ()


def _latest_model_quality_summary(
    audit_result: ResearchOperationAuditResult,
) -> dict[str, Any] | None:
    if audit_result.latest_record is None:
        return None

    summary = audit_result.latest_record.get("model_quality_summary")

    if isinstance(summary, Mapping):
        return dict(summary)

    return None


def _latest_model_quality_failure_messages(
    audit_result: ResearchOperationAuditResult,
) -> list[str]:
    if audit_result.latest_record is None:
        return []

    summary = _latest_model_quality_summary(audit_result)
    messages = list(model_quality_failure_messages(summary))

    record_failures = audit_result.latest_record.get("model_quality_failures")

    if isinstance(record_failures, str):
        messages.append(record_failures)
    elif isinstance(record_failures, Sequence):
        messages.extend(str(failure) for failure in record_failures)

    if summary is not None and summary.get("passed") is False and not messages:
        messages.append("model_quality_failed")

    deduped: list[str] = []
    for message in messages:
        if message not in deduped:
            deduped.append(message)

    return deduped


def _prefixed_model_quality_failures(failures: Sequence[str]) -> list[str]:
    return [
        failure
        if str(failure).startswith("model_quality:")
        else f"model_quality:{failure}"
        for failure in failures
    ]


def _latest_model_testing_summary(
    audit_result: ResearchOperationAuditResult,
) -> dict[str, Any] | None:
    if audit_result.latest_record is None:
        return None

    summary = audit_result.latest_record.get("model_testing_summary")

    if isinstance(summary, Mapping):
        return dict(summary)

    return None


def _model_testing_passed(
    model_testing_summary: Mapping[str, object] | None,
    model_testing_failures: Sequence[str],
) -> bool:
    if model_testing_summary is None:
        return False

    return (
        not model_testing_failures
        and model_testing_summary.get("has_promoted_candidate") is True
        and bool(model_testing_summary.get("best_candidate_id"))
    )


def _latest_experiment_regression_report(
    audit_result: ResearchOperationAuditResult,
) -> dict[str, Any] | None:
    if audit_result.latest_record is None:
        return None

    report = audit_result.latest_record.get("experiment_regression_report")

    if isinstance(report, Mapping):
        return dict(report)

    return None


def _experiment_regression_failed(
    experiment_regression_report: Mapping[str, Any] | None,
) -> bool:
    if experiment_regression_report is None:
        return False

    return bool(experiment_regression_report.get("has_regression"))


def _experiment_regression_failures(
    experiment_regression_report: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if experiment_regression_report is None:
        return ()

    failed_checks = experiment_regression_report.get("failed_checks")

    if isinstance(failed_checks, str):
        return (failed_checks,)

    if isinstance(failed_checks, Sequence):
        return tuple(str(check) for check in failed_checks)

    if experiment_regression_report.get("has_regression") is True:
        return ("experiment_regression_detected",)

    return ()


def _build_check(
    name: str,
    passed: bool,
    pass_message: str,
    fail_message: str,
    details: Mapping[str, Any],
) -> ResearchOperationHealthCheck:
    return ResearchOperationHealthCheck(
        name=name,
        passed=passed,
        status=(
            ResearchOperationHealthStatus.PASS
            if passed
            else ResearchOperationHealthStatus.FAIL
        ),
        message=pass_message if passed else fail_message,
        details=dict(details),
    )


def _model_testing_failures(
    model_testing_summary: Mapping[str, object] | None,
) -> tuple[str, ...]:
    if model_testing_summary is None:
        return ()

    failures: list[str] = []

    candidate_count = model_testing_summary.get("candidate_count")
    promoted_candidate_count = model_testing_summary.get(
        "promoted_candidate_count"
    )
    best_candidate_id = model_testing_summary.get("best_candidate_id")
    has_promoted_candidate = model_testing_summary.get(
        "has_promoted_candidate"
    )

    if candidate_count == 0:
        failures.append("model_testing_no_candidates_evaluated")

    if promoted_candidate_count == 0:
        failures.append("model_testing_no_promoted_candidates")

    if has_promoted_candidate is False:
        failures.append("model_testing_has_no_promoted_candidate")

    if not best_candidate_id:
        failures.append("model_testing_missing_best_candidate")

    return tuple(failures)

