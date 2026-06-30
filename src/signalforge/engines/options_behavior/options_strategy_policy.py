from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.engines.options_strategy.catalog import UNDEFINED_RISK_STRATEGIES


EXCLUDED_ACTIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_maintenance_actions",
    "automatic_defense_actions",
]

ALL_DEFINED_RISK_POLICY_STRATEGIES = [
    "long_call",
    "long_put",
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
    "protective_put",
    "collar",
    "covered_call",
]

DEBIT_FAVORED_STRATEGIES = [
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "calendar_spread",
    "diagonal_spread",
]

CREDIT_FAVORED_STRATEGIES = [
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "covered_call",
    "collar",
]

BALANCED_FAVORED_STRATEGIES = [
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
    "calendar_spread",
    "diagonal_spread",
]

COMPLEX_MULTI_LEG_STRATEGIES = [
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
]

HIGH_GAMMA_REVIEW_STRATEGIES = [
    "long_call",
    "long_put",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
]

VALID_POLICY_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}

OPTION_POLICY_STATUS_SCORES = {
    "preferred": 3.0,
    "allowed": 2.0,
    "needs_review": 1.0,
    "blocked": 0.0,
    "not_found": 1.0,
}

OPTION_SCORE_ADJUSTMENTS = {
    "preferred": 1.0,
    "allowed": 0.5,
    "needs_review": -0.5,
    "blocked": 0.0,
    "not_found": -0.5,
}

OPTION_FIT_DECISIONS = {
    "preferred": "favor",
    "allowed": "allow",
    "needs_review": "manual_review",
    "blocked": "block",
    "not_found": "manual_review",
}


REQUIRED_OPTION_BEHAVIOR_KEYS = [
    "iv_behavior",
    "vol_premium_behavior",
    "liquidity_behavior",
    "skew_behavior",
    "term_structure_behavior",
    "greek_behavior",
]


def build_option_behavior_options_strategy_policy(
    option_behavior_result: Mapping[str, Any] | None,
    *,
    symbol: str | None = None,
) -> dict[str, Any]:
    """
    Convert option behavior into an options-strategy policy.

    This policy is strategy-family guidance only. It does not create contracts,
    choose strikes/expirations, calculate expected value, size trades, route
    orders, submit orders, model fills, or create automatic maintenance/defense
    actions.
    """

    if not isinstance(option_behavior_result, Mapping):
        return _blocked_policy(
            symbol=symbol,
            blocked_reasons=["invalid option_behavior_result shape"],
        )

    source_symbol = symbol or _string_or_none(option_behavior_result.get("symbol"))
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    missing_keys = [
        key
        for key in REQUIRED_OPTION_BEHAVIOR_KEYS
        if _string_or_none(option_behavior_result.get(key)) is None
    ]
    if missing_keys:
        blocked_reasons.append(
            "missing option behavior fields: " + ", ".join(sorted(missing_keys))
        )

    option_behavior_state = _string_or_none(
        option_behavior_result.get("option_behavior_state")
    )
    if option_behavior_state == "constrained":
        warnings.append("option behavior state is constrained")

    iv_behavior = _string_or_none(option_behavior_result.get("iv_behavior"))
    vol_premium_behavior = _string_or_none(
        option_behavior_result.get("vol_premium_behavior")
    )
    liquidity_behavior = _string_or_none(
        option_behavior_result.get("liquidity_behavior")
    )
    skew_behavior = _string_or_none(option_behavior_result.get("skew_behavior"))
    term_structure_behavior = _string_or_none(
        option_behavior_result.get("term_structure_behavior")
    )
    greek_behavior = _string_or_none(option_behavior_result.get("greek_behavior"))

    if liquidity_behavior == "untradable_liquidity":
        blocked_reasons.append("option chain has untradable liquidity")
    elif liquidity_behavior == "low_liquidity":
        warnings.append("option chain liquidity is low; complex structures need review")

    if iv_behavior == "extreme_iv":
        warnings.append("extreme implied volatility requires manual review")

    if greek_behavior == "high_greek_risk":
        warnings.append("option chain has high greek risk")
    elif greek_behavior == "elevated_greek_risk":
        warnings.append("option chain has elevated greek risk")

    if _has_unknown_behavior(option_behavior_result):
        warnings.append("one or more option behavior components are unknown")

    volatility_pricing_bias = _volatility_pricing_bias(
        iv_behavior=iv_behavior,
        vol_premium_behavior=vol_premium_behavior,
    )
    liquidity_posture = _liquidity_posture(liquidity_behavior)
    greek_risk_posture = _greek_risk_posture(greek_behavior)
    term_structure_bias = _term_structure_bias(term_structure_behavior)
    skew_bias = _skew_bias(skew_behavior)
    strategy_policy = _strategy_policy(
        volatility_pricing_bias=volatility_pricing_bias,
        liquidity_behavior=liquidity_behavior,
        greek_behavior=greek_behavior,
        iv_behavior=iv_behavior,
        term_structure_behavior=term_structure_behavior,
    )

    status = _policy_status(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
        volatility_pricing_bias=volatility_pricing_bias,
        liquidity_behavior=liquidity_behavior,
        greek_behavior=greek_behavior,
    )

    return {
        "artifact_type": "option_behavior_options_strategy_policy",
        "status": status,
        "is_ready": status == "ready",
        "symbol": source_symbol,
        "iv_behavior": iv_behavior,
        "vol_premium_behavior": vol_premium_behavior,
        "liquidity_behavior": liquidity_behavior,
        "skew_behavior": skew_behavior,
        "term_structure_behavior": term_structure_behavior,
        "greek_behavior": greek_behavior,
        "option_behavior_score": option_behavior_result.get("option_behavior_score"),
        "option_behavior_state": option_behavior_state,
        "volatility_pricing_bias": volatility_pricing_bias,
        "liquidity_posture": liquidity_posture,
        "greek_risk_posture": greek_risk_posture,
        "term_structure_bias": term_structure_bias,
        "skew_bias": skew_bias,
        "strategy_policy": strategy_policy,
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_option_behavior_summary": _source_option_behavior_summary(
            option_behavior_result
        ),
        "excluded": EXCLUDED_ACTIONS,
    }


def evaluate_option_behavior_option_strategy_fit(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Evaluate one defined-risk option strategy candidate against the current
    option-behavior strategy policy.
    """

    strategy = _strategy_from_candidate(strategy_candidate)
    input_errors = _fit_input_errors(
        strategy_candidate=strategy_candidate,
        option_behavior_options_policy=option_behavior_options_policy,
        strategy=strategy,
    )
    if input_errors:
        return _blocked_fit(strategy=strategy, blocked_reasons=input_errors)

    assert isinstance(option_behavior_options_policy, Mapping)

    if strategy in UNDEFINED_RISK_STRATEGIES:
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=["undefined risk strategies are hard-blocked"],
        )

    policy_status = _policy_status_for_strategy(option_behavior_options_policy, strategy)
    if policy_status is None:
        return {
            "artifact_type": "option_behavior_option_strategy_fit",
            "status": "needs_review",
            "is_ready": False,
            "strategy": strategy,
            "policy_status": "not_found",
            "fit_score": OPTION_POLICY_STATUS_SCORES["not_found"],
            "score_adjustment": OPTION_SCORE_ADJUSTMENTS["not_found"],
            "decision": OPTION_FIT_DECISIONS["not_found"],
            "volatility_pricing_bias": option_behavior_options_policy.get(
                "volatility_pricing_bias"
            ),
            "liquidity_posture": option_behavior_options_policy.get(
                "liquidity_posture"
            ),
            "warnings": ["strategy not found in option behavior policy; manual review required"],
            "blocked_reasons": [],
            "excluded": EXCLUDED_ACTIONS,
        }

    if policy_status == "blocked":
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=["strategy blocked by option behavior policy"],
            option_behavior_options_policy=option_behavior_options_policy,
            policy_status=policy_status,
        )

    status = "needs_review" if policy_status == "needs_review" else "ready"
    warnings = []
    if policy_status == "needs_review":
        warnings.append("strategy requires manual review under current option behavior")

    return {
        "artifact_type": "option_behavior_option_strategy_fit",
        "status": status,
        "is_ready": status == "ready",
        "strategy": strategy,
        "policy_status": policy_status,
        "fit_score": OPTION_POLICY_STATUS_SCORES[policy_status],
        "score_adjustment": OPTION_SCORE_ADJUSTMENTS[policy_status],
        "decision": OPTION_FIT_DECISIONS[policy_status],
        "volatility_pricing_bias": option_behavior_options_policy.get(
            "volatility_pricing_bias"
        ),
        "liquidity_posture": option_behavior_options_policy.get("liquidity_posture"),
        "greek_risk_posture": option_behavior_options_policy.get(
            "greek_risk_posture"
        ),
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
    }


def apply_option_behavior_policy_to_option_candidates(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Apply option-behavior strategy policy to defined-risk strategy candidates.

    Output groups:
    - candidates: option-behavior-ready candidates only
    - needs_review_candidates: usable candidates that need manual review
    - blocked_candidates: candidates blocked by option behavior or defined-risk gate
    """

    input_errors = _application_input_errors(
        option_strategy_candidates=option_strategy_candidates,
        option_behavior_options_policy=option_behavior_options_policy,
    )
    if input_errors:
        return _blocked_application(blocked_reasons=input_errors)

    assert isinstance(option_strategy_candidates, Mapping)
    assert isinstance(option_behavior_options_policy, Mapping)

    source_status = _clean(option_strategy_candidates.get("status"))
    if source_status == "blocked":
        return _blocked_application(
            symbol=_string_or_none(option_strategy_candidates.get("symbol")),
            market_regime=_string_or_none(
                option_strategy_candidates.get("market_regime")
            ),
            option_behavior_options_policy=option_behavior_options_policy,
            warnings=_strings(option_strategy_candidates.get("warnings")),
            blocked_reasons=_strings(option_strategy_candidates.get("blocked_reasons"))
            or ["source option strategy candidates are blocked"],
            source_candidate_summary=_source_candidate_summary(option_strategy_candidates),
        )

    ready_candidates: list[dict[str, Any]] = []
    needs_review_candidates: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []
    warnings: list[str] = list(_strings(option_strategy_candidates.get("warnings")))
    blocked_reasons: list[str] = []

    for candidate in _mapping_list(option_strategy_candidates.get("candidates")):
        fit = evaluate_option_behavior_option_strategy_fit(
            strategy_candidate=candidate,
            option_behavior_options_policy=option_behavior_options_policy,
        )
        enriched = _enrich_candidate_with_fit(candidate=candidate, fit=fit)
        fit_status = _clean(fit.get("status"))

        if fit_status == "ready":
            ready_candidates.append(enriched)
        elif fit_status == "needs_review":
            needs_review_candidates.append(enriched)
            warnings.extend(_strings(fit.get("warnings")))
        else:
            blocked_candidates.append(enriched)
            blocked_reasons.extend(_strings(fit.get("blocked_reasons")))

    ready_candidates = sorted(
        ready_candidates,
        key=lambda candidate: (
            -_float(candidate.get("option_behavior_adjusted_score")),
            candidate.get("strategy", ""),
        ),
    )
    needs_review_candidates = sorted(
        needs_review_candidates,
        key=lambda candidate: (
            -_float(candidate.get("option_behavior_adjusted_score")),
            candidate.get("strategy", ""),
        ),
    )
    blocked_candidates = sorted(
        blocked_candidates,
        key=lambda candidate: candidate.get("strategy", ""),
    )

    status = _application_status(
        source_status=source_status,
        ready_count=len(ready_candidates),
        needs_review_count=len(needs_review_candidates),
        blocked_count=len(blocked_candidates),
        warnings=warnings,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append(
            "no option strategy candidates remain after option behavior policy"
        )

    return {
        "artifact_type": "option_behavior_filtered_option_strategy_candidates",
        "status": status,
        "is_ready": status == "ready",
        "symbol": _string_or_none(option_strategy_candidates.get("symbol")),
        "market_regime": _string_or_none(option_strategy_candidates.get("market_regime")),
        "volatility_pricing_bias": option_behavior_options_policy.get(
            "volatility_pricing_bias"
        ),
        "liquidity_posture": option_behavior_options_policy.get("liquidity_posture"),
        "greek_risk_posture": option_behavior_options_policy.get(
            "greek_risk_posture"
        ),
        "candidate_count": len(ready_candidates),
        "needs_review_count": len(needs_review_candidates),
        "blocked_count": len(blocked_candidates),
        "source_candidate_count": int(
            option_strategy_candidates.get("candidate_count", 0) or 0
        ),
        "candidates": ready_candidates,
        "needs_review_candidates": needs_review_candidates,
        "blocked_candidates": blocked_candidates,
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_candidate_summary": _source_candidate_summary(
            option_strategy_candidates
        ),
        "option_behavior_policy_summary": _policy_summary(
            option_behavior_options_policy
        ),
        "excluded": EXCLUDED_ACTIONS,
    }


def _blocked_policy(
    *,
    symbol: str | None,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "option_behavior_options_strategy_policy",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "iv_behavior": None,
        "vol_premium_behavior": None,
        "liquidity_behavior": None,
        "skew_behavior": None,
        "term_structure_behavior": None,
        "greek_behavior": None,
        "option_behavior_score": None,
        "option_behavior_state": None,
        "volatility_pricing_bias": "blocked",
        "liquidity_posture": "blocked",
        "greek_risk_posture": "blocked",
        "term_structure_bias": "unknown",
        "skew_bias": "unknown",
        "strategy_policy": _blocked_strategy_policy(),
        "warnings": _dedupe_strings(list(warnings or [])),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_option_behavior_summary": {},
        "excluded": EXCLUDED_ACTIONS,
    }


def _blocked_strategy_policy() -> dict[str, list[str]]:
    return {
        "preferred": [],
        "allowed": [],
        "needs_review": [],
        "blocked": [
            *ALL_DEFINED_RISK_POLICY_STRATEGIES,
            *sorted(UNDEFINED_RISK_STRATEGIES),
        ],
    }


def _strategy_policy(
    *,
    volatility_pricing_bias: str,
    liquidity_behavior: str | None,
    greek_behavior: str | None,
    iv_behavior: str | None,
    term_structure_behavior: str | None,
) -> dict[str, list[str]]:
    if liquidity_behavior == "untradable_liquidity":
        return _blocked_strategy_policy()

    preferred: list[str]
    allowed: list[str]
    needs_review: list[str]
    blocked: list[str] = list(sorted(UNDEFINED_RISK_STRATEGIES))

    if volatility_pricing_bias == "debit_favored":
        preferred = list(DEBIT_FAVORED_STRATEGIES)
        allowed = ["long_call", "long_put", "protective_put", "collar"]
        needs_review = [
            "put_credit_spread",
            "call_credit_spread",
            "iron_condor",
            "iron_butterfly",
            "covered_call",
        ]
    elif volatility_pricing_bias == "credit_favored":
        preferred = list(CREDIT_FAVORED_STRATEGIES)
        allowed = ["iron_butterfly", "protective_put"]
        needs_review = [
            "long_call",
            "long_put",
            "bull_call_debit_spread",
            "bear_put_debit_spread",
            "calendar_spread",
            "diagonal_spread",
        ]
    elif volatility_pricing_bias == "avoid_new_debit":
        preferred = ["put_credit_spread", "call_credit_spread", "collar"]
        allowed = ["iron_condor", "covered_call", "protective_put"]
        needs_review = [
            "long_call",
            "long_put",
            "bull_call_debit_spread",
            "bear_put_debit_spread",
            "iron_butterfly",
            "calendar_spread",
            "diagonal_spread",
        ]
    else:
        preferred = list(BALANCED_FAVORED_STRATEGIES)
        allowed = ["iron_condor", "protective_put", "collar", "covered_call"]
        needs_review = ["long_call", "long_put", "iron_butterfly"]

    if term_structure_behavior == "contango_term_structure":
        preferred = _promote(preferred, allowed, ["calendar_spread", "diagonal_spread"])
        allowed = [item for item in allowed if item not in preferred]
    elif term_structure_behavior == "backwardated_term_structure":
        preferred = [item for item in preferred if item not in {"calendar_spread", "diagonal_spread"}]
        needs_review = _add_unique(needs_review, ["calendar_spread", "diagonal_spread"])

    if liquidity_behavior == "low_liquidity":
        blocked = _add_unique(blocked, COMPLEX_MULTI_LEG_STRATEGIES)
        needs_review = _add_unique(
            needs_review,
            [
                item
                for item in [*preferred, *allowed]
                if item not in COMPLEX_MULTI_LEG_STRATEGIES
            ],
        )
        preferred = []
        allowed = []

    if greek_behavior == "high_greek_risk":
        blocked = _add_unique(blocked, ["iron_butterfly"])
        needs_review = _add_unique(needs_review, HIGH_GAMMA_REVIEW_STRATEGIES)
        preferred = [item for item in preferred if item not in HIGH_GAMMA_REVIEW_STRATEGIES]
        allowed = [item for item in allowed if item not in HIGH_GAMMA_REVIEW_STRATEGIES]
    elif greek_behavior == "elevated_greek_risk":
        needs_review = _add_unique(needs_review, ["iron_butterfly", "long_call", "long_put"])
        preferred = [item for item in preferred if item not in {"iron_butterfly", "long_call", "long_put"}]
        allowed = [item for item in allowed if item not in {"iron_butterfly", "long_call", "long_put"}]

    if iv_behavior == "extreme_iv":
        needs_review = _add_unique(needs_review, [*preferred, *allowed])
        preferred = []
        allowed = []

    return _normalized_strategy_policy(
        preferred=preferred,
        allowed=allowed,
        needs_review=needs_review,
        blocked=blocked,
    )


def _normalized_strategy_policy(
    *,
    preferred: Sequence[str],
    allowed: Sequence[str],
    needs_review: Sequence[str],
    blocked: Sequence[str],
) -> dict[str, list[str]]:
    blocked_set = set(blocked)
    preferred_clean = [
        item
        for item in _dedupe_strings(preferred)
        if item not in blocked_set
    ]
    allowed_clean = [
        item
        for item in _dedupe_strings(allowed)
        if item not in blocked_set and item not in preferred_clean
    ]
    needs_review_clean = [
        item
        for item in _dedupe_strings(needs_review)
        if item not in blocked_set and item not in preferred_clean and item not in allowed_clean
    ]

    unassigned = [
        item
        for item in ALL_DEFINED_RISK_POLICY_STRATEGIES
        if item not in blocked_set
        and item not in preferred_clean
        and item not in allowed_clean
        and item not in needs_review_clean
    ]
    needs_review_clean.extend(unassigned)

    return {
        "preferred": preferred_clean,
        "allowed": allowed_clean,
        "needs_review": needs_review_clean,
        "blocked": _dedupe_strings(blocked),
    }


def _volatility_pricing_bias(
    *,
    iv_behavior: str | None,
    vol_premium_behavior: str | None,
) -> str:
    if iv_behavior == "extreme_iv":
        return "avoid_new_debit"

    if iv_behavior == "high_iv" or vol_premium_behavior == "rich_vol":
        return "credit_favored"

    if iv_behavior == "low_iv" or vol_premium_behavior == "cheap_vol":
        return "debit_favored"

    if iv_behavior == "normal_iv" or vol_premium_behavior == "neutral_vol":
        return "balanced"

    return "unknown"


def _liquidity_posture(liquidity_behavior: str | None) -> str:
    if liquidity_behavior in {"high_liquidity", "medium_liquidity"}:
        return "tradable"
    if liquidity_behavior == "low_liquidity":
        return "needs_review"
    if liquidity_behavior == "untradable_liquidity":
        return "blocked"
    return "unknown"


def _greek_risk_posture(greek_behavior: str | None) -> str:
    if greek_behavior == "normal_greek_risk":
        return "normal"
    if greek_behavior == "elevated_greek_risk":
        return "elevated_review"
    if greek_behavior == "high_greek_risk":
        return "high_review"
    return "unknown"


def _term_structure_bias(term_structure_behavior: str | None) -> str:
    if term_structure_behavior == "contango_term_structure":
        return "time_spread_supportive"
    if term_structure_behavior == "backwardated_term_structure":
        return "time_spread_review"
    if term_structure_behavior == "flat_term_structure":
        return "neutral"
    return "unknown"


def _skew_bias(skew_behavior: str | None) -> str:
    if skew_behavior == "downside_rich_skew":
        return "put_premium_rich"
    if skew_behavior == "upside_rich_skew":
        return "call_premium_rich"
    if skew_behavior == "balanced_skew":
        return "balanced"
    if skew_behavior == "distorted_skew":
        return "skew_review"
    return "unknown"


def _policy_status(
    *,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str],
    volatility_pricing_bias: str,
    liquidity_behavior: str | None,
    greek_behavior: str | None,
) -> str:
    if blocked_reasons:
        return "blocked"

    if liquidity_behavior == "untradable_liquidity":
        return "blocked"

    if warnings:
        return "needs_review"

    if volatility_pricing_bias == "unknown" or greek_behavior == "unknown_greek_risk":
        return "needs_review"

    return "ready"


def _has_unknown_behavior(option_behavior_result: Mapping[str, Any]) -> bool:
    return any(
        str(option_behavior_result.get(key, "")).startswith("unknown")
        for key in REQUIRED_OPTION_BEHAVIOR_KEYS
    )


def _fit_input_errors(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
    strategy: str | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(strategy_candidate, Mapping):
        errors.append("invalid strategy_candidate shape")

    if not strategy:
        errors.append("strategy is required")

    if not isinstance(option_behavior_options_policy, Mapping):
        errors.append("invalid option_behavior_options_policy shape")
    else:
        policy_status = _clean(option_behavior_options_policy.get("status"))
        if policy_status not in VALID_POLICY_STATUSES:
            errors.append("invalid option behavior options policy status")
        elif policy_status == "blocked":
            errors.extend(_strings(option_behavior_options_policy.get("blocked_reasons")))
            if not errors:
                errors.append("option behavior options policy is blocked")

    return errors


def _blocked_fit(
    *,
    strategy: str | None,
    blocked_reasons: Sequence[str],
    option_behavior_options_policy: Mapping[str, Any] | None = None,
    policy_status: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "option_behavior_option_strategy_fit",
        "status": "blocked",
        "is_ready": False,
        "strategy": strategy,
        "policy_status": policy_status or "blocked",
        "fit_score": 0.0,
        "score_adjustment": 0.0,
        "decision": "block",
        "volatility_pricing_bias": option_behavior_options_policy.get("volatility_pricing_bias")
        if isinstance(option_behavior_options_policy, Mapping)
        else None,
        "liquidity_posture": option_behavior_options_policy.get("liquidity_posture")
        if isinstance(option_behavior_options_policy, Mapping)
        else None,
        "greek_risk_posture": option_behavior_options_policy.get("greek_risk_posture")
        if isinstance(option_behavior_options_policy, Mapping)
        else None,
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
    }


def _policy_status_for_strategy(
    policy: Mapping[str, Any],
    strategy: str | None,
) -> str | None:
    if strategy is None:
        return None

    strategy_policy = policy.get("strategy_policy")
    if not isinstance(strategy_policy, Mapping):
        return None

    for status in ["preferred", "allowed", "needs_review", "blocked"]:
        if strategy in set(_strings(strategy_policy.get(status))):
            return status

    return None


def _application_input_errors(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(option_strategy_candidates, Mapping):
        errors.append("invalid option_strategy_candidates shape")
    else:
        source_status = _clean(option_strategy_candidates.get("status"))
        if source_status not in VALID_POLICY_STATUSES:
            errors.append("invalid option strategy candidates status")

    if not isinstance(option_behavior_options_policy, Mapping):
        errors.append("invalid option_behavior_options_policy shape")
    else:
        policy_status = _clean(option_behavior_options_policy.get("status"))
        if policy_status not in VALID_POLICY_STATUSES:
            errors.append("invalid option behavior options policy status")

    return errors


def _blocked_application(
    *,
    blocked_reasons: Sequence[str],
    symbol: str | None = None,
    market_regime: str | None = None,
    option_behavior_options_policy: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
    source_candidate_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "option_behavior_filtered_option_strategy_candidates",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "market_regime": market_regime,
        "volatility_pricing_bias": option_behavior_options_policy.get("volatility_pricing_bias")
        if isinstance(option_behavior_options_policy, Mapping)
        else None,
        "liquidity_posture": option_behavior_options_policy.get("liquidity_posture")
        if isinstance(option_behavior_options_policy, Mapping)
        else None,
        "greek_risk_posture": option_behavior_options_policy.get("greek_risk_posture")
        if isinstance(option_behavior_options_policy, Mapping)
        else None,
        "candidate_count": 0,
        "needs_review_count": 0,
        "blocked_count": 0,
        "source_candidate_count": 0,
        "candidates": [],
        "needs_review_candidates": [],
        "blocked_candidates": [],
        "warnings": _dedupe_strings(list(warnings or [])),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_candidate_summary": dict(source_candidate_summary or {}),
        "option_behavior_policy_summary": _policy_summary(option_behavior_options_policy),
        "excluded": EXCLUDED_ACTIONS,
    }


def _application_status(
    *,
    source_status: str | None,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    warnings: Sequence[str],
) -> str:
    if source_status == "blocked":
        return "blocked"

    if ready_count > 0:
        return "needs_review" if warnings else "ready"

    if needs_review_count > 0:
        return "needs_review"

    if blocked_count > 0:
        return "blocked"

    return "blocked"


def _enrich_candidate_with_fit(
    *,
    candidate: Mapping[str, Any],
    fit: Mapping[str, Any],
) -> dict[str, Any]:
    base_score = _float(candidate.get("option_behavior_adjusted_score"))
    if base_score == 0.0:
        base_score = _float(candidate.get("asset_behavior_adjusted_score"))
    if base_score == 0.0:
        base_score = _float(candidate.get("regime_adjusted_score"))
    if base_score == 0.0:
        base_score = _float(candidate.get("score"))

    score_adjustment = _float(fit.get("score_adjustment"))
    return {
        **dict(candidate),
        "option_behavior_fit": dict(fit),
        "option_behavior_policy_status": fit.get("policy_status"),
        "option_behavior_adjusted_score": round(base_score + score_adjustment, 4),
    }


def _strategy_from_candidate(candidate: Mapping[str, Any] | None) -> str | None:
    if not isinstance(candidate, Mapping):
        return None
    return _string_or_none(candidate.get("strategy"))


def _source_option_behavior_summary(option_behavior_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "iv_behavior": _string_or_none(option_behavior_result.get("iv_behavior")),
        "vol_premium_behavior": _string_or_none(
            option_behavior_result.get("vol_premium_behavior")
        ),
        "liquidity_behavior": _string_or_none(
            option_behavior_result.get("liquidity_behavior")
        ),
        "skew_behavior": _string_or_none(option_behavior_result.get("skew_behavior")),
        "term_structure_behavior": _string_or_none(
            option_behavior_result.get("term_structure_behavior")
        ),
        "greek_behavior": _string_or_none(option_behavior_result.get("greek_behavior")),
        "option_behavior_score": option_behavior_result.get("option_behavior_score"),
        "option_behavior_state": _string_or_none(
            option_behavior_result.get("option_behavior_state")
        ),
    }


def _source_candidate_summary(option_strategy_candidates: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": _string_or_none(option_strategy_candidates.get("artifact_type")),
        "status": _string_or_none(option_strategy_candidates.get("status")),
        "symbol": _string_or_none(option_strategy_candidates.get("symbol")),
        "candidate_count": int(option_strategy_candidates.get("candidate_count", 0) or 0),
        "needs_review_count": int(
            option_strategy_candidates.get("needs_review_count", 0) or 0
        ),
        "blocked_count": int(option_strategy_candidates.get("blocked_count", 0) or 0),
    }


def _policy_summary(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        return {}
    strategy_policy = policy.get("strategy_policy")
    return {
        "status": _string_or_none(policy.get("status")),
        "volatility_pricing_bias": _string_or_none(policy.get("volatility_pricing_bias")),
        "liquidity_posture": _string_or_none(policy.get("liquidity_posture")),
        "greek_risk_posture": _string_or_none(policy.get("greek_risk_posture")),
        "preferred_count": len(_strings(strategy_policy.get("preferred")))
        if isinstance(strategy_policy, Mapping)
        else 0,
        "allowed_count": len(_strings(strategy_policy.get("allowed")))
        if isinstance(strategy_policy, Mapping)
        else 0,
        "needs_review_count": len(_strings(strategy_policy.get("needs_review")))
        if isinstance(strategy_policy, Mapping)
        else 0,
        "blocked_count": len(_strings(strategy_policy.get("blocked")))
        if isinstance(strategy_policy, Mapping)
        else 0,
    }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return cleaned


def _string_or_none(value: Any) -> str | None:
    return _clean(value)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence):
        return []
    return [item for item in (_clean(item) for item in value) if item is not None]


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if cleaned is None or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _add_unique(values: Sequence[str], additions: Sequence[str]) -> list[str]:
    return _dedupe_strings([*values, *additions])


def _promote(
    preferred: Sequence[str],
    allowed: Sequence[str],
    promotions: Sequence[str],
) -> list[str]:
    return _dedupe_strings([*promotions, *preferred, *allowed])



