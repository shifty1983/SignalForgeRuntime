from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.research.model_candidate import ModelCandidateEvaluation


@dataclass(frozen=True)
class ModelComparisonReport:
    """Aggregated comparison across multiple candidate model evaluations."""

    evaluations: tuple[ModelCandidateEvaluation, ...]
    promoted_candidates: tuple[str, ...]
    rejected_candidates: tuple[str, ...]
    best_candidate_id: str | None

    @property
    def candidate_count(self) -> int:
        return len(self.evaluations)

    @property
    def promoted_count(self) -> int:
        return len(self.promoted_candidates)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_candidates)

    @property
    def has_promoted_candidate(self) -> bool:
        return self.best_candidate_id is not None


def build_model_comparison_report(
    evaluations: Iterable[ModelCandidateEvaluation],
) -> ModelComparisonReport:
    """Build a stable comparison report from candidate evaluations."""

    evaluation_tuple = tuple(evaluations)

    promoted = tuple(
        evaluation.candidate.model_id
        for evaluation in evaluation_tuple
        if evaluation.promoted
    )

    rejected = tuple(
        evaluation.candidate.model_id
        for evaluation in evaluation_tuple
        if not evaluation.promoted
    )

    best_candidate_id = _select_best_candidate_id(evaluation_tuple)

    return ModelComparisonReport(
        evaluations=evaluation_tuple,
        promoted_candidates=promoted,
        rejected_candidates=rejected,
        best_candidate_id=best_candidate_id,
    )
    
def build_model_comparison_summary(
    report: ModelComparisonReport,
) -> dict[str, object]:
    """Build a JSON-safe summary for operation records and logs."""

    return {
        "candidate_count": report.candidate_count,
        "promoted_candidate_count": report.promoted_count,
        "rejected_candidate_count": report.rejected_count,
        "promoted_candidates": list(report.promoted_candidates),
        "rejected_candidates": list(report.rejected_candidates),
        "best_candidate_id": report.best_candidate_id,
        "has_promoted_candidate": report.has_promoted_candidate,
        "evaluations": [
            {
                "model_id": evaluation.candidate.model_id,
                "model_name": evaluation.candidate.model_name,
                "factor_names": list(evaluation.candidate.factor_names),
                "promoted": evaluation.promoted,
                "quality_score": evaluation.quality_score,
                "failure_reasons": list(evaluation.failure_reasons),
            }
            for evaluation in report.evaluations
        ],
    }

def _select_best_candidate_id(
    evaluations: tuple[ModelCandidateEvaluation, ...],
) -> str | None:
    passing_evaluations = [
        evaluation
        for evaluation in evaluations
        if evaluation.promoted
    ]

    if not passing_evaluations:
        return None

    ranked = sorted(
        passing_evaluations,
        key=lambda evaluation: _safe_quality_score(evaluation),
        reverse=True,
    )

    return ranked[0].candidate.model_id


def _safe_quality_score(evaluation: ModelCandidateEvaluation) -> float:
    if evaluation.quality_score is not None:
        return evaluation.quality_score

    report = evaluation.quality_report

    for attr_name in (
        "quality_score",
        "overall_score",
        "promotion_score",
        "score",
    ):
        value = getattr(report, attr_name, None)
        if isinstance(value, int | float):
            return float(value)

    summary = getattr(report, "summary", None)

    if isinstance(summary, dict):
        for key in (
            "quality_score",
            "overall_score",
            "promotion_score",
            "score",
        ):
            value = summary.get(key)
            if isinstance(value, int | float):
                return float(value)

    return 0.0
