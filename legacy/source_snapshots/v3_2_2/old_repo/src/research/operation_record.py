from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from src.research.model_quality_operation import (
    build_model_quality_operation_summary,
    model_quality_failure_messages,
)


class ResearchOperationRecordStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class ResearchOperationRecordConfig:
    operation_name: str = "research_evaluation_operation"
    run_id: str | None = None
    require_run_id: bool = False
    include_summary: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation_name:
            raise ValueError("operation_name cannot be empty.")

        if self.require_run_id and not self.run_id:
            raise ValueError("run_id is required when require_run_id=True.")

        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ResearchOperationRecord:
    operation_name: str
    status: ResearchOperationRecordStatus
    passed: bool
    run_id: str | None = None
    evaluation_decision: str | None = None
    evaluation_promoted: bool | None = None
    model_operation_status: str | None = None
    model_test_passed: bool | None = None
    model_gate_passed: bool | None = None
    model_gate_failure_count: int = 0
    model_gate_warning_count: int = 0
    portfolio_target_rows: int = 0
    backtest_input_rows: int = 0
    daily_return_rows: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    summary_payload: Mapping[str, Any] | None = None
    backtest_report_attached: bool = False
    backtest_attachment_passed: bool | None = None
    backtest_nav_rows: int = 0
    backtest_exposure_rows: int = 0
    backtest_trade_count: int = 0
    backtest_rebalance_count: int = 0
    backtest_start_value: float | None = None
    backtest_final_value: float | None = None
    backtest_total_return: float | None = None
    backtest_handoff_summary: Mapping[str, Any] | None = None
    model_readiness_attached: bool = False
    model_readiness_passed: bool | None = None
    model_readiness_failure_count: int = 0
    model_readiness_warning_count: int = 0
    model_quality_summary: dict[str, object] | None = None
    model_quality_failures: list[str] | None = None
    model_testing_summary: Mapping[str, Any] | None = None
    experiment_regression_report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "operation_name": self.operation_name,
            "run_id": self.run_id,
            "status": self.status.value,
            "passed": self.passed,
            "evaluation_decision": self.evaluation_decision,
            "evaluation_promoted": self.evaluation_promoted,
            "model_operation_status": self.model_operation_status,
            "model_test_passed": self.model_test_passed,
            "model_gate_passed": self.model_gate_passed,
            "model_gate_failure_count": self.model_gate_failure_count,
            "model_gate_warning_count": self.model_gate_warning_count,
            "portfolio_target_rows": self.portfolio_target_rows,
            "backtest_input_rows": self.backtest_input_rows,
            "daily_return_rows": self.daily_return_rows,
            "metadata": dict(self.metadata),
            "backtest_report_attached": self.backtest_report_attached,
            "backtest_attachment_passed": self.backtest_attachment_passed,
            "backtest_nav_rows": self.backtest_nav_rows,
            "backtest_exposure_rows": self.backtest_exposure_rows,
            "backtest_trade_count": self.backtest_trade_count,
            "backtest_rebalance_count": self.backtest_rebalance_count,
            "backtest_start_value": self.backtest_start_value,
            "backtest_final_value": self.backtest_final_value,
            "backtest_total_return": self.backtest_total_return,
            "backtest_handoff_summary": (
                dict(self.backtest_handoff_summary)
                if self.backtest_handoff_summary is not None
                else None
            ),
            "backtest_handoff_attached": self.backtest_handoff_summary is not None,
            "backtest_handoff_passed": _backtest_handoff_passed(
                self.backtest_handoff_summary
            ),
            "backtest_handoff_failure_count": _backtest_handoff_failure_count(
                self.backtest_handoff_summary
            ),
            "backtest_handoff_failures": _backtest_handoff_failures(
                self.backtest_handoff_summary
            ),
            "backtest_handoff_fixture_id": _backtest_handoff_value(
                self.backtest_handoff_summary,
                "fixture_id",
            ),
            "backtest_handoff_candidate_id": _backtest_handoff_value(
                self.backtest_handoff_summary,
                "candidate_id",
            ),
            "backtest_handoff_performance": _backtest_handoff_performance(
                self.backtest_handoff_summary
            ),
            "model_readiness_attached": self.model_readiness_attached,
            "model_readiness_passed": self.model_readiness_passed,
            "model_readiness_failure_count": self.model_readiness_failure_count,
            "model_readiness_warning_count": self.model_readiness_warning_count,
            "model_quality_summary": (
                dict(self.model_quality_summary)
                if self.model_quality_summary is not None
                else None
            ),
            "model_quality_failures": list(self.model_quality_failures or []),
            "model_testing_summary": (
                dict(self.model_testing_summary)
                if self.model_testing_summary is not None
                else None
            ),
            "experiment_regression_report": (
                dict(self.experiment_regression_report)
                if self.experiment_regression_report is not None
                else None
            ),
            "experiment_regression_attached": self.experiment_regression_report is not None,
            "experiment_regression_passed": _experiment_regression_passed(
                self.experiment_regression_report
            ),
            "experiment_regression_failure_count": _experiment_regression_failure_count(
                self.experiment_regression_report
            ),
            "experiment_regression_failures": _experiment_regression_failures(
                self.experiment_regression_report
            ),
        }

        if self.summary_payload is not None:
            data["summary_payload"] = dict(self.summary_payload)

        return data


@dataclass(frozen=True)
class ResearchOperationRecordCheck:
    name: str
    passed: bool
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchOperationRecordValidationResult:
    checks: tuple[ResearchOperationRecordCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[ResearchOperationRecordCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "message": check.message,
                    "details": dict(check.details),
                }
                for check in self.checks
            ],
        }


class ResearchOperationRecordError(ValueError):
    """Raised when a research operation record fails validation."""


def build_research_operation_record(
    operation_result: Any,
    config: ResearchOperationRecordConfig | None = None,
    backtest_attachment: Any | None = None,
    backtest_handoff_result: Any | None = None,
    model_readiness_report: Any | None = None,
    model_quality_report: Any | None = None,
    model_testing_summary: Mapping[str, Any] | None = None,
    experiment_regression_report: Mapping[str, Any] | None = None,
) -> ResearchOperationRecord:
    config = config or ResearchOperationRecordConfig()

    status_value = _enum_value(getattr(operation_result, "status", None))

    if status_value not in {"pass", "fail"}:
        raise ValueError("operation_result.status must be pass or fail.")

    status = ResearchOperationRecordStatus(status_value)
    passed = bool(
        getattr(operation_result, "passed", status == ResearchOperationRecordStatus.PASS)
    )

    operation_metadata = dict(getattr(operation_result, "metadata", {}) or {})

    evaluation_result = getattr(operation_result, "evaluation_result", None)
    model_operation_result = getattr(operation_result, "model_operation_result", None)

    model_test_result = getattr(model_operation_result, "model_test_result", None)
    model_gate_result = getattr(model_operation_result, "model_gate_result", None)

    model_gate_failures = tuple(getattr(model_gate_result, "failures", ()) or ())
    model_gate_warnings = tuple(getattr(model_gate_result, "warnings", ()) or ())

    metadata = {
        **operation_metadata,
        **dict(config.metadata),
    }

    summary_payload = None
    if config.include_summary:
        summary_payload = _call_summary(operation_result)

    backtest_payload = (
        backtest_attachment.to_dict()
        if backtest_attachment is not None
        else None
    )

    backtest_report = (
        backtest_payload.get("report", {})
        if isinstance(backtest_payload, Mapping)
        else {}
    )

    backtest_performance = dict(backtest_report.get("performance", {}) or {})
    backtest_nav_series = tuple(backtest_report.get("nav_series", ()) or ())
    backtest_exposure_series = tuple(backtest_report.get("exposure_series", ()) or ())
    backtest_trade_summary = dict(backtest_report.get("trade_summary", {}) or {})
    backtest_rebalance_summary = dict(
        backtest_report.get("rebalance_summary", {}) or {}
    )

    backtest_handoff_payload = _object_to_mapping(backtest_handoff_result)
    
    model_readiness_payload = (
        model_readiness_report.to_dict()
        if model_readiness_report is not None
        else None
    )

    model_readiness_failures = (
        tuple(model_readiness_payload.get("checks", ()) or ())
        if isinstance(model_readiness_payload, Mapping)
        else ()
    )

    model_readiness_failure_count = sum(
        1
        for check in model_readiness_failures
        if check.get("status") == "fail"
    )

    model_readiness_warning_count = sum(
        1
        for check in model_readiness_failures
        if check.get("status") == "warning"
    )

    model_quality_summary = (
        build_model_quality_operation_summary(model_quality_report)
        if model_quality_report is not None
        else None
    )
    model_quality_failures = (
        model_quality_failure_messages(model_quality_summary)
        if model_quality_summary is not None
        else []
    )

    return ResearchOperationRecord(
        operation_name=config.operation_name,
        run_id=config.run_id,
        status=status,
        passed=passed,
        evaluation_decision=operation_metadata.get(
            "evaluation_decision",
            getattr(evaluation_result, "decision", None),
        ),
        evaluation_promoted=operation_metadata.get(
            "evaluation_promoted",
            getattr(evaluation_result, "promoted", None),
        ),
        model_operation_status=operation_metadata.get(
            "model_operation_status",
            _enum_value(getattr(model_operation_result, "status", None)),
        ),
        model_test_passed=(
            bool(getattr(model_test_result, "passed"))
            if model_test_result is not None and hasattr(model_test_result, "passed")
            else None
        ),
        model_gate_passed=(
            bool(getattr(model_gate_result, "passed"))
            if model_gate_result is not None and hasattr(model_gate_result, "passed")
            else None
        ),
        model_gate_failure_count=len(model_gate_failures),
        model_gate_warning_count=len(model_gate_warnings),
        portfolio_target_rows=_height(getattr(model_test_result, "portfolio_targets", None)),
        backtest_input_rows=_height(getattr(model_test_result, "backtest_input", None)),
        daily_return_rows=_height(getattr(model_test_result, "daily_returns", None)),
        metadata=metadata,
        summary_payload=summary_payload,
        backtest_report_attached=backtest_attachment is not None,
        backtest_attachment_passed=(
            bool(backtest_payload.get("passed"))
            if isinstance(backtest_payload, Mapping)
            else None
        ),
        backtest_nav_rows=len(backtest_nav_series),
        backtest_exposure_rows=len(backtest_exposure_series),
        backtest_trade_count=int(backtest_trade_summary.get("trade_count", 0) or 0),
        backtest_rebalance_count=int(
            backtest_rebalance_summary.get("rebalance_count", 0) or 0
        ),
        backtest_start_value=backtest_performance.get("start_value"),
        backtest_final_value=backtest_performance.get("final_value"),
        backtest_total_return=backtest_performance.get("total_return"),
        backtest_handoff_summary=(
            dict(backtest_handoff_payload)
            if backtest_handoff_payload is not None
            else None
        ),
        model_readiness_attached=model_readiness_report is not None,
        model_readiness_passed=(
            bool(model_readiness_payload.get("passed"))
            if isinstance(model_readiness_payload, Mapping)
            else None
        ),
        model_readiness_failure_count=model_readiness_failure_count,
        model_readiness_warning_count=model_readiness_warning_count,
        model_quality_summary=model_quality_summary,
        model_quality_failures=model_quality_failures,
        model_testing_summary=(
            dict(model_testing_summary)
            if model_testing_summary is not None
            else None
        ),
        experiment_regression_report=(
            dict(experiment_regression_report)
            if experiment_regression_report is not None
            else None
        ),
    )


def validate_research_operation_record(
    record: ResearchOperationRecord,
    require_passed: bool = False,
) -> ResearchOperationRecordValidationResult:
    checks: list[ResearchOperationRecordCheck] = []

    checks.append(
        ResearchOperationRecordCheck(
            name="operation_name",
            passed=bool(record.operation_name),
            message=(
                "Operation name is present."
                if record.operation_name
                else "Operation name is missing."
            ),
        )
    )

    checks.append(
        ResearchOperationRecordCheck(
            name="status_consistency",
            passed=(
                (record.status == ResearchOperationRecordStatus.PASS and record.passed)
                or (record.status == ResearchOperationRecordStatus.FAIL and not record.passed)
            ),
            message="Operation status and passed flag are consistent.",
            details={
                "status": record.status.value,
                "passed": record.passed,
            },
        )
    )

    if record.status == ResearchOperationRecordStatus.PASS:
        checks.append(
            ResearchOperationRecordCheck(
                name="passing_operation_has_model_gate_pass",
                passed=record.model_gate_passed is not False,
                message=(
                    "Passing operation has no failed model gate."
                    if record.model_gate_passed is not False
                    else "Passing operation has a failed model gate."
                ),
                details={"model_gate_passed": record.model_gate_passed},
            )
        )

        checks.append(
            ResearchOperationRecordCheck(
                name="passing_operation_has_model_test_pass",
                passed=record.model_test_passed is not False,
                message=(
                    "Passing operation has no failed model test."
                    if record.model_test_passed is not False
                    else "Passing operation has a failed model test."
                ),
                details={"model_test_passed": record.model_test_passed},
            )
        )

    if require_passed:
        checks.append(
            ResearchOperationRecordCheck(
                name="require_passed",
                passed=record.passed,
                message=(
                    "Operation record passed required-pass validation."
                    if record.passed
                    else "Operation record failed required-pass validation."
                ),
                details={"status": record.status.value},
            )
        )

    return ResearchOperationRecordValidationResult(checks=tuple(checks))


def enforce_research_operation_record(
    record: ResearchOperationRecord,
    require_passed: bool = False,
) -> ResearchOperationRecord:
    result = validate_research_operation_record(
        record=record,
        require_passed=require_passed,
    )

    if not result.passed:
        messages = "; ".join(check.message for check in result.failures)
        raise ResearchOperationRecordError(
            f"Research operation record validation failed: {messages}"
        )

    return record


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None

    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)

    return str(value)


def _height(frame: Any) -> int:
    if frame is None:
        return 0

    height = getattr(frame, "height", None)
    if height is not None:
        return int(height)

    try:
        return len(frame)
    except TypeError:
        return 0


def _call_summary(obj: Any) -> Mapping[str, Any] | None:
    summary = getattr(obj, "summary", None)

    if not callable(summary):
        return None

    data = summary()

    if data is None:
        return None

    if not isinstance(data, Mapping):
        raise TypeError("operation_result.summary() must return a mapping.")

    return dict(data)


def attach_model_quality_report(
    record: ResearchOperationRecord,
    report: object,
) -> ResearchOperationRecord:
    """
    Attach a compact ModelQualityReport summary to a research operation record.

    The operation layer stores only operationally relevant quality state:
    pass/fail, status, key diagnostics, and blocking failure reasons.
    """
    summary = build_model_quality_operation_summary(report)
    failures = model_quality_failure_messages(summary)

    return replace(
        record,
        model_quality_summary=summary,
        model_quality_failures=failures,
    )


def attach_model_testing_summary(
    record: ResearchOperationRecord,
    summary: Mapping[str, Any],
) -> ResearchOperationRecord:
    """Attach a compact model-testing comparison summary to a record."""

    return replace(
        record,
        model_testing_summary=dict(summary),
    )


def attach_experiment_regression_report(
    record: ResearchOperationRecord,
    report: Mapping[str, Any],
) -> ResearchOperationRecord:
    """Attach an experiment regression comparison report to a record."""

    return replace(
        record,
        experiment_regression_report=dict(report),
    )


def attach_backtest_handoff_result(
    record: ResearchOperationRecord,
    result: object,
) -> ResearchOperationRecord:
    """Attach a research-to-backtest handoff result to a record."""

    payload = _object_to_mapping(result)

    if payload is None:
        raise TypeError("backtest handoff result must be mapping-like")

    return replace(
        record,
        backtest_handoff_summary=dict(payload),
    )


def _object_to_mapping(value: Any | None) -> Mapping[str, Any] | None:
    if value is None:
        return None

    if isinstance(value, Mapping):
        return value

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, Mapping):
            return data
        raise TypeError("object.to_dict() must return a mapping.")

    data = getattr(value, "__dict__", None)
    if isinstance(data, Mapping):
        return data

    return None


def _backtest_handoff_passed(
    backtest_handoff_summary: Mapping[str, Any] | None,
) -> bool | None:
    if backtest_handoff_summary is None:
        return None

    if "passed" in backtest_handoff_summary:
        return backtest_handoff_summary.get("passed") is True

    return backtest_handoff_summary.get("status") == "passed"


def _backtest_handoff_failure_count(
    backtest_handoff_summary: Mapping[str, Any] | None,
) -> int:
    return len(_backtest_handoff_failures(backtest_handoff_summary))


def _backtest_handoff_failures(
    backtest_handoff_summary: Mapping[str, Any] | None,
) -> list[str]:
    if backtest_handoff_summary is None:
        return []

    explicit_failures = backtest_handoff_summary.get("failures")

    if isinstance(explicit_failures, str):
        return [explicit_failures]

    if isinstance(explicit_failures, Sequence):
        return [str(failure) for failure in explicit_failures]

    failure_reason = backtest_handoff_summary.get("failure_reason")

    if failure_reason:
        return [str(failure_reason)]

    if _backtest_handoff_passed(backtest_handoff_summary) is False:
        return ["backtest_handoff_failed"]

    return []


def _backtest_handoff_value(
    backtest_handoff_summary: Mapping[str, Any] | None,
    key: str,
) -> Any | None:
    if backtest_handoff_summary is None:
        return None

    return backtest_handoff_summary.get(key)


def _backtest_handoff_performance(
    backtest_handoff_summary: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if backtest_handoff_summary is None:
        return None

    performance = backtest_handoff_summary.get("performance")

    if isinstance(performance, Mapping):
        return dict(performance)

    return None


def _experiment_regression_passed(
    experiment_regression_report: Mapping[str, Any] | None,
) -> bool | None:
    if experiment_regression_report is None:
        return None

    return experiment_regression_report.get("has_regression") is False


def _experiment_regression_failure_count(
    experiment_regression_report: Mapping[str, Any] | None,
) -> int:
    if experiment_regression_report is None:
        return 0

    failures = experiment_regression_report.get("failed_checks", [])

    if isinstance(failures, str):
        return 1

    if isinstance(failures, Sequence):
        return len(failures)

    return 0


def _experiment_regression_failures(
    experiment_regression_report: Mapping[str, Any] | None,
) -> list[str]:
    if experiment_regression_report is None:
        return []

    failures = experiment_regression_report.get("failed_checks", [])

    if isinstance(failures, str):
        return [failures]

    if isinstance(failures, Sequence):
        return [str(failure) for failure in failures]

    return []

