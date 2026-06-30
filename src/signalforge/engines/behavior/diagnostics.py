from __future__ import annotations

from numbers import Real

from signalforge.engines.behavior.schema import validate_behavior_output


SCORED_BEHAVIOR_KEYS = {
    "return_score",
    "volatility_score",
    "trend_score",
    "drawdown_score",
    "behavior_score",
    "behavior_state",
}

VALID_BEHAVIOR_STATES = {
    "constructive",
    "neutral",
    "defensive",
}

COMPONENT_SCORE_KEYS = {
    "return_score",
    "volatility_score",
    "trend_score",
    "drawdown_score",
}


def validate_scored_behavior_output(
    result: dict,
) -> None:
    """
    Validate full scored behavior output.

    This extends the base behavior contract by requiring:
    - component scores
    - normalized behavior score
    - behavior state
    """
    validate_behavior_output(result)

    missing = SCORED_BEHAVIOR_KEYS - set(result.keys())

    if missing:
        raise ValueError(
            f"Scored behavior output missing keys: {sorted(missing)}"
        )

    for key in COMPONENT_SCORE_KEYS:
        value = result[key]

        if not isinstance(value, Real):
            raise TypeError(f"{key} must be numeric")

        if value < -1.0 or value > 1.0:
            raise ValueError(
                f"{key} must be between -1.0 and 1.0"
            )

    behavior_score = result["behavior_score"]

    if not isinstance(behavior_score, Real):
        raise TypeError("behavior_score must be numeric")

    if behavior_score < 0.0 or behavior_score > 100.0:
        raise ValueError(
            "behavior_score must be between 0.0 and 100.0"
        )

    behavior_state = result["behavior_state"]

    if behavior_state not in VALID_BEHAVIOR_STATES:
        raise ValueError(
            f"Invalid behavior_state: {behavior_state}"
        )


def diagnose_behavior_output(
    result: dict,
) -> dict:
    """
    Return a diagnostics report for a behavior output.

    This is useful before passing behavior results into:
    - Options Analytics
    - Expected Value
    - Strategy Selection
    - Optimizer
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        validate_scored_behavior_output(result)
    except Exception as exc:
        errors.append(str(exc))

    behavior_score = result.get("behavior_score")
    behavior_state = result.get("behavior_state")
    realized_volatility = result.get("realized_volatility")
    max_drawdown = result.get("max_drawdown")

    if isinstance(realized_volatility, Real) and realized_volatility > 0.60:
        warnings.append("Realized volatility is extremely high")

    if isinstance(max_drawdown, Real) and max_drawdown < -0.40:
        warnings.append("Maximum drawdown is severe")

    if (
        isinstance(behavior_score, Real)
        and behavior_score >= 70.0
        and behavior_state == "defensive"
    ):
        warnings.append(
            "Behavior score and behavior state appear inconsistent"
        )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "behavior_score": behavior_score,
        "behavior_state": behavior_state,
    }


def behavior_output_is_valid(
    result: dict,
) -> bool:
    """
    Boolean validity check for scored behavior output.
    """
    try:
        validate_scored_behavior_output(result)
    except Exception:
        return False

    return True




