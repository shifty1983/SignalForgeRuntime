from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.portfolio_construction.evaluator import (
    PortfolioCandidateEvaluation,
    PortfolioConstructionEvaluationReport,
)


@dataclass(frozen=True)
class PortfolioConstructionCandidateSummary:
    portfolio_input_id: str
    candidate_id: str
    symbol: str
    direction: str
    target_weight: float
    selection_rank: int
    selection_score: float
    eligible: bool
    accepted: bool
    rejection_reasons: tuple[str, ...]

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
            "accepted": self.accepted,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class PortfolioConstructionReport:
    passed: bool
    construction_status: str
    candidate_count: int
    eligible_count: int
    rejected_count: int
    accepted_count: int
    accepted_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    total_target_exposure: float
    long_exposure: float
    short_exposure: float
    net_exposure: float
    candidate_summaries: tuple[PortfolioConstructionCandidateSummary, ...]
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "construction_status": self.construction_status,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "accepted_count": self.accepted_count,
            "accepted_candidate_ids": list(self.accepted_candidate_ids),
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "total_target_exposure": self.total_target_exposure,
            "long_exposure": self.long_exposure,
            "short_exposure": self.short_exposure,
            "net_exposure": self.net_exposure,
            "candidate_summaries": [
                summary.to_dict()
                for summary in self.candidate_summaries
            ],
            "blocking_reasons": list(self.blocking_reasons),
        }


def build_portfolio_construction_report(
    evaluation_report: PortfolioConstructionEvaluationReport,
) -> PortfolioConstructionReport:
    """
    Build a deterministic portfolio construction report from portfolio candidate
    evaluations.

    This report preserves accepted target weights and summarizes exposure.
    It does not optimize, rebalance, resize, generate orders, or execute trades.
    """
    if evaluation_report.errors:
        return _blocked_portfolio_construction_report(
            evaluation_report=evaluation_report,
            blocking_reasons=evaluation_report.errors,
        )

    eligible_evaluations = tuple(
        evaluation
        for evaluation in evaluation_report.evaluations
        if evaluation.eligible
    )

    if not eligible_evaluations:
        return _blocked_portfolio_construction_report(
            evaluation_report=evaluation_report,
            blocking_reasons=("no eligible portfolio construction candidates",),
        )

    accepted_candidate_ids = tuple(
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
            accepted_candidate_ids=accepted_candidate_ids,
        )
        for evaluation in evaluation_report.evaluations
    )

    return PortfolioConstructionReport(
        passed=True,
        construction_status="constructed",
        candidate_count=evaluation_report.candidate_count,
        eligible_count=evaluation_report.eligible_count,
        rejected_count=evaluation_report.rejected_count,
        accepted_count=len(accepted_candidate_ids),
        accepted_candidate_ids=accepted_candidate_ids,
        rejected_candidate_ids=rejected_candidate_ids,
        total_target_exposure=_total_target_exposure(eligible_evaluations),
        long_exposure=_long_exposure(eligible_evaluations),
        short_exposure=_short_exposure(eligible_evaluations),
        net_exposure=_net_exposure(eligible_evaluations),
        candidate_summaries=candidate_summaries,
        blocking_reasons=(),
    )


def _blocked_portfolio_construction_report(
    *,
    evaluation_report: PortfolioConstructionEvaluationReport,
    blocking_reasons: tuple[str, ...],
) -> PortfolioConstructionReport:
    rejected_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in evaluation_report.evaluations
        if not evaluation.eligible
    )

    candidate_summaries = tuple(
        _candidate_summary(
            evaluation=evaluation,
            accepted_candidate_ids=(),
        )
        for evaluation in evaluation_report.evaluations
    )

    return PortfolioConstructionReport(
        passed=False,
        construction_status="blocked",
        candidate_count=evaluation_report.candidate_count,
        eligible_count=evaluation_report.eligible_count,
        rejected_count=evaluation_report.rejected_count,
        accepted_count=0,
        accepted_candidate_ids=(),
        rejected_candidate_ids=rejected_candidate_ids,
        total_target_exposure=0.0,
        long_exposure=0.0,
        short_exposure=0.0,
        net_exposure=0.0,
        candidate_summaries=candidate_summaries,
        blocking_reasons=tuple(blocking_reasons),
    )


def _candidate_summary(
    *,
    evaluation: PortfolioCandidateEvaluation,
    accepted_candidate_ids: tuple[str, ...],
) -> PortfolioConstructionCandidateSummary:
    return PortfolioConstructionCandidateSummary(
        portfolio_input_id=evaluation.portfolio_input_id,
        candidate_id=evaluation.candidate_id,
        symbol=evaluation.symbol,
        direction=evaluation.direction,
        target_weight=evaluation.target_weight,
        selection_rank=evaluation.selection_rank,
        selection_score=evaluation.selection_score,
        eligible=evaluation.eligible,
        accepted=evaluation.candidate_id in accepted_candidate_ids,
        rejection_reasons=evaluation.rejection_reasons,
    )


def _total_target_exposure(
    evaluations: tuple[PortfolioCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(abs(evaluation.target_weight) for evaluation in evaluations)
    )


def _long_exposure(
    evaluations: tuple[PortfolioCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(
            evaluation.target_weight
            for evaluation in evaluations
            if evaluation.target_weight > 0
        )
    )


def _short_exposure(
    evaluations: tuple[PortfolioCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(
            abs(evaluation.target_weight)
            for evaluation in evaluations
            if evaluation.target_weight < 0
        )
    )


def _net_exposure(
    evaluations: tuple[PortfolioCandidateEvaluation, ...],
) -> float:
    return _rounded(
        sum(evaluation.target_weight for evaluation in evaluations)
    )


def _rounded(value: float) -> float:
    return round(float(value), 10)
