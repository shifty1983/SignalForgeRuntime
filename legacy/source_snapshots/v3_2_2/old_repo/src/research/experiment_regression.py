from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CandidateRankChange:
    candidate_id: str
    baseline_rank: int | None
    current_rank: int | None
    rank_delta: int | None


@dataclass(frozen=True)
class PromotionCandidateChange:
    baseline_promotion_candidate_id: str | None
    current_promotion_candidate_id: str | None
    changed: bool


@dataclass(frozen=True)
class QualityScoreDegradation:
    candidate_id: str
    baseline_quality_score: float
    current_quality_score: float
    degradation: float


@dataclass(frozen=True)
class ExperimentRegressionReport:
    baseline_experiment_id: str
    current_experiment_id: str
    has_regression: bool
    rank_changes: list[CandidateRankChange]
    promotion_candidate_change: PromotionCandidateChange
    new_rejected_candidate_ids: list[str]
    quality_score_degradations: list[QualityScoreDegradation]
    failed_checks: list[str]

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_experiment_runs(
    *,
    baseline_summary: Any,
    current_summary: Any,
    max_allowed_quality_score_degradation: float = 0.05,
    fail_on_rank_change: bool = False,
) -> ExperimentRegressionReport:
    baseline_experiment_id = _extract_experiment_id(baseline_summary)
    current_experiment_id = _extract_experiment_id(current_summary)

    rank_changes = _compare_candidate_ranks(
        baseline_ranked_candidate_ids=_extract_ranked_candidate_ids(baseline_summary),
        current_ranked_candidate_ids=_extract_ranked_candidate_ids(current_summary),
    )

    promotion_candidate_change = _compare_promotion_candidate(
        baseline_promotion_candidate_id=_extract_promotion_candidate_id(
            baseline_summary
        ),
        current_promotion_candidate_id=_extract_promotion_candidate_id(
            current_summary
        ),
    )

    new_rejected_candidate_ids = _detect_new_rejected_candidates(
        baseline_rejected_candidate_ids=_extract_rejected_candidate_ids(
            baseline_summary
        ),
        current_rejected_candidate_ids=_extract_rejected_candidate_ids(
            current_summary
        ),
    )

    quality_score_degradations = _detect_quality_score_degradations(
        baseline_quality_scores=_extract_quality_scores(baseline_summary),
        current_quality_scores=_extract_quality_scores(current_summary),
        max_allowed_quality_score_degradation=max_allowed_quality_score_degradation,
    )

    failed_checks: list[str] = []

    if fail_on_rank_change and rank_changes:
        failed_checks.append("candidate_rank_changes_detected")

    if promotion_candidate_change.changed:
        failed_checks.append("promotion_candidate_changed")

    if new_rejected_candidate_ids:
        failed_checks.append("new_rejected_candidates_detected")

    if quality_score_degradations:
        failed_checks.append("quality_score_degradation_detected")

    return ExperimentRegressionReport(
        baseline_experiment_id=baseline_experiment_id,
        current_experiment_id=current_experiment_id,
        has_regression=bool(failed_checks),
        rank_changes=rank_changes,
        promotion_candidate_change=promotion_candidate_change,
        new_rejected_candidate_ids=new_rejected_candidate_ids,
        quality_score_degradations=quality_score_degradations,
        failed_checks=failed_checks,
    )


def _compare_candidate_ranks(
    *,
    baseline_ranked_candidate_ids: list[str],
    current_ranked_candidate_ids: list[str],
) -> list[CandidateRankChange]:
    baseline_ranks = {
        candidate_id: index + 1
        for index, candidate_id in enumerate(baseline_ranked_candidate_ids)
    }
    current_ranks = {
        candidate_id: index + 1
        for index, candidate_id in enumerate(current_ranked_candidate_ids)
    }

    ordered_candidate_ids = _stable_unique(
        [*baseline_ranked_candidate_ids, *current_ranked_candidate_ids]
    )

    rank_changes: list[CandidateRankChange] = []

    for candidate_id in ordered_candidate_ids:
        baseline_rank = baseline_ranks.get(candidate_id)
        current_rank = current_ranks.get(candidate_id)

        if baseline_rank == current_rank:
            continue

        rank_delta = (
            current_rank - baseline_rank
            if baseline_rank is not None and current_rank is not None
            else None
        )

        rank_changes.append(
            CandidateRankChange(
                candidate_id=candidate_id,
                baseline_rank=baseline_rank,
                current_rank=current_rank,
                rank_delta=rank_delta,
            )
        )

    return rank_changes


def _compare_promotion_candidate(
    *,
    baseline_promotion_candidate_id: str | None,
    current_promotion_candidate_id: str | None,
) -> PromotionCandidateChange:
    return PromotionCandidateChange(
        baseline_promotion_candidate_id=baseline_promotion_candidate_id,
        current_promotion_candidate_id=current_promotion_candidate_id,
        changed=baseline_promotion_candidate_id != current_promotion_candidate_id,
    )


def _detect_new_rejected_candidates(
    *,
    baseline_rejected_candidate_ids: list[str],
    current_rejected_candidate_ids: list[str],
) -> list[str]:
    baseline_rejected = set(baseline_rejected_candidate_ids)

    return [
        candidate_id
        for candidate_id in current_rejected_candidate_ids
        if candidate_id not in baseline_rejected
    ]


def _detect_quality_score_degradations(
    *,
    baseline_quality_scores: dict[str, float],
    current_quality_scores: dict[str, float],
    max_allowed_quality_score_degradation: float,
) -> list[QualityScoreDegradation]:
    degradations: list[QualityScoreDegradation] = []

    for candidate_id, baseline_score in baseline_quality_scores.items():
        if candidate_id not in current_quality_scores:
            continue

        current_score = current_quality_scores[candidate_id]
        degradation = baseline_score - current_score

        if degradation > max_allowed_quality_score_degradation:
            degradations.append(
                QualityScoreDegradation(
                    candidate_id=candidate_id,
                    baseline_quality_score=baseline_score,
                    current_quality_score=current_score,
                    degradation=degradation,
                )
            )

    return degradations


def _extract_experiment_id(summary: Any) -> str:
    return str(
        _get_value(summary, "experiment_id")
        or _get_value(summary, "operation_id")
        or "unknown_experiment"
    )


def _extract_ranked_candidate_ids(summary: Any) -> list[str]:
    return _as_string_list(_get_value(summary, "ranked_candidate_ids", []))


def _extract_rejected_candidate_ids(summary: Any) -> list[str]:
    explicit_rejected = _get_value(summary, "rejected_candidate_ids")

    if explicit_rejected is not None:
        return _as_string_list(explicit_rejected)

    rejected: list[str] = []

    for candidate in _extract_candidate_records(summary):
        status = str(_get_value(candidate, "status", "")).lower()
        candidate_id = _get_value(candidate, "candidate_id")

        if candidate_id and status in {"rejected", "failed", "blocked"}:
            rejected.append(str(candidate_id))

    return rejected


def _extract_promotion_candidate_id(summary: Any) -> str | None:
    for key in (
        "promotion_candidate_id",
        "best_candidate_id",
        "selected_candidate_id",
        "promoted_candidate_id",
    ):
        value = _get_value(summary, key)

        if value:
            return str(value)

    promotion_candidate_ids = _get_value(summary, "promotion_candidate_ids")

    if promotion_candidate_ids:
        candidate_ids = _as_string_list(promotion_candidate_ids)
        return candidate_ids[0] if candidate_ids else None

    return None


def _extract_quality_scores(summary: Any) -> dict[str, float]:
    for key in (
        "candidate_quality_scores",
        "quality_scores",
        "candidate_scores",
    ):
        value = _get_value(summary, key)

        if isinstance(value, Mapping):
            return {
                str(candidate_id): float(score)
                for candidate_id, score in value.items()
                if score is not None
            }

    quality_scores: dict[str, float] = {}

    for candidate in _extract_candidate_records(summary):
        candidate_id = _get_value(candidate, "candidate_id")
        quality_score = _extract_quality_score(candidate)

        if candidate_id is not None and quality_score is not None:
            quality_scores[str(candidate_id)] = quality_score

    return quality_scores


def _extract_candidate_records(summary: Any) -> list[Any]:
    for key in (
        "candidate_summaries",
        "candidate_results",
        "candidate_evaluations",
        "candidates",
    ):
        value = _get_value(summary, key)

        if isinstance(value, list):
            return value

    return []


def _extract_quality_score(candidate: Any) -> float | None:
    for key in (
        "quality_score",
        "model_quality_score",
        "aggregate_quality_score",
        "score",
    ):
        value = _get_value(candidate, key)

        if value is not None:
            return float(value)

    quality_report = _get_value(candidate, "quality_report")

    if quality_report is not None:
        for key in (
            "quality_score",
            "model_quality_score",
            "aggregate_quality_score",
            "score",
        ):
            value = _get_value(quality_report, key)

            if value is not None:
                return float(value)

    return None


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)

    return getattr(source, key, default)


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    return [str(item) for item in value]


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        unique_values.append(value)

    return unique_values
