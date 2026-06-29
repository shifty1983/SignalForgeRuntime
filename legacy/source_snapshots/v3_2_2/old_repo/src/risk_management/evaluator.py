from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Any

from src.risk_management.portfolio_adapter import (
    validate_risk_management_input_rows,
)


PASSING_STATUSES = {"passed", "pass", "success", "succeeded", "ok"}
BLOCKING_STATUSES = {"failed", "fail", "invalid", "rejected", "blocked", "error"}

REQUIRED_CONSTRUCTION_CONTEXT_FIELDS = (
    "construction_status",
    "accepted_count",
    "rejected_count",
    "total_target_exposure",
    "long_exposure",
    "short_exposure",
    "net_exposure",
)


@dataclass(frozen=True)
class RiskCandidateEvaluation:
    risk_input_id: str
    portfolio_input_id: str
    candidate_id: str
    symbol: str
    direction: str
    target_weight: float
    selection_rank: int
    selection_score: float
    eligible: bool
    rejection_reasons: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    metadata: Mapping[str, Any]
    performance_context: Mapping[str, Any]
    construction_context: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_input_id": self.risk_input_id,
            "portfolio_input_id": self.portfolio_input_id,
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "target_weight": self.target_weight,
            "selection_rank": self.selection_rank,
            "selection_score": self.selection_score,
            "eligible": self.eligible,
            "rejection_reasons": list(self.rejection_reasons),
            "diagnostics": dict(self.diagnostics),
            "metadata": dict(self.metadata),
            "performance_context": dict(self.performance_context),
            "construction_context": dict(self.construction_context),
        }


@dataclass(frozen=True)
class RiskManagementEvaluationReport:
    passed: bool
    candidate_count: int
    eligible_count: int
    rejected_count: int
    evaluations: tuple[RiskCandidateEvaluation, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "evaluations": [
                evaluation.to_dict()
                for evaluation in self.evaluations
            ],
            "errors": list(self.errors),
        }


def evaluate_risk_management_candidates(
    rows: Sequence[Mapping[str, Any]],
) -> RiskManagementEvaluationReport:
    """
    Evaluate risk-management input rows for downstream readiness.

    This does not apply exposure limits, concentration limits, stop rules,
    position resizing, order generation, or execution.
    """
    contract_validation = validate_risk_management_input_rows(rows)

    if not contract_validation.passed:
        return RiskManagementEvaluationReport(
            passed=False,
            candidate_count=len(rows),
            eligible_count=0,
            rejected_count=len(rows),
            evaluations=(),
            errors=contract_validation.errors,
        )

    evaluations = tuple(
        _evaluate_risk_input_row(row)
        for row in rows
    )

    eligible_count = sum(
        1 for evaluation in evaluations
        if evaluation.eligible
    )
    rejected_count = len(evaluations) - eligible_count

    return RiskManagementEvaluationReport(
        passed=rejected_count == 0,
        candidate_count=len(evaluations),
        eligible_count=eligible_count,
        rejected_count=rejected_count,
        evaluations=evaluations,
        errors=(),
    )


def _evaluate_risk_input_row(
    row: Mapping[str, Any],
) -> RiskCandidateEvaluation:
    diagnostics = dict(row["diagnostics"])
    metadata = dict(row["metadata"])
    performance_context = dict(row["performance_context"])
    construction_context = dict(row["construction_context"])

    rejection_reasons = _risk_rejection_reasons(
        direction=str(row["direction"]),
        target_weight=float(row["target_weight"]),
        diagnostics=diagnostics,
        metadata=metadata,
        performance_context=performance_context,
        construction_context=construction_context,
    )

    return RiskCandidateEvaluation(
        risk_input_id=str(row["risk_input_id"]),
        portfolio_input_id=str(row["portfolio_input_id"]),
        candidate_id=str(row["candidate_id"]),
        symbol=str(row["symbol"]),
        direction=str(row["direction"]),
        target_weight=float(row["target_weight"]),
        selection_rank=int(row["selection_rank"]),
        selection_score=float(row["selection_score"]),
        eligible=not rejection_reasons,
        rejection_reasons=tuple(rejection_reasons),
        diagnostics=diagnostics,
        metadata=metadata,
        performance_context=performance_context,
        construction_context=construction_context,
    )


def _risk_rejection_reasons(
    *,
    direction: str,
    target_weight: float,
    diagnostics: Mapping[str, Any],
    metadata: Mapping[str, Any],
    performance_context: Mapping[str, Any],
    construction_context: Mapping[str, Any],
) -> list[str]:
    rejection_reasons: list[str] = []

    if not diagnostics:
        rejection_reasons.append("missing diagnostics")

    if not performance_context:
        rejection_reasons.append("missing performance_context")

    if not construction_context:
        rejection_reasons.append("missing construction_context")
    else:
        rejection_reasons.extend(
            _construction_context_rejection_reasons(construction_context)
        )

    rejection_reasons.extend(
        _direction_weight_rejection_reasons(
            direction=direction,
            target_weight=target_weight,
        )
    )

    diagnostic_status = _status_value(
        diagnostics,
        "diagnostic_status",
        "diagnostics_status",
        "status",
    )
    if diagnostic_status in BLOCKING_STATUSES:
        rejection_reasons.append(
            f"diagnostics status is blocking: {diagnostic_status}"
        )

    backtest_status = _status_value(
        performance_context,
        "backtest_status",
        "status",
    )
    if backtest_status is not None and backtest_status not in PASSING_STATUSES:
        rejection_reasons.append(
            f"backtest status is not passed: {backtest_status}"
        )

    if _is_blocked(metadata) or _is_blocked(diagnostics):
        rejection_reasons.append("candidate is blocked")

    return rejection_reasons


def _construction_context_rejection_reasons(
    construction_context: Mapping[str, Any],
) -> list[str]:
    rejection_reasons: list[str] = []

    for field in REQUIRED_CONSTRUCTION_CONTEXT_FIELDS:
        if field not in construction_context:
            rejection_reasons.append(
                f"construction_context missing required field: {field}"
            )

    construction_status = construction_context.get("construction_status")
    if construction_status != "constructed":
        rejection_reasons.append(
            f"construction status is not constructed: {construction_status}"
        )

    accepted_count = construction_context.get("accepted_count")
    if not _non_negative_int(accepted_count) or accepted_count < 1:
        rejection_reasons.append("construction_context has invalid accepted_count")

    rejected_count = construction_context.get("rejected_count")
    if not _non_negative_int(rejected_count):
        rejection_reasons.append("construction_context has invalid rejected_count")

    for field in (
        "total_target_exposure",
        "long_exposure",
        "short_exposure",
        "net_exposure",
    ):
        value = construction_context.get(field)
        if not _valid_number(value):
            rejection_reasons.append(
                f"construction_context has invalid {field}"
            )

    return rejection_reasons


def _direction_weight_rejection_reasons(
    *,
    direction: str,
    target_weight: float,
) -> list[str]:
    if direction == "LONG" and target_weight <= 0:
        return ["LONG risk candidate must have positive target_weight"]

    if direction == "SHORT" and target_weight >= 0:
        return ["SHORT risk candidate must have negative target_weight"]

    if direction == "FLAT" and target_weight != 0:
        return ["FLAT risk candidate must have zero target_weight"]

    return []


def _status_value(
    source: Mapping[str, Any],
    *field_names: str,
) -> str | None:
    for field_name in field_names:
        if field_name in source and source[field_name] is not None:
            return str(source[field_name]).lower()

    return None


def _is_blocked(source: Mapping[str, Any]) -> bool:
    for field_name in ("blocked", "is_blocked"):
        if source.get(field_name) is True:
            return True

    status = _status_value(source, "eligibility_status", "candidate_status")
    return status in BLOCKING_STATUSES


def _valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
