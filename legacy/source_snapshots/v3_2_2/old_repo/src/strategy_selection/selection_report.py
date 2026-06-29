from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.strategy_selection.evaluator import (
    StrategyCandidateEvaluation,
    StrategySelectionEvaluationReport,
)


DEFAULT_MAX_SELECTED_CANDIDATES = 1

SELECTION_SCORE_FIELDS = (
    "selection_score",
    "quality_score",
    "factor_score",
    "signal_strength",
)


@dataclass(frozen=True)
class StrategySelectionCandidateSummary:
    candidate_id: str
    symbol: str
    direction: str
    target_weight: float
    eligible: bool
    selected: bool
    rank: int | None
    selection_score: float
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "target_weight": self.target_weight,
            "eligible": self.eligible,
            "selected": self.selected,
            "rank": self.rank,
            "selection_score": self.selection_score,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class StrategySelectionReport:
    passed: bool
    selection_status: str
    candidate_count: int
    eligible_count: int
    rejected_count: int
    selected_count: int
    selected_candidate_ids: tuple[str, ...]
    ranked_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    candidate_summaries: tuple[StrategySelectionCandidateSummary, ...]
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "selection_status": self.selection_status,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "selected_count": self.selected_count,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "ranked_candidate_ids": list(self.ranked_candidate_ids),
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "candidate_summaries": [
                summary.to_dict()
                for summary in self.candidate_summaries
            ],
            "blocking_reasons": list(self.blocking_reasons),
        }


def build_strategy_selection_report(
    evaluation_report: StrategySelectionEvaluationReport,
    *,
    max_selected_candidates: int = DEFAULT_MAX_SELECTED_CANDIDATES,
) -> StrategySelectionReport:
    """
    Build a deterministic strategy selection report from candidate evaluations.

    This ranks already-eligible candidates and records selected candidate IDs.
    It does not optimize weights, construct portfolios, generate orders, or
    mutate candidate rows.
    """
    if max_selected_candidates < 1:
        raise ValueError("max_selected_candidates must be at least 1")

    if evaluation_report.errors:
        return _blocked_selection_report(
            evaluation_report=evaluation_report,
            blocking_reasons=evaluation_report.errors,
        )

    eligible_candidates = [
        evaluation
        for evaluation in evaluation_report.evaluations
        if evaluation.eligible
    ]

    if not eligible_candidates:
        return _blocked_selection_report(
            evaluation_report=evaluation_report,
            blocking_reasons=("no eligible strategy candidates",),
        )

    ranked_candidates = tuple(
        sorted(
            eligible_candidates,
            key=_ranking_key,
        )
    )

    selected_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in ranked_candidates[:max_selected_candidates]
    )
    ranked_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in ranked_candidates
    )
    rejected_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in evaluation_report.evaluations
        if not evaluation.eligible
    )

    rank_by_candidate_id = {
        evaluation.candidate_id: rank
        for rank, evaluation in enumerate(ranked_candidates, start=1)
    }

    candidate_summaries = tuple(
        _candidate_summary(
            evaluation=evaluation,
            selected_candidate_ids=selected_candidate_ids,
            rank=rank_by_candidate_id.get(evaluation.candidate_id),
        )
        for evaluation in evaluation_report.evaluations
    )

    return StrategySelectionReport(
        passed=True,
        selection_status="selected",
        candidate_count=evaluation_report.candidate_count,
        eligible_count=evaluation_report.eligible_count,
        rejected_count=evaluation_report.rejected_count,
        selected_count=len(selected_candidate_ids),
        selected_candidate_ids=selected_candidate_ids,
        ranked_candidate_ids=ranked_candidate_ids,
        rejected_candidate_ids=rejected_candidate_ids,
        candidate_summaries=candidate_summaries,
        blocking_reasons=(),
    )


def _blocked_selection_report(
    *,
    evaluation_report: StrategySelectionEvaluationReport,
    blocking_reasons: tuple[str, ...],
) -> StrategySelectionReport:
    rejected_candidate_ids = tuple(
        evaluation.candidate_id
        for evaluation in evaluation_report.evaluations
        if not evaluation.eligible
    )

    candidate_summaries = tuple(
        _candidate_summary(
            evaluation=evaluation,
            selected_candidate_ids=(),
            rank=None,
        )
        for evaluation in evaluation_report.evaluations
    )

    return StrategySelectionReport(
        passed=False,
        selection_status="blocked",
        candidate_count=evaluation_report.candidate_count,
        eligible_count=evaluation_report.eligible_count,
        rejected_count=evaluation_report.rejected_count,
        selected_count=0,
        selected_candidate_ids=(),
        ranked_candidate_ids=(),
        rejected_candidate_ids=rejected_candidate_ids,
        candidate_summaries=candidate_summaries,
        blocking_reasons=tuple(blocking_reasons),
    )


def _candidate_summary(
    *,
    evaluation: StrategyCandidateEvaluation,
    selected_candidate_ids: tuple[str, ...],
    rank: int | None,
) -> StrategySelectionCandidateSummary:
    return StrategySelectionCandidateSummary(
        candidate_id=evaluation.candidate_id,
        symbol=evaluation.symbol,
        direction=evaluation.direction,
        target_weight=evaluation.target_weight,
        eligible=evaluation.eligible,
        selected=evaluation.candidate_id in selected_candidate_ids,
        rank=rank,
        selection_score=_selection_score(evaluation),
        rejection_reasons=evaluation.rejection_reasons,
    )


def _ranking_key(
    evaluation: StrategyCandidateEvaluation,
) -> tuple[float, str, str]:
    return (
        -_selection_score(evaluation),
        evaluation.symbol,
        evaluation.candidate_id,
    )


def _selection_score(
    evaluation: StrategyCandidateEvaluation,
) -> float:
    for field in SELECTION_SCORE_FIELDS:
        value = evaluation.diagnostics.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)

    return 0.0
