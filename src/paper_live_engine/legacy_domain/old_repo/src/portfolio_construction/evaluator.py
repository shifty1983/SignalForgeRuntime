from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.portfolio_construction.strategy_adapter import (
    validate_portfolio_construction_input_rows,
)


PASSING_STATUSES = {"passed", "pass", "success", "succeeded", "ok"}
BLOCKING_STATUSES = {"failed", "fail", "invalid", "rejected", "blocked", "error"}


@dataclass(frozen=True)
class PortfolioCandidateEvaluation:
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

    def to_dict(self) -> dict[str, Any]:
        return {
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
        }


@dataclass(frozen=True)
class PortfolioConstructionEvaluationReport:
    passed: bool
    candidate_count: int
    eligible_count: int
    rejected_count: int
    evaluations: tuple[PortfolioCandidateEvaluation, ...]
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


def evaluate_portfolio_construction_candidates(
    rows: Sequence[Mapping[str, Any]],
) -> PortfolioConstructionEvaluationReport:
    """
    Evaluate portfolio-construction input rows for downstream readiness.

    This does not optimize, rebalance, allocate capital, build trades, or mutate
    target weights.
    """
    contract_validation = validate_portfolio_construction_input_rows(rows)

    if not contract_validation.passed:
        return PortfolioConstructionEvaluationReport(
            passed=False,
            candidate_count=len(rows),
            eligible_count=0,
            rejected_count=len(rows),
            evaluations=(),
            errors=contract_validation.errors,
        )

    evaluations = tuple(
        _evaluate_portfolio_input_row(row)
        for row in rows
    )

    eligible_count = sum(
        1 for evaluation in evaluations
        if evaluation.eligible
    )
    rejected_count = len(evaluations) - eligible_count

    return PortfolioConstructionEvaluationReport(
        passed=rejected_count == 0,
        candidate_count=len(evaluations),
        eligible_count=eligible_count,
        rejected_count=rejected_count,
        evaluations=evaluations,
        errors=(),
    )


def _evaluate_portfolio_input_row(
    row: Mapping[str, Any],
) -> PortfolioCandidateEvaluation:
    diagnostics = dict(row["diagnostics"])
    metadata = dict(row["metadata"])
    performance_context = dict(row["performance_context"])

    rejection_reasons = _portfolio_rejection_reasons(
        direction=str(row["direction"]),
        target_weight=float(row["target_weight"]),
        diagnostics=diagnostics,
        metadata=metadata,
        performance_context=performance_context,
    )

    return PortfolioCandidateEvaluation(
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
    )


def _portfolio_rejection_reasons(
    *,
    direction: str,
    target_weight: float,
    diagnostics: Mapping[str, Any],
    metadata: Mapping[str, Any],
    performance_context: Mapping[str, Any],
) -> list[str]:
    rejection_reasons: list[str] = []

    if not diagnostics:
        rejection_reasons.append("missing diagnostics")

    if not performance_context:
        rejection_reasons.append("missing performance_context")

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


def _direction_weight_rejection_reasons(
    *,
    direction: str,
    target_weight: float,
) -> list[str]:
    if direction == "LONG" and target_weight <= 0:
        return ["LONG candidate must have positive target_weight"]

    if direction == "SHORT" and target_weight >= 0:
        return ["SHORT candidate must have negative target_weight"]

    if direction == "FLAT" and target_weight != 0:
        return ["FLAT candidate must have zero target_weight"]

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
