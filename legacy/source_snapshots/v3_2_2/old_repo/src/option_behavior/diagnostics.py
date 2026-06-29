from __future__ import annotations

from numbers import Real

from src.option_behavior.schema import validate_option_behavior_output


SCORED_OPTION_BEHAVIOR_KEYS = {
    "iv_score",
    "vol_premium_score",
    "liquidity_score",
    "skew_score",
    "term_structure_score",
    "greek_score",
    "option_behavior_score",
    "option_behavior_state",
}

VALID_OPTION_BEHAVIOR_STATES = {
    "supportive",
    "neutral",
    "constrained",
}

COMPONENT_SCORE_KEYS = {
    "iv_score",
    "vol_premium_score",
    "liquidity_score",
    "skew_score",
    "term_structure_score",
    "greek_score",
}


def validate_scored_option_behavior_output(
    result: dict,
) -> None:
    validate_option_behavior_output(result)

    missing = SCORED_OPTION_BEHAVIOR_KEYS - set(result.keys())

    if missing:
        raise ValueError(
            f"Scored option behavior output missing keys: {sorted(missing)}"
        )

    for key in COMPONENT_SCORE_KEYS:
        value = result[key]

        if not isinstance(value, Real):
            raise TypeError(f"{key} must be numeric")

        if value < -1.0 or value > 1.0:
            raise ValueError(
                f"{key} must be between -1.0 and 1.0"
            )

    option_behavior_score = result["option_behavior_score"]

    if not isinstance(option_behavior_score, Real):
        raise TypeError("option_behavior_score must be numeric")

    if option_behavior_score < 0.0 or option_behavior_score > 100.0:
        raise ValueError(
            "option_behavior_score must be between 0.0 and 100.0"
        )

    option_behavior_state = result["option_behavior_state"]

    if option_behavior_state not in VALID_OPTION_BEHAVIOR_STATES:
        raise ValueError(
            f"Invalid option_behavior_state: {option_behavior_state}"
        )


def diagnose_option_behavior_output(
    result: dict,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        validate_scored_option_behavior_output(result)
    except Exception as exc:
        errors.append(str(exc))

    option_behavior_score = result.get("option_behavior_score")
    option_behavior_state = result.get("option_behavior_state")

    if result.get("iv_behavior") == "extreme_iv":
        warnings.append("Implied volatility is extreme")

    if result.get("liquidity_behavior") == "untradable_liquidity":
        warnings.append("Option liquidity is untradable")

    if result.get("greek_behavior") == "high_greek_risk":
        warnings.append("Greek risk is high")

    if result.get("skew_behavior") == "distorted_skew":
        warnings.append("Skew behavior is distorted")

    if (
        isinstance(option_behavior_score, Real)
        and option_behavior_score >= 70.0
        and option_behavior_state == "constrained"
    ):
        warnings.append(
            "Option behavior score and state appear inconsistent"
        )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "option_behavior_score": option_behavior_score,
        "option_behavior_state": option_behavior_state,
    }


def option_behavior_output_is_valid(
    result: dict,
) -> bool:
    try:
        validate_scored_option_behavior_output(result)
    except Exception:
        return False

    return True
