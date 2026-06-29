from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ResearchModelGateStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True)
class ResearchModelGateCheck:
    name: str
    passed: bool
    status: ResearchModelGateStatus
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchModelGateConfig:
    min_daily_return_rows: int = 1
    min_final_equity: float = 0.0
    max_drawdown_floor: float = -1.0
    max_gross_exposure: float | None = None
    max_abs_net_exposure: float | None = None
    require_smoke_passed: bool = True
    require_promoted: bool = False

    def __post_init__(self) -> None:
        if self.min_daily_return_rows <= 0:
            raise ValueError("min_daily_return_rows must be greater than zero.")

        if self.min_final_equity < 0:
            raise ValueError("min_final_equity cannot be negative.")

        if self.max_drawdown_floor > 0:
            raise ValueError("max_drawdown_floor must be zero or negative.")

        if self.max_gross_exposure is not None and self.max_gross_exposure <= 0:
            raise ValueError("max_gross_exposure must be greater than zero when provided.")

        if self.max_abs_net_exposure is not None and self.max_abs_net_exposure < 0:
            raise ValueError("max_abs_net_exposure cannot be negative when provided.")


@dataclass(frozen=True)
class ResearchModelGateResult:
    checks: tuple[ResearchModelGateCheck, ...]

    @property
    def passed(self) -> bool:
        return not any(check.status == ResearchModelGateStatus.FAIL for check in self.checks)

    @property
    def warnings(self) -> tuple[ResearchModelGateCheck, ...]:
        return tuple(
            check for check in self.checks
            if check.status == ResearchModelGateStatus.WARNING
        )

    @property
    def failures(self) -> tuple[ResearchModelGateCheck, ...]:
        return tuple(
            check for check in self.checks
            if check.status == ResearchModelGateStatus.FAIL
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
        }


class ResearchModelGateError(ValueError):
    """Raised when a research model test result fails the model gate."""


def evaluate_research_model_gate(
    model_test_result: Any,
    config: ResearchModelGateConfig | None = None,
) -> ResearchModelGateResult:
    config = config or ResearchModelGateConfig()
    checks: list[ResearchModelGateCheck] = []

    smoke_result = getattr(model_test_result, "smoke_result", None)
    metadata = dict(getattr(model_test_result, "metadata", {}) or {})

    if smoke_result is None:
        return ResearchModelGateResult(
            checks=(
                ResearchModelGateCheck(
                    name="smoke_result.exists",
                    passed=False,
                    status=ResearchModelGateStatus.FAIL,
                    message="Model test result does not include a smoke_result.",
                ),
            )
        )

    smoke_summary = dict(getattr(smoke_result, "summary", {}) or {})
    daily_returns = getattr(model_test_result, "daily_returns", None)

    if config.require_smoke_passed:
        smoke_passed = bool(getattr(smoke_result, "passed", False))
        checks.append(
            ResearchModelGateCheck(
                name="smoke_result.passed",
                passed=smoke_passed,
                status=(
                    ResearchModelGateStatus.PASS
                    if smoke_passed
                    else ResearchModelGateStatus.FAIL
                ),
                message=(
                    "Smoke backtest passed."
                    if smoke_passed
                    else "Smoke backtest did not pass."
                ),
                details={"smoke_passed": smoke_passed},
            )
        )

    if config.require_promoted:
        promoted = metadata.get("evaluation_promoted")

        checks.append(
            ResearchModelGateCheck(
                name="evaluation.promoted",
                passed=promoted is True,
                status=(
                    ResearchModelGateStatus.PASS
                    if promoted is True
                    else ResearchModelGateStatus.FAIL
                ),
                message=(
                    "Evaluation result was promoted."
                    if promoted is True
                    else "Evaluation result was not promoted."
                ),
                details={"evaluation_promoted": promoted},
            )
        )

    daily_rows = int(smoke_summary.get("rows", 0))

    checks.append(
        ResearchModelGateCheck(
            name="daily_return_rows",
            passed=daily_rows >= config.min_daily_return_rows,
            status=(
                ResearchModelGateStatus.PASS
                if daily_rows >= config.min_daily_return_rows
                else ResearchModelGateStatus.FAIL
            ),
            message=(
                "Daily return row count meets gate requirement."
                if daily_rows >= config.min_daily_return_rows
                else "Daily return row count is below gate requirement."
            ),
            details={
                "daily_return_rows": daily_rows,
                "min_daily_return_rows": config.min_daily_return_rows,
            },
        )
    )

    final_equity = float(smoke_summary.get("final_equity", 0.0))

    checks.append(
        ResearchModelGateCheck(
            name="final_equity",
            passed=final_equity >= config.min_final_equity,
            status=(
                ResearchModelGateStatus.PASS
                if final_equity >= config.min_final_equity
                else ResearchModelGateStatus.FAIL
            ),
            message=(
                "Final equity meets gate requirement."
                if final_equity >= config.min_final_equity
                else "Final equity is below gate requirement."
            ),
            details={
                "final_equity": final_equity,
                "min_final_equity": config.min_final_equity,
            },
        )
    )

    max_drawdown = float(smoke_summary.get("max_drawdown", 0.0))

    checks.append(
        ResearchModelGateCheck(
            name="max_drawdown",
            passed=max_drawdown >= config.max_drawdown_floor,
            status=(
                ResearchModelGateStatus.PASS
                if max_drawdown >= config.max_drawdown_floor
                else ResearchModelGateStatus.FAIL
            ),
            message=(
                "Max drawdown is within gate requirement."
                if max_drawdown >= config.max_drawdown_floor
                else "Max drawdown breached gate requirement."
            ),
            details={
                "max_drawdown": max_drawdown,
                "max_drawdown_floor": config.max_drawdown_floor,
            },
        )
    )

    if config.max_gross_exposure is not None:
        max_observed_gross = _max_column_value(
            daily_returns,
            column="gross_exposure",
            absolute=False,
        )

        checks.append(
            ResearchModelGateCheck(
                name="gross_exposure",
                passed=max_observed_gross <= config.max_gross_exposure,
                status=(
                    ResearchModelGateStatus.PASS
                    if max_observed_gross <= config.max_gross_exposure
                    else ResearchModelGateStatus.FAIL
                ),
                message=(
                    "Gross exposure is within gate requirement."
                    if max_observed_gross <= config.max_gross_exposure
                    else "Gross exposure breached gate requirement."
                ),
                details={
                    "max_observed_gross_exposure": max_observed_gross,
                    "max_gross_exposure": config.max_gross_exposure,
                },
            )
        )

    if config.max_abs_net_exposure is not None:
        max_observed_abs_net = _max_column_value(
            daily_returns,
            column="net_exposure",
            absolute=True,
        )

        checks.append(
            ResearchModelGateCheck(
                name="net_exposure",
                passed=max_observed_abs_net <= config.max_abs_net_exposure,
                status=(
                    ResearchModelGateStatus.PASS
                    if max_observed_abs_net <= config.max_abs_net_exposure
                    else ResearchModelGateStatus.FAIL
                ),
                message=(
                    "Net exposure is within gate requirement."
                    if max_observed_abs_net <= config.max_abs_net_exposure
                    else "Net exposure breached gate requirement."
                ),
                details={
                    "max_observed_abs_net_exposure": max_observed_abs_net,
                    "max_abs_net_exposure": config.max_abs_net_exposure,
                },
            )
        )

    return ResearchModelGateResult(checks=tuple(checks))


def enforce_research_model_gate(
    model_test_result: Any,
    config: ResearchModelGateConfig | None = None,
) -> Any:
    result = evaluate_research_model_gate(
        model_test_result=model_test_result,
        config=config,
    )

    if not result.passed:
        messages = "; ".join(check.message for check in result.failures)
        raise ResearchModelGateError(
            f"Research model gate failed: {messages}"
        )

    return model_test_result


def _max_column_value(
    frame: Any,
    column: str,
    absolute: bool = False,
) -> float:
    if frame is None or not hasattr(frame, "columns") or column not in frame.columns:
        return 0.0

    values = frame[column].to_list()

    if not values:
        return 0.0

    if absolute:
        return max(abs(float(value)) for value in values)

    return max(float(value) for value in values)
