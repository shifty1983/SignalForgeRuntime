from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from src.research.robustness import (
    RobustnessReport,
    RobustnessReportStatus,
)
from src.research.validation import (
    ResearchValidationReport,
    ResearchValidationStatus,
)
from src.research.walk_forward import (
    WalkForwardReport,
    WalkForwardReportStatus,
)


class ResearchPromotionDecision(str, Enum):
    REJECTED = "rejected"
    NEEDS_MORE_DATA = "needs_more_data"
    WATCHLIST = "watchlist"
    PROMOTED_TO_BACKTEST = "promoted_to_backtest"
    PROMOTED_TO_STRATEGY_SELECTION = "promoted_to_strategy_selection"


@dataclass(frozen=True)
class ResearchScoreComponent:
    name: str
    value: float
    weight: float
    weighted_value: float
    passed: bool | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "weight": self.weight,
            "weighted_value": self.weighted_value,
            "passed": self.passed,
            "description": self.description,
        }


@dataclass(frozen=True)
class ResearchScoreReport:
    decision: ResearchPromotionDecision
    score: float
    components: Mapping[str, ResearchScoreComponent]
    issues: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def rejected(self) -> bool:
        return self.decision == ResearchPromotionDecision.REJECTED

    @property
    def needs_more_data(self) -> bool:
        return self.decision == ResearchPromotionDecision.NEEDS_MORE_DATA

    @property
    def watchlist(self) -> bool:
        return self.decision == ResearchPromotionDecision.WATCHLIST

    @property
    def promoted(self) -> bool:
        return self.decision in {
            ResearchPromotionDecision.PROMOTED_TO_BACKTEST,
            ResearchPromotionDecision.PROMOTED_TO_STRATEGY_SELECTION,
        }

    def component_value(self, name: str) -> float:
        return self.components[name].value

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "score": self.score,
            "components": {
                name: component.to_dict()
                for name, component in self.components.items()
            },
            "issues": list(self.issues),
            "metadata": dict(self.metadata),
        }


DEFAULT_RESEARCH_SCORE_WEIGHTS: dict[str, float] = {
    "validation_status": 0.20,
    "sample_quality": 0.15,
    "hit_rate": 0.15,
    "average_signed_return": 0.15,
    "information_coefficient": 0.10,
    "robustness": 0.15,
    "walk_forward": 0.10,
}


def score_research(
    validation_report: ResearchValidationReport,
    robustness_report: RobustnessReport | None = None,
    walk_forward_report: WalkForwardReport | None = None,
    weights: Mapping[str, float] | None = None,
    min_rows: int = 100,
    min_active_signals: int = 25,
    min_watchlist_score: float = 0.45,
    min_promote_to_backtest_score: float = 0.65,
    min_promote_to_strategy_score: float = 0.80,
    min_robustness_pass_rate: float = 0.50,
    min_walk_forward_pass_rate: float = 0.50,
) -> ResearchScoreReport:
    score_weights = normalize_score_weights(weights or DEFAULT_RESEARCH_SCORE_WEIGHTS)

    components = build_research_score_components(
        validation_report=validation_report,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        weights=score_weights,
        min_rows=min_rows,
        min_active_signals=min_active_signals,
        min_robustness_pass_rate=min_robustness_pass_rate,
        min_walk_forward_pass_rate=min_walk_forward_pass_rate,
    )

    score = sum(component.weighted_value for component in components.values())
    issues = build_research_score_issues(
        validation_report=validation_report,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        components=components,
        min_robustness_pass_rate=min_robustness_pass_rate,
        min_walk_forward_pass_rate=min_walk_forward_pass_rate,
    )

    decision = derive_research_promotion_decision(
        score=score,
        validation_report=validation_report,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        min_watchlist_score=min_watchlist_score,
        min_promote_to_backtest_score=min_promote_to_backtest_score,
        min_promote_to_strategy_score=min_promote_to_strategy_score,
        min_robustness_pass_rate=min_robustness_pass_rate,
        min_walk_forward_pass_rate=min_walk_forward_pass_rate,
    )

    return ResearchScoreReport(
        decision=decision,
        score=score,
        components=components,
        issues=tuple(issues),
        metadata={
            "min_rows": min_rows,
            "min_active_signals": min_active_signals,
            "min_watchlist_score": min_watchlist_score,
            "min_promote_to_backtest_score": min_promote_to_backtest_score,
            "min_promote_to_strategy_score": min_promote_to_strategy_score,
            "min_robustness_pass_rate": min_robustness_pass_rate,
            "min_walk_forward_pass_rate": min_walk_forward_pass_rate,
        },
    )


def build_research_score_components(
    validation_report: ResearchValidationReport,
    robustness_report: RobustnessReport | None,
    walk_forward_report: WalkForwardReport | None,
    weights: Mapping[str, float],
    min_rows: int,
    min_active_signals: int,
    min_robustness_pass_rate: float,
    min_walk_forward_pass_rate: float,
) -> dict[str, ResearchScoreComponent]:
    row_count = _metric_value(validation_report, "row_count")
    active_signal_count = _metric_value(validation_report, "active_signal_count")
    hit_rate = _metric_value(validation_report, "hit_rate")
    average_signed_return = _metric_value(validation_report, "average_signed_return")
    information_coefficient = _metric_value(
        validation_report,
        "information_coefficient",
    )

    validation_status_score = _validation_status_score(validation_report.status)
    sample_quality_score = _sample_quality_score(
        row_count=row_count,
        active_signal_count=active_signal_count,
        min_rows=min_rows,
        min_active_signals=min_active_signals,
    )
    hit_rate_score = _bounded_metric_score(hit_rate)
    average_signed_return_score = _positive_return_score(average_signed_return)
    information_coefficient_score = _information_coefficient_score(
        information_coefficient
    )
    robustness_score = _robustness_score(robustness_report)
    walk_forward_score = _walk_forward_score(walk_forward_report)

    return {
        "validation_status": _component(
            name="validation_status",
            value=validation_status_score,
            weight=weights["validation_status"],
            passed=validation_report.status == ResearchValidationStatus.PASSED,
            description="Pass/fail state from research validation.",
        ),
        "sample_quality": _component(
            name="sample_quality",
            value=sample_quality_score,
            weight=weights["sample_quality"],
            passed=sample_quality_score >= 1.0,
            description="Rows and active signals relative to minimum requirements.",
        ),
        "hit_rate": _component(
            name="hit_rate",
            value=hit_rate_score,
            weight=weights["hit_rate"],
            passed=hit_rate is not None and hit_rate >= 0.50,
            description="Active signal hit rate converted directly to a 0-1 score.",
        ),
        "average_signed_return": _component(
            name="average_signed_return",
            value=average_signed_return_score,
            weight=weights["average_signed_return"],
            passed=average_signed_return is not None and average_signed_return > 0,
            description="Positive signed return receives credit; non-positive receives none.",
        ),
        "information_coefficient": _component(
            name="information_coefficient",
            value=information_coefficient_score,
            weight=weights["information_coefficient"],
            passed=information_coefficient is not None
            and abs(information_coefficient) > 0,
            description="Absolute IC clipped to a 0-1 score.",
        ),
        "robustness": _component(
            name="robustness",
            value=robustness_score,
            weight=weights["robustness"],
            passed=robustness_report is not None
            and robustness_report.pass_rate() >= min_robustness_pass_rate,
            description="Robustness scenario pass rate.",
        ),
        "walk_forward": _component(
            name="walk_forward",
            value=walk_forward_score,
            weight=weights["walk_forward"],
            passed=walk_forward_report is not None
            and walk_forward_report.pass_rate() >= min_walk_forward_pass_rate,
            description="Walk-forward window pass rate.",
        ),
    }


def derive_research_promotion_decision(
    score: float,
    validation_report: ResearchValidationReport,
    robustness_report: RobustnessReport | None = None,
    walk_forward_report: WalkForwardReport | None = None,
    min_watchlist_score: float = 0.45,
    min_promote_to_backtest_score: float = 0.65,
    min_promote_to_strategy_score: float = 0.80,
    min_robustness_pass_rate: float = 0.50,
    min_walk_forward_pass_rate: float = 0.50,
) -> ResearchPromotionDecision:
    if validation_report.status == ResearchValidationStatus.INSUFFICIENT_DATA:
        return ResearchPromotionDecision.NEEDS_MORE_DATA

    if robustness_report is not None:
        if robustness_report.status == RobustnessReportStatus.INSUFFICIENT_DATA:
            return ResearchPromotionDecision.NEEDS_MORE_DATA

    if walk_forward_report is not None:
        if walk_forward_report.status == WalkForwardReportStatus.INSUFFICIENT_DATA:
            return ResearchPromotionDecision.NEEDS_MORE_DATA

    if validation_report.status == ResearchValidationStatus.FAILED:
        if score >= min_watchlist_score:
            return ResearchPromotionDecision.WATCHLIST

        return ResearchPromotionDecision.REJECTED

    robustness_pass_rate = (
        robustness_report.pass_rate() if robustness_report is not None else None
    )
    walk_forward_pass_rate = (
        walk_forward_report.pass_rate() if walk_forward_report is not None else None
    )

    robustness_ok = (
        robustness_pass_rate is None
        or robustness_pass_rate >= min_robustness_pass_rate
    )
    walk_forward_ok = (
        walk_forward_pass_rate is None
        or walk_forward_pass_rate >= min_walk_forward_pass_rate
    )

    if (
        score >= min_promote_to_strategy_score
        and robustness_ok
        and walk_forward_ok
        and robustness_report is not None
        and walk_forward_report is not None
    ):
        return ResearchPromotionDecision.PROMOTED_TO_STRATEGY_SELECTION

    if score >= min_promote_to_backtest_score and robustness_ok:
        return ResearchPromotionDecision.PROMOTED_TO_BACKTEST

    if score >= min_watchlist_score:
        return ResearchPromotionDecision.WATCHLIST

    return ResearchPromotionDecision.REJECTED


def build_research_score_issues(
    validation_report: ResearchValidationReport,
    robustness_report: RobustnessReport | None,
    walk_forward_report: WalkForwardReport | None,
    components: Mapping[str, ResearchScoreComponent],
    min_robustness_pass_rate: float,
    min_walk_forward_pass_rate: float,
) -> list[str]:
    issues: list[str] = []

    if validation_report.status != ResearchValidationStatus.PASSED:
        issues.append(f"Validation status is {validation_report.status.value}.")

    for issue in validation_report.issues:
        issues.append(f"Validation issue: {issue}")

    if components["sample_quality"].value < 1.0:
        issues.append("Sample quality is below configured minimums.")

    if components["average_signed_return"].value <= 0.0:
        issues.append("Average signed return is not positive.")

    if robustness_report is None:
        issues.append("Robustness report was not provided.")
    elif robustness_report.pass_rate() < min_robustness_pass_rate:
        issues.append(
            f"Robustness pass rate below minimum: "
            f"{robustness_report.pass_rate()} < {min_robustness_pass_rate}"
        )

    if walk_forward_report is None:
        issues.append("Walk-forward report was not provided.")
    elif walk_forward_report.pass_rate() < min_walk_forward_pass_rate:
        issues.append(
            f"Walk-forward pass rate below minimum: "
            f"{walk_forward_report.pass_rate()} < {min_walk_forward_pass_rate}"
        )

    return issues


def normalize_score_weights(weights: Mapping[str, float]) -> dict[str, float]:
    missing = set(DEFAULT_RESEARCH_SCORE_WEIGHTS) - set(weights)

    if missing:
        raise ValueError(f"Missing score weights: {', '.join(sorted(missing))}")

    cleaned = {
        name: float(weights[name])
        for name in DEFAULT_RESEARCH_SCORE_WEIGHTS
    }

    if any(weight < 0 for weight in cleaned.values()):
        raise ValueError("Score weights cannot be negative.")

    total = sum(cleaned.values())

    if total <= 0:
        raise ValueError("Score weights must sum to a positive value.")

    return {
        name: weight / total
        for name, weight in cleaned.items()
    }


def _component(
    name: str,
    value: float,
    weight: float,
    passed: bool | None,
    description: str,
) -> ResearchScoreComponent:
    bounded_value = _clip(value, 0.0, 1.0)

    return ResearchScoreComponent(
        name=name,
        value=bounded_value,
        weight=weight,
        weighted_value=bounded_value * weight,
        passed=passed,
        description=description,
    )


def _metric_value(
    report: ResearchValidationReport,
    metric_name: str,
) -> float | int | None:
    try:
        return report.metric_value(metric_name)
    except KeyError:
        return None


def _validation_status_score(status: ResearchValidationStatus) -> float:
    if status == ResearchValidationStatus.PASSED:
        return 1.0

    if status == ResearchValidationStatus.FAILED:
        return 0.25

    return 0.0


def _sample_quality_score(
    row_count: float | int | None,
    active_signal_count: float | int | None,
    min_rows: int,
    min_active_signals: int,
) -> float:
    if min_rows <= 0:
        raise ValueError("min_rows must be greater than zero.")

    if min_active_signals <= 0:
        raise ValueError("min_active_signals must be greater than zero.")

    row_score = (row_count or 0) / min_rows
    active_score = (active_signal_count or 0) / min_active_signals

    return _clip(min(row_score, active_score), 0.0, 1.0)


def _bounded_metric_score(value: float | int | None) -> float:
    if value is None:
        return 0.0

    return _clip(float(value), 0.0, 1.0)


def _positive_return_score(value: float | int | None) -> float:
    if value is None:
        return 0.0

    return 1.0 if value > 0 else 0.0


def _information_coefficient_score(value: float | int | None) -> float:
    if value is None:
        return 0.0

    return _clip(abs(float(value)), 0.0, 1.0)


def _robustness_score(report: RobustnessReport | None) -> float:
    if report is None:
        return 0.0

    return _clip(report.pass_rate(), 0.0, 1.0)


def _walk_forward_score(report: WalkForwardReport | None) -> float:
    if report is None:
        return 0.0

    return _clip(report.pass_rate(), 0.0, 1.0)


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
