from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ModelReadinessStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True)
class ModelReadinessCheck:
    name: str
    status: ModelReadinessStatus
    passed: bool
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelReadinessConfig:
    require_promoted: bool = True
    require_diagnostics_passed: bool = False
    allow_diagnostic_warnings: bool = True
    require_backtest_attachment: bool = True
    require_backtest_passed: bool = True
    min_total_return: float | None = None
    max_drawdown: float | None = None
    min_trade_count: int | None = None
    min_rebalance_count: int | None = None
    min_nav_rows: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.min_trade_count is not None and self.min_trade_count < 0:
            raise ValueError("min_trade_count cannot be negative.")

        if self.min_rebalance_count is not None and self.min_rebalance_count < 0:
            raise ValueError("min_rebalance_count cannot be negative.")

        if self.min_nav_rows < 0:
            raise ValueError("min_nav_rows cannot be negative.")

        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ModelReadinessReport:
    checks: tuple[ModelReadinessCheck, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(check.status == ModelReadinessStatus.FAIL for check in self.checks)

    @property
    def warnings(self) -> tuple[ModelReadinessCheck, ...]:
        return tuple(
            check for check in self.checks if check.status == ModelReadinessStatus.WARNING
        )

    @property
    def failures(self) -> tuple[ModelReadinessCheck, ...]:
        return tuple(
            check for check in self.checks if check.status == ModelReadinessStatus.FAIL
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "passed": check.passed,
                    "message": check.message,
                    "details": dict(check.details),
                }
                for check in self.checks
            ],
            "metadata": dict(self.metadata),
        }


def evaluate_model_readiness(
    evaluation_output: Mapping[str, Any],
    diagnostics_report: Any | None = None,
    backtest_attachment: Any | None = None,
    config: ModelReadinessConfig | None = None,
) -> ModelReadinessReport:
    config = config or ModelReadinessConfig()
    checks: list[ModelReadinessCheck] = []

    checks.append(
        _check_promoted(
            evaluation_output=evaluation_output,
            require_promoted=config.require_promoted,
        )
    )

    checks.append(
        _check_diagnostics(
            diagnostics_report=diagnostics_report,
            require_diagnostics_passed=config.require_diagnostics_passed,
            allow_diagnostic_warnings=config.allow_diagnostic_warnings,
        )
    )

    checks.append(
        _check_backtest_attachment_present(
            backtest_attachment=backtest_attachment,
            require_backtest_attachment=config.require_backtest_attachment,
        )
    )

    if backtest_attachment is not None:
        attachment_payload = backtest_attachment.to_dict()

        checks.append(
            _check_backtest_attachment_passed(
                attachment_payload=attachment_payload,
                require_backtest_passed=config.require_backtest_passed,
            )
        )

        checks.append(
            _check_backtest_nav_rows(
                attachment_payload=attachment_payload,
                min_nav_rows=config.min_nav_rows,
            )
        )

        checks.extend(
            _check_backtest_performance_thresholds(
                attachment_payload=attachment_payload,
                min_total_return=config.min_total_return,
                max_drawdown=config.max_drawdown,
            )
        )

        checks.extend(
            _check_backtest_activity_thresholds(
                attachment_payload=attachment_payload,
                min_trade_count=config.min_trade_count,
                min_rebalance_count=config.min_rebalance_count,
            )
        )

    return ModelReadinessReport(
        checks=tuple(checks),
        metadata={
            "source": "model_readiness",
            **dict(config.metadata),
        },
    )


def _check_promoted(
    evaluation_output: Mapping[str, Any],
    require_promoted: bool,
) -> ModelReadinessCheck:
    promoted = evaluation_output.get("promoted")

    if not require_promoted:
        return ModelReadinessCheck(
            name="evaluation_promoted",
            status=ModelReadinessStatus.PASS,
            passed=True,
            message="Promotion check is not required.",
            details={"promoted": promoted, "require_promoted": require_promoted},
        )

    passed = promoted is True

    return ModelReadinessCheck(
        name="evaluation_promoted",
        status=ModelReadinessStatus.PASS if passed else ModelReadinessStatus.FAIL,
        passed=passed,
        message=(
            "Evaluation output is promoted."
            if passed
            else "Evaluation output is not promoted."
        ),
        details={"promoted": promoted, "require_promoted": require_promoted},
    )


def _check_diagnostics(
    diagnostics_report: Any | None,
    require_diagnostics_passed: bool,
    allow_diagnostic_warnings: bool,
) -> ModelReadinessCheck:
    if diagnostics_report is None:
        status = (
            ModelReadinessStatus.FAIL
            if require_diagnostics_passed
            else ModelReadinessStatus.WARNING
        )

        return ModelReadinessCheck(
            name="diagnostics_available",
            status=status,
            passed=not require_diagnostics_passed,
            message=(
                "Diagnostics report is missing."
                if require_diagnostics_passed
                else "Diagnostics report is missing but not required."
            ),
            details={"require_diagnostics_passed": require_diagnostics_passed},
        )

    diagnostics_passed = bool(getattr(diagnostics_report, "passed", False))
    warnings = tuple(getattr(diagnostics_report, "warnings", ()) or ())
    failures = tuple(getattr(diagnostics_report, "failures", ()) or ())

    if diagnostics_passed:
        status = (
            ModelReadinessStatus.WARNING
            if warnings and not allow_diagnostic_warnings
            else ModelReadinessStatus.PASS
        )

        passed = not warnings or allow_diagnostic_warnings

        return ModelReadinessCheck(
            name="diagnostics_passed",
            status=status if passed else ModelReadinessStatus.FAIL,
            passed=passed,
            message=(
                "Diagnostics passed."
                if passed
                else "Diagnostics passed but warnings are not allowed."
            ),
            details={
                "diagnostics_passed": diagnostics_passed,
                "warning_count": len(warnings),
                "failure_count": len(failures),
                "allow_diagnostic_warnings": allow_diagnostic_warnings,
            },
        )

    return ModelReadinessCheck(
        name="diagnostics_passed",
        status=ModelReadinessStatus.FAIL,
        passed=False,
        message="Diagnostics failed.",
        details={
            "diagnostics_passed": diagnostics_passed,
            "warning_count": len(warnings),
            "failure_count": len(failures),
        },
    )


def _check_backtest_attachment_present(
    backtest_attachment: Any | None,
    require_backtest_attachment: bool,
) -> ModelReadinessCheck:
    attached = backtest_attachment is not None

    if not require_backtest_attachment:
        return ModelReadinessCheck(
            name="backtest_attachment_present",
            status=ModelReadinessStatus.PASS,
            passed=True,
            message="Backtest attachment check is not required.",
            details={"attached": attached},
        )

    return ModelReadinessCheck(
        name="backtest_attachment_present",
        status=ModelReadinessStatus.PASS if attached else ModelReadinessStatus.FAIL,
        passed=attached,
        message=(
            "Backtest attachment is present."
            if attached
            else "Backtest attachment is required but missing."
        ),
        details={"attached": attached},
    )


def _check_backtest_attachment_passed(
    attachment_payload: Mapping[str, Any],
    require_backtest_passed: bool,
) -> ModelReadinessCheck:
    backtest_passed = attachment_payload.get("passed")

    if not require_backtest_passed:
        return ModelReadinessCheck(
            name="backtest_attachment_passed",
            status=ModelReadinessStatus.PASS,
            passed=True,
            message="Backtest attachment pass check is not required.",
            details={"backtest_passed": backtest_passed},
        )

    passed = backtest_passed is True

    return ModelReadinessCheck(
        name="backtest_attachment_passed",
        status=ModelReadinessStatus.PASS if passed else ModelReadinessStatus.FAIL,
        passed=passed,
        message=(
            "Backtest attachment passed."
            if passed
            else "Backtest attachment did not pass."
        ),
        details={"backtest_passed": backtest_passed},
    )


def _check_backtest_nav_rows(
    attachment_payload: Mapping[str, Any],
    min_nav_rows: int,
) -> ModelReadinessCheck:
    report = dict(attachment_payload.get("report", {}) or {})
    nav_series = tuple(report.get("nav_series", ()) or ())
    nav_rows = len(nav_series)
    passed = nav_rows >= min_nav_rows

    return ModelReadinessCheck(
        name="backtest_nav_rows",
        status=ModelReadinessStatus.PASS if passed else ModelReadinessStatus.FAIL,
        passed=passed,
        message=(
            "Backtest NAV row count meets requirement."
            if passed
            else "Backtest NAV row count is below requirement."
        ),
        details={"nav_rows": nav_rows, "min_nav_rows": min_nav_rows},
    )


def _check_backtest_performance_thresholds(
    attachment_payload: Mapping[str, Any],
    min_total_return: float | None,
    max_drawdown: float | None,
) -> list[ModelReadinessCheck]:
    report = dict(attachment_payload.get("report", {}) or {})
    performance = dict(report.get("performance", {}) or {})

    checks: list[ModelReadinessCheck] = []

    if min_total_return is not None:
        total_return = performance.get("total_return")
        passed = total_return is not None and float(total_return) >= min_total_return

        checks.append(
            ModelReadinessCheck(
                name="backtest_min_total_return",
                status=ModelReadinessStatus.PASS if passed else ModelReadinessStatus.FAIL,
                passed=passed,
                message=(
                    "Backtest total return meets minimum requirement."
                    if passed
                    else "Backtest total return is below minimum requirement."
                ),
                details={
                    "total_return": total_return,
                    "min_total_return": min_total_return,
                },
            )
        )

    if max_drawdown is not None:
        drawdown = performance.get("max_drawdown")
        passed = drawdown is not None and float(drawdown) >= max_drawdown

        checks.append(
            ModelReadinessCheck(
                name="backtest_max_drawdown",
                status=ModelReadinessStatus.PASS if passed else ModelReadinessStatus.FAIL,
                passed=passed,
                message=(
                    "Backtest drawdown is within requirement."
                    if passed
                    else "Backtest drawdown breaches requirement."
                ),
                details={
                    "max_drawdown": drawdown,
                    "allowed_max_drawdown": max_drawdown,
                },
            )
        )

    return checks


def _check_backtest_activity_thresholds(
    attachment_payload: Mapping[str, Any],
    min_trade_count: int | None,
    min_rebalance_count: int | None,
) -> list[ModelReadinessCheck]:
    report = dict(attachment_payload.get("report", {}) or {})
    trade_summary = dict(report.get("trade_summary", {}) or {})
    rebalance_summary = dict(report.get("rebalance_summary", {}) or {})

    checks: list[ModelReadinessCheck] = []

    if min_trade_count is not None:
        trade_count = int(trade_summary.get("trade_count", 0) or 0)
        passed = trade_count >= min_trade_count

        checks.append(
            ModelReadinessCheck(
                name="backtest_min_trade_count",
                status=ModelReadinessStatus.PASS if passed else ModelReadinessStatus.FAIL,
                passed=passed,
                message=(
                    "Backtest trade count meets requirement."
                    if passed
                    else "Backtest trade count is below requirement."
                ),
                details={
                    "trade_count": trade_count,
                    "min_trade_count": min_trade_count,
                },
            )
        )

    if min_rebalance_count is not None:
        rebalance_count = int(rebalance_summary.get("rebalance_count", 0) or 0)
        passed = rebalance_count >= min_rebalance_count

        checks.append(
            ModelReadinessCheck(
                name="backtest_min_rebalance_count",
                status=ModelReadinessStatus.PASS if passed else ModelReadinessStatus.FAIL,
                passed=passed,
                message=(
                    "Backtest rebalance count meets requirement."
                    if passed
                    else "Backtest rebalance count is below requirement."
                ),
                details={
                    "rebalance_count": rebalance_count,
                    "min_rebalance_count": min_rebalance_count,
                },
            )
        )

    return checks
