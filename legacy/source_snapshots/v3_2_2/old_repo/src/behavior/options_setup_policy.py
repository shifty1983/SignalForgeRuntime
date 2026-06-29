from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.options_strategy.catalog import UNDEFINED_RISK_STRATEGIES
from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_SOURCE_REFS_KEY,
    MATRIX_METADATA_STATE_KEY,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
)


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

BULLISH_STRATEGIES = [
    "bull_call_debit_spread",
    "put_credit_spread",
    "diagonal_spread",
]

BEARISH_STRATEGIES = [
    "bear_put_debit_spread",
    "call_credit_spread",
]

NEUTRAL_STRATEGIES = [
    "iron_condor",
    "calendar_spread",
    "iron_butterfly",
]

DEFENSIVE_STRATEGIES = [
    "protective_put",
    "collar",
    "covered_call",
]

ALL_DEFINED_RISK_POLICY_STRATEGIES = [
    "bull_call_debit_spread",
    "put_credit_spread",
    "bear_put_debit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
    "protective_put",
    "collar",
    "covered_call",
]

STRATEGY_FIT_SCORES = {
    "preferred": 3.0,
    "allowed": 2.0,
    "needs_review": 1.0,
    "blocked": 0.0,
    "not_found": 1.0,
}

STRATEGY_SCORE_ADJUSTMENTS = {
    "preferred": 1.0,
    "allowed": 0.5,
    "needs_review": -0.5,
    "blocked": 0.0,
    "not_found": -0.5,
}

STRATEGY_FIT_DECISIONS = {
    "preferred": "favor",
    "allowed": "allow",
    "needs_review": "manual_review",
    "blocked": "block",
    "not_found": "manual_review",
}

BULLISH_BEHAVIORS = {
    "uptrend",
    "controlled_uptrend",
    "bullish_momentum",
    "breakout_continuation",
    "support_holding",
    "bullish_mean_reversion",
    "range_support",
    "constructive",
}

BEARISH_BEHAVIORS = {
    "downtrend",
    "controlled_downtrend",
    "bearish_momentum",
    "breakdown_continuation",
    "resistance_holding",
    "bearish_mean_reversion",
    "range_resistance",
    "defensive",
}

NEUTRAL_BEHAVIORS = {
    "sideways",
    "range_bound",
    "low_trend_strength",
    "neutral_mean_reversion",
    "balanced_range",
    "volatility_compression",
    "pin_risk",
    "neutral",
}

HIGH_RISK_BEHAVIORS = {
    "deep_drawdown",
    "high_vol",
    "unstable",
    "gap_risk",
    "event_risk",
}


VALID_POLICY_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}


def build_asset_behavior_options_setup_policy(
    asset_behavior_result: Mapping[str, Any] | None,
    *,
    symbol: str | None = None,
    has_underlying_position: bool = False,
) -> dict[str, Any]:
    """
    Convert asset behavior into an options-aware setup policy.

    This policy is strategy-family guidance only. It does not generate option
    contracts, choose strikes/expirations, calculate EV, size trades, route
    orders, submit orders, model fills, or create automatic maintenance/defense
    actions.
    """

    if not isinstance(asset_behavior_result, Mapping):
        return _blocked_policy(
            symbol=symbol,
            blocked_reasons=["invalid asset_behavior_result shape"],
        )

    source_status = _clean(asset_behavior_result.get("status"))
    warnings = []
    blocked_reasons = []

    if source_status == "blocked":
        blocked_reasons.append("asset behavior result is blocked")

    if source_status == "needs_review":
        warnings.append("asset behavior result needs review")

    source_symbol = symbol or _string_or_none(asset_behavior_result.get("symbol"))
    normalized_behavior = _normalized_asset_behavior(asset_behavior_result)
    directional_bias = _directional_bias(asset_behavior_result, normalized_behavior)
    risk_posture = _risk_posture(asset_behavior_result, normalized_behavior)
    setup_quality_score = _setup_quality_score(asset_behavior_result, directional_bias, risk_posture)
    setup_family_bias = _setup_family_bias(directional_bias, risk_posture)
    strategy_policy = _strategy_policy(
        directional_bias=directional_bias,
        risk_posture=risk_posture,
        has_underlying_position=has_underlying_position,
    )

    if normalized_behavior is None:
        blocked_reasons.append("missing asset behavior label or component behavior inputs")

    status = _policy_status(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
        risk_posture=risk_posture,
        setup_quality_score=setup_quality_score,
    )

    result = {
        "artifact_type": "asset_behavior_options_setup_policy",
        "status": status,
        "is_ready": status == "ready",
        "symbol": source_symbol,
        "asset_behavior_label": normalized_behavior,
        "normalized_asset_behavior": normalized_behavior,
        "directional_bias": directional_bias,
        "risk_posture": risk_posture,
        "setup_quality_score": setup_quality_score,
        "setup_family_bias": setup_family_bias,
        "strategy_policy": strategy_policy,
        "has_underlying_position": bool(has_underlying_position),
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_asset_behavior_summary": _source_asset_behavior_summary(asset_behavior_result),
        "excluded": EXCLUDED_ACTIONS,
    }
    result.update(
        _asset_behavior_matrix_dimension_payload(
            symbol=source_symbol,
            asset_behavior_state=normalized_behavior,
            source_refs={
                "symbol": "asset_behavior_result.symbol",
                "asset_behavior_state": "asset_behavior_result.asset_behavior_or_derived_behavior",
            },
        )
    )
    return result


def evaluate_asset_behavior_option_strategy_fit(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Evaluate one concrete option strategy candidate against the asset-behavior
    options setup policy.
    """

    strategy = _strategy_from_candidate(strategy_candidate)
    input_errors = _fit_input_errors(
        strategy_candidate=strategy_candidate,
        asset_behavior_options_policy=asset_behavior_options_policy,
        strategy=strategy,
    )
    if input_errors:
        return _blocked_fit(strategy=strategy, blocked_reasons=input_errors)

    assert isinstance(asset_behavior_options_policy, Mapping)
    if strategy in UNDEFINED_RISK_STRATEGIES:
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=["undefined risk strategies are hard-blocked"],
            asset_behavior_options_policy=asset_behavior_options_policy,
            policy_status="blocked",
        )

    policy_status = _policy_status_for_strategy(asset_behavior_options_policy, strategy)
    if policy_status is None:
        policy_status = "not_found"

    if policy_status == "blocked":
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=["strategy blocked by asset behavior options policy"],
            asset_behavior_options_policy=asset_behavior_options_policy,
            policy_status=policy_status,
        )

    warnings = []
    if policy_status in {"needs_review", "not_found"}:
        warnings.append("strategy requires manual review under current asset behavior policy")

    status = "ready" if policy_status in {"preferred", "allowed"} else "needs_review"
    stamped = _stamp_strategy_fit_matrix_metadata(
        strategy_candidate=strategy_candidate,
        asset_behavior_options_policy=asset_behavior_options_policy,
        strategy=strategy,
    )
    return {
        "artifact_type": "asset_behavior_option_strategy_fit",
        "status": status,
        "is_ready": status == "ready",
        "strategy": strategy,
        "asset_behavior_label": asset_behavior_options_policy.get("asset_behavior_label"),
        "directional_bias": asset_behavior_options_policy.get("directional_bias"),
        "risk_posture": asset_behavior_options_policy.get("risk_posture"),
        "policy_status": policy_status,
        "fit_score": STRATEGY_FIT_SCORES[policy_status],
        "score_adjustment": STRATEGY_SCORE_ADJUSTMENTS[policy_status],
        "decision": STRATEGY_FIT_DECISIONS[policy_status],
        MATRIX_METADATA_KEY: stamped.get(MATRIX_METADATA_KEY),
        MATRIX_METADATA_STATE_KEY: stamped.get(MATRIX_METADATA_STATE_KEY),
        MATRIX_METADATA_MISSING_FIELDS_KEY: stamped.get(MATRIX_METADATA_MISSING_FIELDS_KEY),
        MATRIX_METADATA_SOURCE_REFS_KEY: stamped.get(MATRIX_METADATA_SOURCE_REFS_KEY),
        MATRIX_CELL_KEY_KEY: stamped.get(MATRIX_CELL_KEY_KEY),
        "ready_to_build_exact_matrix_edge_summary": stamped.get(MATRIX_METADATA_STATE_KEY) == "ready",
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
    }


def apply_asset_behavior_policy_to_option_candidates(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Apply the asset-behavior options setup policy to generated option strategy
    candidates.
    """

    input_errors = _application_input_errors(
        option_strategy_candidates=option_strategy_candidates,
        asset_behavior_options_policy=asset_behavior_options_policy,
    )
    if input_errors:
        return _blocked_application(blocked_reasons=input_errors)

    assert isinstance(option_strategy_candidates, Mapping)
    assert isinstance(asset_behavior_options_policy, Mapping)

    source_status = _clean(option_strategy_candidates.get("status"))
    warnings = list(_strings(option_strategy_candidates.get("warnings")))
    blocked_reasons = list(_strings(option_strategy_candidates.get("blocked_reasons")))

    if source_status == "blocked":
        if not blocked_reasons:
            blocked_reasons.append("source option strategy candidates are blocked")
        return _blocked_application(
            symbol=_string_or_none(option_strategy_candidates.get("symbol")),
            warnings=warnings,
            blocked_reasons=blocked_reasons,
            asset_behavior_options_policy=asset_behavior_options_policy,
            source_candidate_summary=_source_candidate_summary(option_strategy_candidates),
        )

    ready_candidates: list[dict[str, Any]] = []
    needs_review_candidates: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []

    for candidate in _mapping_list(option_strategy_candidates.get("candidates")):
        fit = evaluate_asset_behavior_option_strategy_fit(
            strategy_candidate=candidate,
            asset_behavior_options_policy=asset_behavior_options_policy,
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
        key=lambda candidate: (-_float(candidate.get("asset_behavior_adjusted_score")), candidate.get("strategy", "")),
    )
    needs_review_candidates = sorted(
        needs_review_candidates,
        key=lambda candidate: (-_float(candidate.get("asset_behavior_adjusted_score")), candidate.get("strategy", "")),
    )
    blocked_candidates = sorted(blocked_candidates, key=lambda candidate: candidate.get("strategy", ""))

    status = _application_status(
        source_status=source_status,
        ready_count=len(ready_candidates),
        needs_review_count=len(needs_review_candidates),
        blocked_count=len(blocked_candidates),
        warnings=warnings,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("no option strategy candidates remain after asset behavior policy")

    all_candidates = [*ready_candidates, *needs_review_candidates, *blocked_candidates]
    matrix_summary = matrix_metadata_coverage(all_candidates)

    return {
        "artifact_type": "asset_behavior_filtered_option_strategy_candidates",
        "status": status,
        "is_ready": status == "ready",
        "symbol": _string_or_none(option_strategy_candidates.get("symbol")),
        "asset_behavior_label": asset_behavior_options_policy.get("asset_behavior_label"),
        "directional_bias": asset_behavior_options_policy.get("directional_bias"),
        "risk_posture": asset_behavior_options_policy.get("risk_posture"),
        "candidate_count": len(ready_candidates),
        "needs_review_count": len(needs_review_candidates),
        "blocked_count": len(blocked_candidates),
        "source_candidate_count": int(option_strategy_candidates.get("candidate_count", 0) or 0),
        "candidates": ready_candidates,
        "needs_review_candidates": needs_review_candidates,
        "blocked_candidates": blocked_candidates,
        "matrix_metadata_candidate_summary": matrix_summary,
        "exact_matrix_cell_ready_record_count": matrix_summary["exact_matrix_cell_ready_record_count"],
        "matrix_metadata_needs_review_record_count": matrix_summary["needs_review_record_count"],
        "ready_to_build_exact_matrix_edge_summary": matrix_summary["ready_to_build_exact_matrix_edge_summary"],
        "recommended_next_step": (
            "patch_historical_replay_export_candidates_with_matrix_metadata"
            if matrix_summary["ready_to_build_exact_matrix_edge_summary"]
            else "continue_matrix_metadata_source_dimension_stamping"
        ),
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_candidate_summary": _source_candidate_summary(option_strategy_candidates),
        "excluded": EXCLUDED_ACTIONS,
    }



def _asset_behavior_matrix_dimension_payload(
    *,
    symbol: str | None,
    asset_behavior_state: str | None,
    source_refs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "symbol": symbol,
        "asset_behavior_state": asset_behavior_state,
    }
    missing_fields = [
        field
        for field, value in metadata.items()
        if value is None or value == ""
    ]
    return {
        "matrix_dimension_provider": "asset_behavior_options_setup_policy",
        "matrix_dimension_fields": ["symbol", "asset_behavior_state"],
        "matrix_dimension_metadata": metadata,
        "matrix_dimension_state": "ready" if not missing_fields else "needs_review",
        "matrix_dimension_missing_fields": missing_fields,
        "matrix_dimension_source_refs": dict(source_refs or {}),
        "ready_to_patch_historical_replay_exports": True,
        "ready_to_build_exact_matrix_edge_summary": False,
        "recommended_next_step": "stamp_asset_behavior_options_policy_matrix_metadata",
    }


def _stamp_strategy_fit_matrix_metadata(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    strategy: str | None,
) -> dict[str, Any]:
    candidate = dict(strategy_candidate or {})
    policy = asset_behavior_options_policy if isinstance(asset_behavior_options_policy, Mapping) else {}
    metadata = {
        "symbol": _first_present_string(
            candidate,
            ["symbol", "ticker", "underlying", "underlying_symbol"],
        )
        or _string_or_none(policy.get("symbol")),
        "asset_behavior_state": _string_or_none(policy.get("asset_behavior_label"))
        or _string_or_none(policy.get("normalized_asset_behavior")),
        "strategy_id": _first_present_string(
            candidate,
            ["strategy_id", "strategy", "setup_id", "scenario_id"],
        )
        or strategy,
        "strategy_family": _first_present_string(
            candidate,
            ["strategy_family", "family", "strategy_type", "variant_id"],
        )
        or strategy,
        "regime_state": _first_present_string(candidate, ["regime_state", "regime", "market_regime"]),
        "option_behavior_state": _first_present_string(
            candidate,
            ["option_behavior_state", "option_behavior", "options_behavior_state"],
        ),
        "horizon_days": candidate.get("horizon_days")
        or candidate.get("horizon")
        or candidate.get("window_days")
        or candidate.get("target_horizon_days"),
        "asset_class": _first_present_string(candidate, ["asset_class", "security_type", "instrument_type"]),
        "strategy_direction": _first_present_string(
            candidate,
            ["strategy_direction", "direction", "bias"],
        )
        or _string_or_none(policy.get("directional_bias")),
        "risk_structure": _first_present_string(
            candidate,
            ["risk_structure", "risk_profile", "defined_risk_state"],
        ),
    }
    return stamp_matrix_metadata(
        candidate,
        metadata,
        source_refs={
            "symbol": "candidate_or_asset_behavior_options_policy",
            "asset_behavior_state": "asset_behavior_options_policy",
            "strategy_id": "option_strategy_candidate",
            "strategy_family": "option_strategy_candidate",
            "regime_state": "option_strategy_candidate",
            "option_behavior_state": "option_strategy_candidate",
            "horizon_days": "option_strategy_candidate",
        },
        preserve_existing=True,
    )

def _blocked_policy(
    *,
    symbol: str | None,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str] | None = None,
) -> dict[str, Any]:
    result = {
        "artifact_type": "asset_behavior_options_setup_policy",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "asset_behavior_label": None,
        "normalized_asset_behavior": None,
        "directional_bias": "unknown",
        "risk_posture": "blocked",
        "setup_quality_score": 0.0,
        "setup_family_bias": {
            "preferred": [],
            "allowed": [],
            "needs_review": [],
            "blocked": ["momentum", "trend_following", "mean_reversion", "income", "portfolio_defense"],
        },
        "strategy_policy": {
            "preferred": [],
            "allowed": [],
            "needs_review": [],
            "blocked": ALL_DEFINED_RISK_POLICY_STRATEGIES + sorted(UNDEFINED_RISK_STRATEGIES),
        },
        "has_underlying_position": False,
        "warnings": list(warnings or []),
        "blocked_reasons": list(blocked_reasons),
        "source_asset_behavior_summary": {},
        "excluded": EXCLUDED_ACTIONS,
    }
    result.update(
        _asset_behavior_matrix_dimension_payload(
            symbol=symbol,
            asset_behavior_state=None,
            source_refs={"symbol": "input.symbol"},
        )
    )
    return result


def _normalized_asset_behavior(asset_behavior_result: Mapping[str, Any]) -> str | None:
    explicit = _first_present_string(
        asset_behavior_result,
        [
            "asset_behavior",
            "behavior",
            "behavior_classification",
            "classification",
            "asset_behavior_state",
            "behavior_state",
        ],
    )
    if explicit:
        return explicit

    trend = _clean(asset_behavior_result.get("trend_behavior"))
    return_behavior = _clean(asset_behavior_result.get("return_behavior"))
    volatility = _clean(asset_behavior_result.get("volatility_behavior"))
    drawdown = _clean(asset_behavior_result.get("drawdown_behavior"))

    if trend == "uptrend" and return_behavior in {"positive", None} and volatility != "high_vol":
        return "controlled_uptrend"
    if trend == "uptrend":
        return "uptrend"
    if trend == "downtrend" and return_behavior in {"negative", None}:
        return "controlled_downtrend"
    if trend == "downtrend":
        return "downtrend"
    if trend == "sideways" and volatility == "low_vol":
        return "range_bound"
    if trend == "sideways":
        return "sideways"
    if drawdown == "deep_drawdown":
        return "deep_drawdown"
    return None


def _directional_bias(
    asset_behavior_result: Mapping[str, Any],
    normalized_behavior: str | None,
) -> str:
    behavior = _clean(normalized_behavior)
    trend = _clean(asset_behavior_result.get("trend_behavior"))
    return_behavior = _clean(asset_behavior_result.get("return_behavior"))
    behavior_state = _clean(asset_behavior_result.get("behavior_state"))

    if behavior in BULLISH_BEHAVIORS or trend == "uptrend" or behavior_state == "constructive":
        return "bullish"
    if behavior in BEARISH_BEHAVIORS or trend == "downtrend" or behavior_state == "defensive":
        return "bearish"
    if behavior in NEUTRAL_BEHAVIORS or trend == "sideways" or return_behavior == "neutral":
        return "neutral"
    return "unknown"


def _risk_posture(
    asset_behavior_result: Mapping[str, Any],
    normalized_behavior: str | None,
) -> str:
    behavior = _clean(normalized_behavior)
    volatility = _clean(asset_behavior_result.get("volatility_behavior"))
    drawdown = _clean(asset_behavior_result.get("drawdown_behavior"))
    score = _maybe_float(
        asset_behavior_result.get("asset_behavior_score"),
        asset_behavior_result.get("behavior_score"),
    )

    if behavior in HIGH_RISK_BEHAVIORS or volatility == "high_vol" or drawdown == "deep_drawdown":
        return "defensive"
    if drawdown == "moderate_drawdown" or (score is not None and score < 45.0):
        return "cautious"
    if volatility == "low_vol" and score is not None and score >= 70.0:
        return "constructive"
    return "normal"


def _setup_quality_score(
    asset_behavior_result: Mapping[str, Any],
    directional_bias: str,
    risk_posture: str,
) -> float:
    source_score = _maybe_float(
        asset_behavior_result.get("asset_behavior_score"),
        asset_behavior_result.get("behavior_score"),
    )
    if source_score is not None:
        base_score = source_score
    elif directional_bias in {"bullish", "bearish", "neutral"}:
        base_score = 65.0
    else:
        base_score = 40.0

    if risk_posture == "defensive":
        base_score -= 15.0
    elif risk_posture == "cautious":
        base_score -= 7.5
    elif risk_posture == "constructive":
        base_score += 5.0

    return round(max(0.0, min(100.0, float(base_score))), 2)


def _setup_family_bias(directional_bias: str, risk_posture: str) -> dict[str, list[str]]:
    if risk_posture == "defensive":
        return {
            "preferred": ["portfolio_defense"],
            "allowed": ["trend_following"],
            "needs_review": ["mean_reversion", "income"],
            "blocked": ["momentum"],
        }

    if directional_bias == "bullish":
        return {
            "preferred": ["momentum", "trend_following"],
            "allowed": ["income", "mean_reversion"],
            "needs_review": ["portfolio_defense"],
            "blocked": [],
        }

    if directional_bias == "bearish":
        return {
            "preferred": ["momentum", "trend_following"],
            "allowed": ["portfolio_defense", "income", "mean_reversion"],
            "needs_review": [],
            "blocked": [],
        }

    if directional_bias == "neutral":
        return {
            "preferred": ["mean_reversion", "income"],
            "allowed": ["portfolio_defense"],
            "needs_review": ["momentum", "trend_following"],
            "blocked": [],
        }

    return {
        "preferred": [],
        "allowed": [],
        "needs_review": ["momentum", "trend_following", "mean_reversion", "income", "portfolio_defense"],
        "blocked": [],
    }


def _strategy_policy(
    *,
    directional_bias: str,
    risk_posture: str,
    has_underlying_position: bool,
) -> dict[str, list[str]]:
    if risk_posture == "defensive":
        preferred = ["protective_put", "collar"] if has_underlying_position else ["bear_put_debit_spread"]
        allowed = ["call_credit_spread"]
        needs_review = ["covered_call", "put_credit_spread", "iron_condor", "calendar_spread"]
        blocked = ["bull_call_debit_spread", "iron_butterfly", "diagonal_spread"]
        return _with_undefined_blocked(preferred, allowed, needs_review, blocked)

    if directional_bias == "bullish":
        preferred = ["bull_call_debit_spread", "put_credit_spread"]
        allowed = ["diagonal_spread", "covered_call"] if has_underlying_position else ["diagonal_spread"]
        needs_review = ["calendar_spread", "collar"] if has_underlying_position else ["calendar_spread"]
        blocked = ["bear_put_debit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put"]
        return _with_undefined_blocked(preferred, allowed, needs_review, blocked)

    if directional_bias == "bearish":
        preferred = ["bear_put_debit_spread", "call_credit_spread"]
        allowed = ["protective_put", "collar"] if has_underlying_position else []
        needs_review = ["calendar_spread", "iron_condor"]
        blocked = ["bull_call_debit_spread", "put_credit_spread", "iron_butterfly", "diagonal_spread", "covered_call"]
        return _with_undefined_blocked(preferred, allowed, needs_review, blocked)

    if directional_bias == "neutral":
        preferred = ["iron_condor", "calendar_spread"]
        allowed = ["covered_call", "collar"] if has_underlying_position else []
        needs_review = ["iron_butterfly", "put_credit_spread", "call_credit_spread"]
        blocked = ["bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread", "protective_put"]
        return _with_undefined_blocked(preferred, allowed, needs_review, blocked)

    return _with_undefined_blocked(
        preferred=[],
        allowed=[],
        needs_review=ALL_DEFINED_RISK_POLICY_STRATEGIES,
        blocked=[],
    )


def _with_undefined_blocked(
    preferred: Sequence[str],
    allowed: Sequence[str],
    needs_review: Sequence[str],
    blocked: Sequence[str],
) -> dict[str, list[str]]:
    return {
        "preferred": _dedupe_strings(preferred),
        "allowed": _dedupe_strings(allowed),
        "needs_review": _dedupe_strings(needs_review),
        "blocked": _dedupe_strings([*blocked, *sorted(UNDEFINED_RISK_STRATEGIES)]),
    }


def _policy_status(
    *,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str],
    risk_posture: str,
    setup_quality_score: float,
) -> str:
    if blocked_reasons:
        return "blocked"
    if risk_posture in {"defensive", "cautious"} or setup_quality_score < 55.0 or warnings:
        return "needs_review"
    return "ready"


def _policy_status_for_strategy(
    asset_behavior_options_policy: Mapping[str, Any],
    strategy: str | None,
) -> str | None:
    if strategy is None:
        return None
    policy = asset_behavior_options_policy.get("strategy_policy")
    if not isinstance(policy, Mapping):
        return None

    for status in ["preferred", "allowed", "needs_review", "blocked"]:
        if strategy in set(_strings(policy.get(status))):
            return status
    return None


def _blocked_fit(
    *,
    strategy: str | None,
    blocked_reasons: Sequence[str],
    asset_behavior_options_policy: Mapping[str, Any] | None = None,
    policy_status: str = "blocked",
) -> dict[str, Any]:
    stamped = (
        _stamp_strategy_fit_matrix_metadata(
            strategy_candidate={"strategy": strategy} if strategy else {},
            asset_behavior_options_policy=asset_behavior_options_policy,
            strategy=strategy,
        )
        if isinstance(asset_behavior_options_policy, Mapping)
        else {}
    )
    return {
        "artifact_type": "asset_behavior_option_strategy_fit",
        "status": "blocked",
        "is_ready": False,
        "strategy": strategy,
        "asset_behavior_label": asset_behavior_options_policy.get("asset_behavior_label") if isinstance(asset_behavior_options_policy, Mapping) else None,
        "directional_bias": asset_behavior_options_policy.get("directional_bias") if isinstance(asset_behavior_options_policy, Mapping) else None,
        "risk_posture": asset_behavior_options_policy.get("risk_posture") if isinstance(asset_behavior_options_policy, Mapping) else None,
        "policy_status": policy_status,
        "fit_score": 0.0,
        "score_adjustment": 0.0,
        "decision": "block",
        MATRIX_METADATA_KEY: stamped.get(MATRIX_METADATA_KEY),
        MATRIX_METADATA_STATE_KEY: stamped.get(MATRIX_METADATA_STATE_KEY),
        MATRIX_METADATA_MISSING_FIELDS_KEY: stamped.get(MATRIX_METADATA_MISSING_FIELDS_KEY),
        MATRIX_METADATA_SOURCE_REFS_KEY: stamped.get(MATRIX_METADATA_SOURCE_REFS_KEY),
        MATRIX_CELL_KEY_KEY: stamped.get(MATRIX_CELL_KEY_KEY),
        "ready_to_build_exact_matrix_edge_summary": False,
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
    }


def _blocked_application(
    *,
    blocked_reasons: Sequence[str],
    symbol: str | None = None,
    warnings: Sequence[str] | None = None,
    asset_behavior_options_policy: Mapping[str, Any] | None = None,
    source_candidate_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    matrix_summary = matrix_metadata_coverage([])
    return {
        "artifact_type": "asset_behavior_filtered_option_strategy_candidates",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "asset_behavior_label": asset_behavior_options_policy.get("asset_behavior_label") if isinstance(asset_behavior_options_policy, Mapping) else None,
        "directional_bias": asset_behavior_options_policy.get("directional_bias") if isinstance(asset_behavior_options_policy, Mapping) else None,
        "risk_posture": asset_behavior_options_policy.get("risk_posture") if isinstance(asset_behavior_options_policy, Mapping) else None,
        "candidate_count": 0,
        "needs_review_count": 0,
        "blocked_count": 0,
        "source_candidate_count": 0,
        "candidates": [],
        "needs_review_candidates": [],
        "blocked_candidates": [],
        "matrix_metadata_candidate_summary": matrix_summary,
        "exact_matrix_cell_ready_record_count": 0,
        "matrix_metadata_needs_review_record_count": 0,
        "ready_to_build_exact_matrix_edge_summary": False,
        "recommended_next_step": "resolve_asset_behavior_options_policy_blockers",
        "warnings": list(warnings or []),
        "blocked_reasons": list(blocked_reasons),
        "source_candidate_summary": dict(source_candidate_summary or {}),
        "excluded": EXCLUDED_ACTIONS,
    }


def _fit_input_errors(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    strategy: str | None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(strategy_candidate, Mapping):
        errors.append("invalid strategy_candidate shape")
    if strategy is None:
        errors.append("missing option strategy")
    if not isinstance(asset_behavior_options_policy, Mapping):
        errors.append("invalid asset_behavior_options_policy shape")
    elif _clean(asset_behavior_options_policy.get("status")) not in VALID_POLICY_STATUSES:
        errors.append("invalid asset behavior options policy status")
    elif _clean(asset_behavior_options_policy.get("status")) == "blocked":
        errors.append("asset behavior options policy is blocked")
    return errors


def _application_input_errors(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(option_strategy_candidates, Mapping):
        errors.append("invalid option_strategy_candidates shape")
    if not isinstance(asset_behavior_options_policy, Mapping):
        errors.append("invalid asset_behavior_options_policy shape")
    elif _clean(asset_behavior_options_policy.get("status")) not in VALID_POLICY_STATUSES:
        errors.append("invalid asset behavior options policy status")
    elif _clean(asset_behavior_options_policy.get("status")) == "blocked":
        errors.append("asset behavior options policy is blocked")
    return errors


def _enrich_candidate_with_fit(
    *,
    candidate: Mapping[str, Any],
    fit: Mapping[str, Any],
) -> dict[str, Any]:
    base_score = _candidate_score(candidate)
    adjustment = _float(fit.get("score_adjustment"))
    stamped = stamp_matrix_metadata(
        candidate,
        fit.get(MATRIX_METADATA_KEY) if isinstance(fit.get(MATRIX_METADATA_KEY), Mapping) else {},
        source_refs=fit.get(MATRIX_METADATA_SOURCE_REFS_KEY)
        if isinstance(fit.get(MATRIX_METADATA_SOURCE_REFS_KEY), Mapping)
        else {},
        preserve_existing=True,
    )
    return {
        **stamped,
        "asset_behavior_policy_status": fit.get("policy_status"),
        "asset_behavior_fit_status": fit.get("status"),
        "asset_behavior_fit_score": fit.get("fit_score"),
        "asset_behavior_adjusted_score": round(base_score + adjustment, 4),
        "asset_behavior_fit_decision": fit.get("decision"),
        "asset_behavior_fit_warnings": list(_strings(fit.get("warnings"))),
        "asset_behavior_fit_blocked_reasons": list(_strings(fit.get("blocked_reasons"))),
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
    if ready_count > 0 and not warnings:
        return "ready"
    if ready_count > 0 or needs_review_count > 0:
        return "needs_review"
    if blocked_count > 0:
        return "blocked"
    return "blocked"


def _candidate_score(candidate: Mapping[str, Any]) -> float:
    for key in [
        "asset_behavior_adjusted_score",
        "regime_adjusted_score",
        "score",
        "match_score",
        "opportunity_score",
        "expected_value",
    ]:
        value = candidate.get(key)
        if value is not None:
            return _float(value)
    return 0.0


def _strategy_from_candidate(strategy_candidate: Mapping[str, Any] | None) -> str | None:
    if not isinstance(strategy_candidate, Mapping):
        return None
    return _string_or_none(strategy_candidate.get("strategy"))


def _source_asset_behavior_summary(asset_behavior_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": _string_or_none(asset_behavior_result.get("status")),
        "symbol": _string_or_none(asset_behavior_result.get("symbol")),
        "asset_behavior": _first_present_string(
            asset_behavior_result,
            [
                "asset_behavior",
                "behavior",
                "behavior_classification",
                "classification",
                "asset_behavior_state",
                "behavior_state",
            ],
        ),
        "trend_behavior": _string_or_none(asset_behavior_result.get("trend_behavior")),
        "volatility_behavior": _string_or_none(asset_behavior_result.get("volatility_behavior")),
        "return_behavior": _string_or_none(asset_behavior_result.get("return_behavior")),
        "drawdown_behavior": _string_or_none(asset_behavior_result.get("drawdown_behavior")),
        "behavior_score": asset_behavior_result.get("behavior_score"),
        "asset_behavior_score": asset_behavior_result.get("asset_behavior_score"),
    }


def _source_candidate_summary(option_strategy_candidates: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": option_strategy_candidates.get("artifact_type"),
        "status": option_strategy_candidates.get("status"),
        "symbol": option_strategy_candidates.get("symbol"),
        "candidate_count": option_strategy_candidates.get("candidate_count"),
        "needs_review_count": option_strategy_candidates.get("needs_review_count"),
        "blocked_count": option_strategy_candidates.get("blocked_count"),
        "matrix_metadata_candidate_summary": option_strategy_candidates.get("matrix_metadata_candidate_summary"),
        "ready_to_build_exact_matrix_edge_summary": option_strategy_candidates.get(
            "ready_to_build_exact_matrix_edge_summary"
        ),
    }


def _first_present_string(source: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = _string_or_none(source.get(key))
        if value:
            return value
    return None


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = []
        for item in value:
            cleaned = _string_or_none(item)
            if cleaned:
                values.append(cleaned)
        return values
    cleaned = _string_or_none(value)
    return [cleaned] if cleaned else []


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = _string_or_none(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean(value: Any) -> str | None:
    cleaned = _string_or_none(value)
    return cleaned.lower() if cleaned else None


def _maybe_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

