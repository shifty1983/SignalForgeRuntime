from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.risk_management.evaluator import (
    RiskCandidateEvaluation,
    RiskManagementEvaluationReport,
)


@dataclass(frozen=True)
class RiskManagementCandidateSummary:
    risk_input_id: str
    portfolio_input_id: str
    candidate_id: str
    symbol: str
    direction: str
    target_weight: float
    selection_rank: int
    selection_score: float
    eligible: bool
    approved: bool
    rejection_reasons: tuple[str, ...]

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
            "approved": self.approved,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class RiskManagementReport:
    passed: bool
    risk_status: str
    candidate_count: int
    eligible_count: int
    rejected_count: int
    approved_count: int
    approved_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    total_risk_exposure: float
    long_exposure: float
    short_exposure: float
    net_exposure: float
    candidate_summaries: tuple[RiskManagementCandidateSummary, ...]
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "risk_status": self.risk_status,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "approved_count": self.approved_count,
            "approved_candidate_ids": list(self.approved_candidate_ids),
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "total_risk_exposure": self.total_risk_exposure,
            "long_exposure": self.long_exposure,
            "short_exposure": self.short_exposure,
            "net_exposure": self.net_exposure,
            "candidate_summaries": [
                summary.to_dict()
                for summary in self.candidate_summaries
            ],
            "blocking_reasons": list(self.blocking_reasons),
        }


def build_risk_management_report(
    evaluation_report: RiskManagementEvaluationReport,
) -> RiskManagementReport:
    """
    Build a deterministic risk management report from risk candidate evaluations.

    This report preserves approved target weights and summarizes risk exposure.
    It does not apply portfolio risk limits, concentration limits, stop rules,
    position resizing, order generation, or execution.
    """
    if evaluation_report.errors:
        return _blocked_risk_management_report(
            evaluation_report=evaluation_report,
            blocking_reasons=evaluation_report.errors,
        )

    eligible_evaluations = tuple(
        evaluation
        for evaluation in evaluation_report.evaluations
        if evaluation.eligible
    )

    if not eligible_evaluations:
        return _blocked_risk_management_report(
            evaluation_report=evaluation_report,
            blocking_reasons=("no eligible risk management candidates",),
        )

    approved_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in eligible_evaluations
    )
    rejected_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in evaluation_report.evaluations
        if not evaluation.eligible
    )

    candidate_summaries = tuple(
        _candidate_summary(
            evaluation=evaluation,
            approved_candidate_ids=approved_candidate_ids,
        )
        for evaluation in evaluation_report.evaluations
    )

    return RiskManagementReport(
        passed=True,
        risk_status="approved",
        candidate_count=evaluation_report.candidate_count,
        eligible_count=evaluation_report.eligible_count,
        rejected_count=evaluation_report.rejected_count,
        approved_count=len(approved_candidate_ids),
        approved_candidate_ids=approved_candidate_ids,
        rejected_candidate_ids=rejected_candidate_ids,
        total_risk_exposure=_total_risk_exposure(eligible_evaluations),
        long_exposure=_long_exposure(eligible_evaluations),
        short_exposure=_short_exposure(eligible_evaluations),
        net_exposure=_net_exposure(eligible_evaluations),
        candidate_summaries=candidate_summaries,
        blocking_reasons=(),
    )


def _blocked_risk_management_report(
    *,
    evaluation_report: RiskManagementEvaluationReport,
    blocking_reasons: tuple[str, ...],
) -> RiskManagementReport:
    rejected_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in evaluation_report.evaluations
        if not evaluation.eligible
    )

    candidate_summaries = tuple(
        _candidate_summary(
            evaluation=evaluation,
            approved_candidate_ids=(),
        )
        for evaluation in evaluation_report.evaluations
    )

    return RiskManagementReport(
        passed=False,
        risk_status="blocked",
        candidate_count=evaluation_report.candidate_count,
        eligible_count=evaluation_report.eligible_count,
        rejected_count=evaluation_report.rejected_count,
        approved_count=0,
        approved_candidate_ids=(),
        rejected_candidate_ids=rejected_candidate_ids,
        total_risk_exposure=0.0,
        long_exposure=0.0,
        short_exposure=0.0,
        net_exposure=0.0,
        candidate_summaries=candidate_summaries,
        blocking_reasons=tuple(blocking_reasons),
    )


def _candidate_summary(
    *,
    evaluation: RiskCandidateEvaluation,
    approved_candidate_ids: tuple[str, ...],
) -> RiskManagementCandidateSummary:
    return RiskManagementCandidateSummary(
        risk_input_id=evaluation.risk_input_id,
        portfolio_input_id=evaluation.portfolio_input_id,
        candidate_id=evaluation.candidate_id,
        symbol=evaluation.symbol,
        direction=evaluation.direction,
        target_weight=evaluation.target_weight,
        selection_rank=evaluation.selection_rank,
        selection_score=evaluation.selection_score,
        eligible=evaluation.eligible,
        approved=evaluation.candidate_id in approved_candidate_ids,
        rejection_reasons=evaluation.rejection_reasons,
    )


def _total_risk_exposure(
    evaluations: tuple[RiskCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(abs(evaluation.target_weight) for evaluation in evaluations)
    )


def _long_exposure(
    evaluations: tuple[RiskCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(
            evaluation.target_weight
            for evaluation in evaluations
            if evaluation.target_weight > 0
        )
    )


def _short_exposure(
    evaluations: tuple[RiskCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(
            abs(evaluation.target_weight)
            for evaluation in evaluations
            if evaluation.target_weight < 0
        )
    )


def _net_exposure(
    evaluations: tuple[RiskCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(evaluation.target_weight for evaluation in evaluations)
    )


def _rounded(value: float) -> float:
    return round(float(value), 10)
