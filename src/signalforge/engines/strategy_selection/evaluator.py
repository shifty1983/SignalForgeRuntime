from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from signalforge.engines.strategy_selection.research_adapter import (
    validate_strategy_candidate_input_rows,
)


PASSING_STATUSES = {"passed", "pass", "success", "succeeded", "ok"}
BLOCKING_STATUSES = {"failed", "fail", "invalid", "rejected", "blocked", "error"}


@dataclass(frozen=True)
class StrategyCandidateEvaluation:
    candidate_id: str
    symbol: str
    direction: str
    target_weight: float
    eligible: bool
    rejection_reasons: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    metadata: Mapping[str, Any]
    performance_context: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "target_weight": self.target_weight,
            "eligible": self.eligible,
            "rejection_reasons": list(self.rejection_reasons),
            "diagnostics": dict(self.diagnostics),
            "metadata": dict(self.metadata),
            "performance_context": dict(self.performance_context),
        }


@dataclass(frozen=True)
class StrategySelectionEvaluationReport:
    passed: bool
    candidate_count: int
    eligible_count: int
    rejected_count: int
    evaluations: tuple[StrategyCandidateEvaluation, ...]
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


def evaluate_strategy_candidates(
    rows: Sequence[Mapping[str, Any]],
) -> StrategySelectionEvaluationReport:
    """
    Evaluate strategy-selection candidate input rows for downstream eligibility.

    This does not score, rank, optimize, allocate, or select strategies.
    It only verifies that candidate rows are eligible to enter future strategy
    selection logic.
    """
    contract_validation = validate_strategy_candidate_input_rows(rows)

    if not contract_validation.passed:
        return StrategySelectionEvaluationReport(
            passed=False,
            candidate_count=len(rows),
            eligible_count=0,
            rejected_count=len(rows),
            evaluations=(),
            errors=contract_validation.errors,
        )

    evaluations = tuple(
        _evaluate_candidate_row(row)
        for row in rows
    )

    eligible_count = sum(
        1 for evaluation in evaluations
        if evaluation.eligible
    )
    rejected_count = len(evaluations) - eligible_count

    return StrategySelectionEvaluationReport(
        passed=rejected_count == 0,
        candidate_count=len(evaluations),
        eligible_count=eligible_count,
        rejected_count=rejected_count,
        evaluations=evaluations,
        errors=(),
    )


def _evaluate_candidate_row(
    row: Mapping[str, Any],
) -> StrategyCandidateEvaluation:
    diagnostics = dict(row["diagnostics"])
    metadata = dict(row["metadata"])
    performance_context = dict(row["performance_context"])

    rejection_reasons = _candidate_rejection_reasons(
        diagnostics=diagnostics,
        metadata=metadata,
        performance_context=performance_context,
    )

    return StrategyCandidateEvaluation(
        candidate_id=str(row["candidate_id"]),
        symbol=str(row["symbol"]),
        direction=str(row["direction"]),
        target_weight=float(row["target_weight"]),
        eligible=not rejection_reasons,
        rejection_reasons=tuple(rejection_reasons),
        diagnostics=diagnostics,
        metadata=metadata,
        performance_context=performance_context,
    )


def _candidate_rejection_reasons(
    *,
    diagnostics: Mapping[str, Any],
    metadata: Mapping[str, Any],
    performance_context: Mapping[str, Any],
) -> list[str]:
    rejection_reasons: list[str] = []

    if not diagnostics:
        rejection_reasons.append("missing diagnostics")

    if not performance_context:
        rejection_reasons.append("missing performance_context")

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
