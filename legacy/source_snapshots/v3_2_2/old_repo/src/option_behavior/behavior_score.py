from __future__ import annotations

from typing import Mapping

from src.option_behavior.schema import validate_option_behavior_output


IV_SCORES = {
    "low_iv": 0.25,
    "normal_iv": 1.0,
    "high_iv": 0.0,
    "extreme_iv": -1.0,
}

VOL_PREMIUM_SCORES = {
    "rich_vol": 0.50,
    "neutral_vol": 1.0,
    "cheap_vol": 0.50,
    "unknown_vol_premium": 0.0,
}

LIQUIDITY_SCORES = {
    "high_liquidity": 1.0,
    "medium_liquidity": 0.25,
    "low_liquidity": -0.50,
    "untradable_liquidity": -1.0,
}

SKEW_SCORES = {
    "balanced_skew": 1.0,
    "downside_rich_skew": 0.25,
    "upside_rich_skew": 0.25,
    "distorted_skew": -0.50,
    "unknown_skew": 0.0,
}

TERM_STRUCTURE_SCORES = {
    "flat_term_structure": 1.0,
    "contango_term_structure": 0.50,
    "backwardated_term_structure": 0.25,
    "unknown_term_structure": 0.0,
}

GREEK_SCORES = {
    "normal_greek_risk": 1.0,
    "elevated_greek_risk": 0.25,
    "high_greek_risk": -0.75,
    "unknown_greek_risk": 0.0,
}

DEFAULT_WEIGHTS = {
    "iv_score": 0.15,
    "vol_premium_score": 0.10,
    "liquidity_score": 0.25,
    "skew_score": 0.15,
    "term_structure_score": 0.10,
    "greek_score": 0.25,
}


def _lookup_score(
    label: str,
    score_map: Mapping[str, float],
    context: str,
) -> float:
    if label not in score_map:
        raise ValueError(
            f"Unknown {context} label: {label}"
        )

    return score_map[label]


def score_option_behavior_components(
    behavior: dict,
) -> dict:
    validate_option_behavior_output(behavior)

    return {
        "iv_score": _lookup_score(
            behavior["iv_behavior"],
            IV_SCORES,
            "iv_behavior",
        ),
        "vol_premium_score": _lookup_score(
            behavior["vol_premium_behavior"],
            VOL_PREMIUM_SCORES,
            "vol_premium_behavior",
        ),
        "liquidity_score": _lookup_score(
            behavior["liquidity_behavior"],
            LIQUIDITY_SCORES,
            "liquidity_behavior",
        ),
        "skew_score": _lookup_score(
            behavior["skew_behavior"],
            SKEW_SCORES,
            "skew_behavior",
        ),
        "term_structure_score": _lookup_score(
            behavior["term_structure_behavior"],
            TERM_STRUCTURE_SCORES,
            "term_structure_behavior",
        ),
        "greek_score": _lookup_score(
            behavior["greek_behavior"],
            GREEK_SCORES,
            "greek_behavior",
        ),
    }


def weighted_option_behavior_score(
    component_scores: dict,
    weights: dict | None = None,
) -> float:
    active_weights = weights or DEFAULT_WEIGHTS

    missing = [
        key for key in active_weights
        if key not in component_scores
    ]

    if missing:
        raise ValueError(
            f"Missing option behavior component scores: {missing}"
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


def classify_option_behavior_score(
    score: float,
    supportive_threshold: float = 70.0,
    constrained_threshold: float = 40.0,
) -> str:
    if score >= supportive_threshold:
        return "supportive"

    if score <= constrained_threshold:
        return "constrained"

    return "neutral"


def build_option_behavior_score(
    behavior: dict,
    weights: dict | None = None,
) -> dict:
    component_scores = score_option_behavior_components(behavior)

    score = weighted_option_behavior_score(
        component_scores=component_scores,
        weights=weights,
    )

    state = classify_option_behavior_score(score)

    return {
        **component_scores,
        "option_behavior_score": score,
        "option_behavior_state": state,
    }
