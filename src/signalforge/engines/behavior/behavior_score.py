from __future__ import annotations

from typing import Mapping

from signalforge.engines.behavior.schema import validate_behavior_output


RETURN_SCORES = {
    "positive": 1.0,
    "neutral": 0.0,
    "negative": -1.0,
}

VOLATILITY_SCORES = {
    "low_vol": 0.5,
    "normal_vol": 1.0,
    "high_vol": -0.5,
}

TREND_SCORES = {
    "uptrend": 1.0,
    "sideways": 0.0,
    "downtrend": -1.0,
    "insufficient_data": 0.0,
}

DRAWDOWN_SCORES = {
    "shallow_drawdown": 1.0,
    "moderate_drawdown": 0.0,
    "deep_drawdown": -1.0,
}


DEFAULT_WEIGHTS = {
    "return_score": 0.30,
    "volatility_score": 0.25,
    "trend_score": 0.30,
    "drawdown_score": 0.15,
}


def _lookup_score(
    label: str,
    score_map: Mapping[str, float],
    context: str,
) -> float:
    """
    Convert a behavior label into a numeric score.
    """
    if label not in score_map:
        raise ValueError(
            f"Unknown {context} label: {label}"
        )

    return score_map[label]


def score_behavior_components(
    behavior: dict,
) -> dict:
    """
    Convert behavior classifier labels into component scores.
    """
    validate_behavior_output(behavior)

    return {
        "return_score": _lookup_score(
            behavior["return_behavior"],
            RETURN_SCORES,
            "return_behavior",
        ),
        "volatility_score": _lookup_score(
            behavior["volatility_behavior"],
            VOLATILITY_SCORES,
            "volatility_behavior",
        ),
        "trend_score": _lookup_score(
            behavior["trend_behavior"],
            TREND_SCORES,
            "trend_behavior",
        ),
        "drawdown_score": _lookup_score(
            behavior["drawdown_behavior"],
            DRAWDOWN_SCORES,
            "drawdown_behavior",
        ),
    }


def weighted_behavior_score(
    component_scores: dict,
    weights: dict | None = None,
) -> float:
    """
    Convert component scores into a normalized 0-100 behavior score.

    Raw components are scored from -1 to +1.
    Final score is normalized where:

    0   = very defensive / unfavorable behavior
    50  = neutral behavior
    100 = strongly constructive behavior
    """
    active_weights = weights or DEFAULT_WEIGHTS

    missing = [
        key for key in active_weights
        if key not in component_scores
    ]

    if missing:
        raise ValueError(
            f"Missing component scores: {missing}"
        )

    total_weight = sum(active_weights.values())

    if total_weight <= 0:
        raise ValueError("Total weight must be positive")

    raw_score = sum(
        component_scores[key] * weight
        for key, weight in active_weights.items()
    ) / total_weight

    normalized_score = ((raw_score + 1.0) / 2.0) * 100.0

    return round(float(normalized_score), 2)


def classify_behavior_score(
    score: float,
    constructive_threshold: float = 70.0,
    defensive_threshold: float = 40.0,
) -> str:
    """
    Classify a normalized behavior score.
    """
    if score >= constructive_threshold:
        return "constructive"

    if score <= defensive_threshold:
        return "defensive"

    return "neutral"


def build_behavior_score(
    behavior: dict,
    weights: dict | None = None,
) -> dict:
    """
    Build full behavior score output from behavior classifier results.
    """
    component_scores = score_behavior_components(behavior)

    score = weighted_behavior_score(
        component_scores=component_scores,
        weights=weights,
    )

    state = classify_behavior_score(score)

    return {
        **component_scores,
        "behavior_score": score,
        "behavior_state": state,
    }




