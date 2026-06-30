from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.engines.behavior.options_setup_policy import evaluate_asset_behavior_option_strategy_fit
from src.option_behavior.options_strategy_policy import (
    evaluate_option_behavior_option_strategy_fit,
)
from src.signalforge.engines.options_strategy.catalog import UNDEFINED_RISK_STRATEGIES
from src.signalforge.engines.regime.options_strategy_fit import evaluate_regime_option_strategy_fit


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

VALID_CANDIDATE_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}

REQUIRED_POLICY_ARTIFACT_TYPES = {
    "regime_options_policy": "regime_options_policy",
    "asset_behavior_options_setup_policy": "asset_behavior_options_setup_policy",
    "option_behavior_options_strategy_policy": "option_behavior_options_strategy_policy",
}


def evaluate_full_options_view_strategy_fit(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    regime_options_policy: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Evaluate one option strategy candidate against the full options view.

    Full options view means the candidate must fit all three policy layers:
    - market regime policy
    - asset behavior setup policy
    - option behavior strategy policy

    This module only scores and classifies strategy-family candidates. It does
    not select contracts, strikes, expirations, sizes, orders, fills, slippage,
    maintenance actions, or defense actions.
    """

    strategy = _strategy_from_candidate(strategy_candidate)
    input_errors = _fit_input_errors(
        strategy_candidate=strategy_candidate,
        strategy=strategy,
        regime_options_policy=regime_options_policy,
        asset_behavior_options_policy=asset_behavior_options_policy,
        option_behavior_options_policy=option_behavior_options_policy,
    )
    if input_errors:
        return _blocked_fit(strategy=strategy, blocked_reasons=input_errors)

    assert isinstance(strategy_candidate, Mapping)
    assert isinstance(regime_options_policy, Mapping)
    assert isinstance(asset_behavior_options_policy, Mapping)
    assert isinstance(option_behavior_options_policy, Mapping)

    if strategy in UNDEFINED_RISK_STRATEGIES:
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=["undefined risk strategies are hard-blocked"],
        )

    regime_fit = evaluate_regime_option_strategy_fit(
        strategy_candidate=strategy_candidate,
        regime_options_policy=regime_options_policy,
    )
    asset_behavior_fit = evaluate_asset_behavior_option_strategy_fit(
        strategy_candidate=strategy_candidate,
        asset_behavior_options_policy=asset_behavior_options_policy,
    )
    option_behavior_fit = evaluate_option_behavior_option_strategy_fit(
        strategy_candidate=strategy_candidate,
        option_behavior_options_policy=option_behavior_options_policy,
    )

    fit_records = [regime_fit, asset_behavior_fit, option_behavior_fit]
    statuses = [_clean(fit.get("status")) for fit in fit_records]
    policy_statuses = [_clean(fit.get("policy_status")) for fit in fit_records]
    warnings = _dedupe_strings(
        warning
        for fit in fit_records
        for warning in _strings(fit.get("warnings"))
    )
    blocked_reasons = _dedupe_strings(
        reason
        for fit in fit_records
        for reason in _strings(fit.get("blocked_reasons"))
    )

    if any(status == "blocked" for status in statuses):
        if not blocked_reasons:
            blocked_reasons.append("strategy blocked by one or more options policy layers")
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=blocked_reasons,
            warnings=warnings,
            regime_fit=regime_fit,
            asset_behavior_fit=asset_behavior_fit,
            option_behavior_fit=option_behavior_fit,
        )

    status = "needs_review" if any(status == "needs_review" for status in statuses) else "ready"
    decision = _combined_decision(policy_statuses=policy_statuses, status=status)
    base_score = _float(strategy_candidate.get("score"))
    total_adjustment = round(
        sum(_float(fit.get("score_adjustment")) for fit in fit_records),
        4,
    )
    full_score = round(base_score + total_adjustment, 4)

    return {
        "artifact_type": "full_options_view_strategy_fit",
        "status": status,
        "is_ready": status == "ready",
        "strategy": strategy,
        "decision": decision,
        "base_score": base_score,
        "total_score_adjustment": total_adjustment,
        "full_options_view_score": full_score,
        "regime_policy_status": regime_fit.get("policy_status"),
        "asset_behavior_policy_status": asset_behavior_fit.get("policy_status"),
        "option_behavior_policy_status": option_behavior_fit.get("policy_status"),
        "regime_fit": _fit_summary(regime_fit),
        "asset_behavior_fit": _fit_summary(asset_behavior_fit),
        "option_behavior_fit": _fit_summary(option_behavior_fit),
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
    }


def apply_full_options_view_to_option_candidates(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    regime_options_policy: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Apply the full options view to generated defined-risk strategy candidates.

    Output groups:
    - candidates: candidates that fit regime, asset behavior, and option behavior
    - needs_review_candidates: candidates that remain possible but need review
    - blocked_candidates: candidates rejected by at least one policy layer
    """

    input_errors = _application_input_errors(
        option_strategy_candidates=option_strategy_candidates,
        regime_options_policy=regime_options_policy,
        asset_behavior_options_policy=asset_behavior_options_policy,
        option_behavior_options_policy=option_behavior_options_policy,
    )
    if input_errors:
        return _blocked_application(blocked_reasons=input_errors)

    assert isinstance(option_strategy_candidates, Mapping)
    assert isinstance(regime_options_policy, Mapping)
    assert isinstance(asset_behavior_options_policy, Mapping)
    assert isinstance(option_behavior_options_policy, Mapping)

    source_status = _clean(option_strategy_candidates.get("status"))
    warnings: list[str] = list(_strings(option_strategy_candidates.get("warnings")))
    blocked_reasons: list[str] = list(_strings(option_strategy_candidates.get("blocked_reasons")))

    if source_status == "blocked":
        if not blocked_reasons:
            blocked_reasons.append("source option strategy candidates are blocked")
        return _blocked_application(
            symbol=_string_or_none(option_strategy_candidates.get("symbol")),
            market_regime=_string_or_none(option_strategy_candidates.get("market_regime")),
            warnings=warnings,
            blocked_reasons=blocked_reasons,
            source_candidate_summary=_source_candidate_summary(option_strategy_candidates),
            policy_summaries=_policy_summaries(
                regime_options_policy=regime_options_policy,
                asset_behavior_options_policy=asset_behavior_options_policy,
                option_behavior_options_policy=option_behavior_options_policy,
            ),
        )

    ready_candidates: list[dict[str, Any]] = []
    needs_review_candidates: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []

    for candidate in _mapping_list(option_strategy_candidates.get("candidates")):
        fit = evaluate_full_options_view_strategy_fit(
            strategy_candidate=candidate,
            regime_options_policy=regime_options_policy,
            asset_behavior_options_policy=asset_behavior_options_policy,
            option_behavior_options_policy=option_behavior_options_policy,
        )
        enriched = _enrich_candidate_with_full_options_view(candidate=candidate, fit=fit)
        fit_status = _clean(fit.get("status"))

        if fit_status == "ready":
            ready_candidates.append(enriched)
        elif fit_status == "needs_review":
            needs_review_candidates.append(enriched)
            warnings.extend(_strings(fit.get("warnings")))
        else:
            blocked_candidates.append(enriched)
            blocked_reasons.extend(_strings(fit.get("blocked_reasons")))
            warnings.extend(_strings(fit.get("warnings")))

    ready_candidates = sorted(
        ready_candidates,
        key=lambda candidate: (
            -_float(candidate.get("full_options_view_score")),
            candidate.get("strategy", ""),
        ),
    )
    needs_review_candidates = sorted(
        needs_review_candidates,
        key=lambda candidate: (
            -_float(candidate.get("full_options_view_score")),
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
        blocked_reasons.append("no option strategy candidates remain after full options view")

    return {
        "artifact_type": "full_options_view_option_strategy_candidates",
        "status": status,
        "is_ready": status == "ready",
        "symbol": _string_or_none(option_strategy_candidates.get("symbol")),
        "market_regime": _string_or_none(option_strategy_candidates.get("market_regime")),
        "candidate_count": len(ready_candidates),
        "needs_review_count": len(needs_review_candidates),
        "blocked_count": len(blocked_candidates),
        "source_candidate_count": int(option_strategy_candidates.get("candidate_count", 0) or 0),
        "candidates": ready_candidates,
        "needs_review_candidates": needs_review_candidates,
        "blocked_candidates": blocked_candidates,
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_candidate_summary": _source_candidate_summary(option_strategy_candidates),
        "policy_summaries": _policy_summaries(
            regime_options_policy=regime_options_policy,
            asset_behavior_options_policy=asset_behavior_options_policy,
            option_behavior_options_policy=option_behavior_options_policy,
        ),
        "excluded": EXCLUDED_ACTIONS,
    }


def _fit_input_errors(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    strategy: str | None,
    regime_options_policy: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(strategy_candidate, Mapping):
        errors.append("strategy_candidate must be a mapping")
    elif not strategy:
        errors.append("strategy is required")

    errors.extend(
        _policy_input_errors(
            regime_options_policy,
            policy_name="regime_options_policy",
            required_artifact_type="regime_options_policy",
        )
    )
    errors.extend(
        _policy_input_errors(
            asset_behavior_options_policy,
            policy_name="asset_behavior_options_policy",
            required_artifact_type="asset_behavior_options_setup_policy",
        )
    )
    errors.extend(
        _policy_input_errors(
            option_behavior_options_policy,
            policy_name="option_behavior_options_policy",
            required_artifact_type="option_behavior_options_strategy_policy",
        )
    )

    return errors


def _application_input_errors(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    regime_options_policy: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(option_strategy_candidates, Mapping):
        errors.append("option_strategy_candidates must be a mapping")
    elif _clean(option_strategy_candidates.get("status")) not in VALID_CANDIDATE_STATUSES:
        errors.append("invalid option strategy candidate status")

    errors.extend(
        _policy_input_errors(
            regime_options_policy,
            policy_name="regime_options_policy",
            required_artifact_type="regime_options_policy",
        )
    )
    errors.extend(
        _policy_input_errors(
            asset_behavior_options_policy,
            policy_name="asset_behavior_options_policy",
            required_artifact_type="asset_behavior_options_setup_policy",
        )
    )
    errors.extend(
        _policy_input_errors(
            option_behavior_options_policy,
            policy_name="option_behavior_options_policy",
            required_artifact_type="option_behavior_options_strategy_policy",
        )
    )

    return errors


def _policy_input_errors(
    policy: Mapping[str, Any] | None,
    *,
    policy_name: str,
    required_artifact_type: str,
) -> list[str]:
    if not isinstance(policy, Mapping):
        return [f"{policy_name} must be a mapping"]

    errors: list[str] = []
    if _clean(policy.get("artifact_type")) != required_artifact_type:
        errors.append(f"{policy_name} has invalid artifact_type")
    if _clean(policy.get("status")) == "blocked":
        errors.append(f"{policy_name} is blocked")
    if not isinstance(policy.get("strategy_policy"), Mapping):
        errors.append(f"{policy_name} missing strategy_policy")
    return errors


def _blocked_fit(
    *,
    strategy: str | None,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str] | None = None,
    regime_fit: Mapping[str, Any] | None = None,
    asset_behavior_fit: Mapping[str, Any] | None = None,
    option_behavior_fit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "full_options_view_strategy_fit",
        "status": "blocked",
        "is_ready": False,
        "strategy": strategy,
        "decision": "block",
        "base_score": 0.0,
        "total_score_adjustment": 0.0,
        "full_options_view_score": 0.0,
        "regime_policy_status": _policy_status_from_fit(regime_fit),
        "asset_behavior_policy_status": _policy_status_from_fit(asset_behavior_fit),
        "option_behavior_policy_status": _policy_status_from_fit(option_behavior_fit),
        "regime_fit": _fit_summary(regime_fit),
        "asset_behavior_fit": _fit_summary(asset_behavior_fit),
        "option_behavior_fit": _fit_summary(option_behavior_fit),
        "warnings": _dedupe_strings(warnings or []),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
    }


def _blocked_application(
    *,
    blocked_reasons: Sequence[str],
    symbol: str | None = None,
    market_regime: str | None = None,
    warnings: Sequence[str] | None = None,
    source_candidate_summary: Mapping[str, Any] | None = None,
    policy_summaries: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "full_options_view_option_strategy_candidates",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "market_regime": market_regime,
        "candidate_count": 0,
        "needs_review_count": 0,
        "blocked_count": 0,
        "source_candidate_count": 0,
        "candidates": [],
        "needs_review_candidates": [],
        "blocked_candidates": [],
        "warnings": _dedupe_strings(warnings or []),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_candidate_summary": dict(source_candidate_summary or {}),
        "policy_summaries": dict(policy_summaries or {}),
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
    if ready_count > 0:
        if source_status == "needs_review" or needs_review_count > 0 or blocked_count > 0 or warnings:
            return "needs_review"
        return "ready"

    if needs_review_count > 0:
        return "needs_review"

    return "blocked"


def _combined_decision(*, policy_statuses: Sequence[str | None], status: str) -> str:
    if status == "blocked":
        return "block"
    if status == "needs_review":
        return "manual_review"
    preferred_count = sum(1 for policy_status in policy_statuses if policy_status == "preferred")
    if preferred_count >= 2:
        return "favor"
    return "allow"


def _enrich_candidate_with_full_options_view(
    *,
    candidate: Mapping[str, Any],
    fit: Mapping[str, Any],
) -> dict[str, Any]:
    enriched = dict(candidate)
    enriched["full_options_view_fit"] = {
        "status": fit.get("status"),
        "decision": fit.get("decision"),
        "base_score": fit.get("base_score"),
        "total_score_adjustment": fit.get("total_score_adjustment"),
        "full_options_view_score": fit.get("full_options_view_score"),
        "regime_policy_status": fit.get("regime_policy_status"),
        "asset_behavior_policy_status": fit.get("asset_behavior_policy_status"),
        "option_behavior_policy_status": fit.get("option_behavior_policy_status"),
        "warnings": list(_strings(fit.get("warnings"))),
        "blocked_reasons": list(_strings(fit.get("blocked_reasons"))),
    }
    enriched["regime_fit"] = dict(fit.get("regime_fit") or {})
    enriched["asset_behavior_fit"] = dict(fit.get("asset_behavior_fit") or {})
    enriched["option_behavior_fit"] = dict(fit.get("option_behavior_fit") or {})
    enriched["full_options_view_score"] = fit.get("full_options_view_score")
    return enriched


def _fit_summary(fit: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fit, Mapping):
        return {}
    return {
        "status": fit.get("status"),
        "policy_status": fit.get("policy_status"),
        "decision": fit.get("decision"),
        "fit_score": fit.get("fit_score"),
        "score_adjustment": fit.get("score_adjustment"),
        "warnings": list(_strings(fit.get("warnings"))),
        "blocked_reasons": list(_strings(fit.get("blocked_reasons"))),
    }


def _policy_status_from_fit(fit: Mapping[str, Any] | None) -> str | None:
    if not isinstance(fit, Mapping):
        return None
    return _string_or_none(fit.get("policy_status"))


def _policy_summaries(
    *,
    regime_options_policy: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "regime_options_policy": _policy_summary(
            regime_options_policy,
            keys=("regime_label", "normalized_regime", "directional_bias", "risk_posture"),
        ),
        "asset_behavior_options_policy": _policy_summary(
            asset_behavior_options_policy,
            keys=("asset_behavior_label", "directional_bias", "risk_posture"),
        ),
        "option_behavior_options_policy": _policy_summary(
            option_behavior_options_policy,
            keys=("volatility_pricing_bias", "liquidity_posture", "greek_risk_posture"),
        ),
    }


def _policy_summary(policy: Mapping[str, Any] | None, *, keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        return {"status": "missing"}

    summary = {
        "artifact_type": policy.get("artifact_type"),
        "status": policy.get("status"),
        "is_ready": policy.get("is_ready"),
        "warnings": list(_strings(policy.get("warnings"))),
        "blocked_reasons": list(_strings(policy.get("blocked_reasons"))),
    }
    for key in keys:
        summary[key] = policy.get(key)
    return summary


def _source_candidate_summary(option_strategy_candidates: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(option_strategy_candidates, Mapping):
        return {}

    return {
        "artifact_type": option_strategy_candidates.get("artifact_type"),
        "status": option_strategy_candidates.get("status"),
        "symbol": option_strategy_candidates.get("symbol"),
        "market_regime": option_strategy_candidates.get("market_regime"),
        "candidate_count": option_strategy_candidates.get("candidate_count"),
        "needs_review_count": option_strategy_candidates.get("needs_review_count"),
        "blocked_count": option_strategy_candidates.get("blocked_count"),
    }


def _strategy_from_candidate(strategy_candidate: Mapping[str, Any] | None) -> str | None:
    if not isinstance(strategy_candidate, Mapping):
        return None
    return _string_or_none(strategy_candidate.get("strategy"))


def _clean(value: Any) -> str | None:
    return _string_or_none(value)


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip().lower()
        return stripped or None
    return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in (_string_or_none(item) for item in value) if item]


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe_strings(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _string_or_none(value)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


