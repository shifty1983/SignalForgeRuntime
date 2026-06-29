from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from src.research.model_candidate import (
    ModelCandidate,
    ModelCandidateEvaluation,
)
from src.research.model_comparison import (
    ModelComparisonReport,
    build_model_comparison_report,
)


@dataclass(frozen=True)
class CandidateEvaluationInputs:
    """Inputs required to evaluate one model candidate."""

    validation_report: Any
    robustness_report: Any
    walk_forward_report: Any


ModelQualityReportBuilder = Callable[
    [ModelCandidate, CandidateEvaluationInputs],
    Any,
]


def run_model_testing_harness(
    candidates: Sequence[ModelCandidate],
    evaluation_inputs_by_candidate_id: Mapping[str, CandidateEvaluationInputs],
    build_quality_report: ModelQualityReportBuilder,
) -> ModelComparisonReport:
    """Evaluate multiple model candidates and return a comparison report."""

    evaluations: list[ModelCandidateEvaluation] = []

    for candidate in candidates:
        inputs = _get_candidate_inputs(
            candidate=candidate,
            evaluation_inputs_by_candidate_id=evaluation_inputs_by_candidate_id,
        )

        quality_report = build_quality_report(candidate, inputs)

        evaluations.append(
            ModelCandidateEvaluation(
                candidate=candidate,
                quality_report=quality_report,
                promoted=_is_promoted(quality_report),
                failure_reasons=_failure_reasons(quality_report),
                quality_score=_quality_score(quality_report),
            )
        )

    return build_model_comparison_report(evaluations)


def _get_candidate_inputs(
    candidate: ModelCandidate,
    evaluation_inputs_by_candidate_id: Mapping[str, CandidateEvaluationInputs],
) -> CandidateEvaluationInputs:
    try:
        return evaluation_inputs_by_candidate_id[candidate.model_id]
    except KeyError as exc:
        raise KeyError(
            f"Missing evaluation inputs for candidate id: {candidate.model_id}"
        ) from exc


def _is_promoted(quality_report: Any) -> bool:
    for attr_name in (
        "promoted",
        "is_promoted",
        "passed",
        "passes_promotion",
    ):
        value = getattr(quality_report, attr_name, None)
        if isinstance(value, bool):
            return value

    promotion_result = getattr(quality_report, "promotion_result", None)
    if promotion_result is not None:
        for attr_name in ("promoted", "passed", "is_promoted"):
            value = getattr(promotion_result, attr_name, None)
            if isinstance(value, bool):
                return value

    summary = getattr(quality_report, "summary", None)
    if isinstance(summary, dict):
        for key in (
            "promoted",
            "is_promoted",
            "passed",
            "passes_promotion",
        ):
            value = summary.get(key)
            if isinstance(value, bool):
                return value

    return False


def _failure_reasons(quality_report: Any) -> tuple[str, ...]:
    for attr_name in (
        "failure_reasons",
        "failures",
        "rejection_reasons",
        "blocking_reasons",
    ):
        value = getattr(quality_report, attr_name, None)
        if value is not None:
            return tuple(str(reason) for reason in value)

    promotion_result = getattr(quality_report, "promotion_result", None)
    if promotion_result is not None:
        for attr_name in (
            "failure_reasons",
            "failures",
            "rejection_reasons",
            "blocking_reasons",
        ):
            value = getattr(promotion_result, attr_name, None)
            if value is not None:
                return tuple(str(reason) for reason in value)

    summary = getattr(quality_report, "summary", None)
    if isinstance(summary, dict):
        for key in (
            "failure_reasons",
            "failures",
            "rejection_reasons",
            "blocking_reasons",
        ):
            value = summary.get(key)
            if value is not None:
                return tuple(str(reason) for reason in value)

    return ()


def _quality_score(quality_report: Any) -> float | None:
    for attr_name in (
        "quality_score",
        "overall_score",
        "promotion_score",
        "score",
    ):
        value = getattr(quality_report, attr_name, None)
        if isinstance(value, int | float):
            return float(value)

    summary = getattr(quality_report, "summary", None)
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

    return None
