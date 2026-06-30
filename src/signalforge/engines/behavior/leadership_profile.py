from __future__ import annotations

from collections.abc import Mapping
from typing import Any


LEADERSHIP_STATES = {
    "market_leader",
    "sector_leader",
    "emerging_leader",
    "market_performer",
    "improving_laggard",
    "market_laggard",
    "weakening_leader",
}

LEADERSHIP_TRENDS = {
    "strengthening",
    "stable",
    "weakening",
    "recovering",
}


def build_leadership_profile(behavior: Mapping[str, Any] | None) -> dict[str, Any]:
    """Classify leadership / laggard behavior from existing asset behavior signals.

    This profile intentionally sits on top of the existing trend-quality,
    momentum, and benchmark-relative-strength profiles. It does not fetch data,
    route orders, select options, model fills, or trigger any automatic action.
    """

    if not isinstance(behavior, Mapping):
        return _empty_profile("behavior must be a mapping")

    relative_strength_state = _clean(behavior.get("relative_strength_state"))
    relative_strength_trend = _clean(behavior.get("relative_strength_trend"))
    trend_quality = _clean(behavior.get("trend_quality"))
    momentum_state = _clean(behavior.get("momentum_state"))

    leadership_score = score_leadership_profile(
        relative_strength_state=relative_strength_state,
        relative_strength_trend=relative_strength_trend,
        trend_quality=trend_quality,
        momentum_state=momentum_state,
    )
    leadership_state = classify_leadership_state(
        relative_strength_state=relative_strength_state,
        relative_strength_trend=relative_strength_trend,
        trend_quality=trend_quality,
        momentum_state=momentum_state,
        leadership_score=leadership_score,
    )
    leadership_trend = classify_leadership_trend(
        relative_strength_trend=relative_strength_trend,
        momentum_state=momentum_state,
        leadership_state=leadership_state,
    )

    return {
        "leadership_status": "ready",
        "leadership_state": leadership_state,
        "leadership_score": leadership_score,
        "leadership_trend": leadership_trend,
        "leadership_warning": None,
    }


def classify_leadership_state(
    *,
    relative_strength_state: str | None,
    relative_strength_trend: str | None,
    trend_quality: str | None,
    momentum_state: str | None,
    leadership_score: float | None = None,
) -> str:
    rs = _clean(relative_strength_state)
    rs_trend = _clean(relative_strength_trend)
    trend = _clean(trend_quality)
    momentum = _clean(momentum_state)
    score = 0.0 if leadership_score is None else float(leadership_score)

    outperforming = rs in {"strong_outperformer", "outperformer"}
    strongly_outperforming = rs == "strong_outperformer"
    underperforming = rs in {"strong_underperformer", "underperformer"}
    strongly_underperforming = rs == "strong_underperformer"
    improving = rs_trend == "improving_relative_strength"
    deteriorating = rs_trend == "deteriorating_relative_strength"
    strong_trend = trend in {"strong_trend", "trend_accelerating"}
    weak_or_choppy = trend in {"weak_trend", "choppy_trend", "trend_breakdown"}
    positive_momentum = momentum in {
        "positive_momentum",
        "persistent_momentum",
        "accelerating_momentum",
        "strong_positive_momentum",
    }
    negative_momentum = momentum in {
        "negative_momentum",
        "decelerating_momentum",
        "reversal_risk",
        "strong_negative_momentum",
    }

    if outperforming and deteriorating:
        return "weakening_leader"

    if underperforming and improving:
        return "improving_laggard"

    if strongly_outperforming and strong_trend and positive_momentum and score >= 0.75:
        return "market_leader"

    if outperforming and (improving or strong_trend or positive_momentum):
        return "emerging_leader"

    if strongly_underperforming or (underperforming and (weak_or_choppy or negative_momentum)):
        return "market_laggard"

    return "market_performer"


def classify_leadership_trend(
    *,
    relative_strength_trend: str | None,
    momentum_state: str | None,
    leadership_state: str | None,
) -> str:
    rs_trend = _clean(relative_strength_trend)
    momentum = _clean(momentum_state)
    state = _clean(leadership_state)

    if state == "improving_laggard" or rs_trend == "improving_relative_strength":
        return "recovering"

    if state == "weakening_leader" or rs_trend == "deteriorating_relative_strength":
        return "weakening"

    if momentum in {"positive_momentum", "persistent_momentum", "accelerating_momentum"}:
        return "strengthening"

    return "stable"


def score_leadership_profile(
    *,
    relative_strength_state: str | None,
    relative_strength_trend: str | None,
    trend_quality: str | None,
    momentum_state: str | None,
) -> float:
    score = 0.50

    rs = _clean(relative_strength_state)
    if rs == "strong_outperformer":
        score += 0.25
    elif rs == "outperformer":
        score += 0.15
    elif rs == "underperformer":
        score -= 0.15
    elif rs == "strong_underperformer":
        score -= 0.25

    rs_trend = _clean(relative_strength_trend)
    if rs_trend == "improving_relative_strength":
        score += 0.10
    elif rs_trend == "deteriorating_relative_strength":
        score -= 0.10

    trend = _clean(trend_quality)
    if trend in {"strong_trend", "trend_accelerating"}:
        score += 0.10
    elif trend in {"choppy_trend", "trend_breakdown"}:
        score -= 0.10
    elif trend == "weak_trend":
        score -= 0.05

    momentum = _clean(momentum_state)
    if momentum in {"positive_momentum", "persistent_momentum", "accelerating_momentum"}:
        score += 0.05
    elif momentum in {"negative_momentum", "decelerating_momentum", "reversal_risk"}:
        score -= 0.05

    return round(max(0.0, min(1.0, score)), 4)


def _empty_profile(reason: str) -> dict[str, Any]:
    return {
        "leadership_status": "blocked",
        "leadership_state": None,
        "leadership_score": None,
        "leadership_trend": None,
        "leadership_warning": reason,
    }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


