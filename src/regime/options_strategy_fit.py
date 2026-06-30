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

VALID_FIT_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}

REGIME_POLICY_STATUS_SCORES = {
    "preferred": 3.0,
    "allowed": 2.0,
    "needs_review": 1.0,
    "blocked": 0.0,
}

REGIME_SCORE_ADJUSTMENTS = {
    "preferred": 1.0,
    "allowed": 0.5,
    "needs_review": -0.5,
    "blocked": 0.0,
}

REGIME_FIT_DECISIONS = {
    "preferred": "favor",
    "allowed": "allow",
    "needs_review": "manual_review",
    "blocked": "block",
}


def evaluate_regime_option_strategy_fit(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    regime_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Evaluate one concrete defined-risk option strategy candidate against an
    options-aware regime policy.

    This is a policy/fit layer only. It does not create contracts, choose
    strikes/expirations, submit orders, model fills, or create automatic
    maintenance/defense actions.
    """

    strategy = _strategy_from_candidate(strategy_candidate)
    input_errors = _fit_input_errors(strategy_candidate, regime_options_policy, strategy)
    if input_errors:
        return _blocked_fit(strategy=strategy, blocked_reasons=input_errors)

    assert isinstance(regime_options_policy, Mapping)

    if strategy in UNDEFINED_RISK_STRATEGIES:
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=["undefined risk strategies are hard-blocked"],
        )

    policy_status = _policy_status_for_strategy(regime_options_policy, strategy)
    if policy_status is None:
        return {
            "artifact_type": "regime_option_strategy_fit",
            "status": "needs_review",
            "is_ready": False,
            "strategy": strategy,
            "regime_label": regime_options_policy.get("regime_label"),
            "normalized_regime": regime_options_policy.get("normalized_regime"),
            "policy_status": "not_found",
            "fit_score": 1.0,
            "score_adjustment": -0.5,
            "decision": "manual_review",
            "warnings": ["strategy not found in regime policy; manual review required"],
            "blocked_reasons": [],
            "excluded": EXCLUDED_ACTIONS,
        }

    if policy_status == "blocked":
        return _blocked_fit(
            strategy=strategy,
            blocked_reasons=["strategy blocked by regime options policy"],
            regime_options_policy=regime_options_policy,
            policy_status=policy_status,
        )

    status = "needs_review" if policy_status == "needs_review" else "ready"
    warnings = []
    if policy_status == "needs_review":
        warnings.append("strategy requires manual review under current regime policy")

    return {
        "artifact_type": "regime_option_strategy_fit",
        "status": status,
        "is_ready": status == "ready",
        "strategy": strategy,
        "regime_label": regime_options_policy.get("regime_label"),
        "normalized_regime": regime_options_policy.get("normalized_regime"),
        "policy_status": policy_status,
        "fit_score": REGIME_POLICY_STATUS_SCORES[policy_status],
        "score_adjustment": REGIME_SCORE_ADJUSTMENTS[policy_status],
        "decision": REGIME_FIT_DECISIONS[policy_status],
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
    }


def apply_regime_policy_to_option_candidates(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    regime_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Apply an options-aware regime policy to generated option strategy candidates.

    Output groups:
    - candidates: regime-ready candidates only
    - needs_review_candidates: candidates that remain possible but need review
    - blocked_candidates: candidates blocked by the regime or defined-risk gate
    """

    input_errors = _application_input_errors(
        option_strategy_candidates=option_strategy_candidates,
        regime_options_policy=regime_options_policy,
    )
    if input_errors:
        return _blocked_application(blocked_reasons=input_errors)

    assert isinstance(option_strategy_candidates, Mapping)
    assert isinstance(regime_options_policy, Mapping)

    source_status = _clean(option_strategy_candidates.get("status"))
    if source_status == "blocked":
        return _blocked_application(
            symbol=_string_or_none(option_strategy_candidates.get("symbol")),
            market_regime=_string_or_none(
                option_strategy_candidates.get("market_regime")
            ),
            regime_options_policy=regime_options_policy,
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
        fit = evaluate_regime_option_strategy_fit(
            strategy_candidate=candidate,
            regime_options_policy=regime_options_policy,
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
        key=lambda candidate: (-_float(candidate.get("regime_adjusted_score")), candidate.get("strategy", "")),
    )
    needs_review_candidates = sorted(
        needs_review_candidates,
        key=lambda candidate: (-_float(candidate.get("regime_adjusted_score")), candidate.get("strategy", "")),
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
        blocked_reasons.append("no option strategy candidates remain after regime policy")

    return {
        "artifact_type": "regime_filtered_option_strategy_candidates",
        "status": status,
        "is_ready": status == "ready",
        "symbol": _string_or_none(option_strategy_candidates.get("symbol")),
        "market_regime": _string_or_none(option_strategy_candidates.get("market_regime")),
        "regime_label": regime_options_policy.get("regime_label"),
        "normalized_regime": regime_options_policy.get("normalized_regime"),
        "directional_bias": regime_options_policy.get("directional_bias"),
        "risk_posture": regime_options_policy.get("risk_posture"),
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
        "source_regime_policy_summary": _source_regime_policy_summary(regime_options_policy),
        "excluded": EXCLUDED_ACTIONS,
    }


def _fit_input_errors(
    strategy_candidate: Mapping[str, Any] | None,
    regime_options_policy: Mapping[str, Any] | None,
    strategy: str | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(strategy_candidate, Mapping):
        errors.append("strategy_candidate must be a mapping")
    elif not strategy:
        errors.append("strategy is required")

    if not isinstance(regime_options_policy, Mapping):
        errors.append("regime_options_policy must be a mapping")
    elif _clean(regime_options_policy.get("status")) == "blocked":
        errors.append("regime options policy is blocked")
    elif not isinstance(regime_options_policy.get("strategy_policy"), Mapping):
        errors.append("regime options policy missing strategy_policy")

    return errors


def _application_input_errors(
    *,
    option_strategy_candidates: Mapping[str, Any] | None,
    regime_options_policy: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(option_strategy_candidates, Mapping):
        errors.append("option_strategy_candidates must be a mapping")
    elif _clean(option_strategy_candidates.get("status")) not in {
        "ready",
        "needs_review",
        "blocked",
    }:
        errors.append("invalid option strategy candidate status")

    if not isinstance(regime_options_policy, Mapping):
        errors.append("regime_options_policy must be a mapping")
    elif _clean(regime_options_policy.get("status")) == "blocked":
        errors.append("regime options policy is blocked")
    elif not isinstance(regime_options_policy.get("strategy_policy"), Mapping):
        errors.append("regime options policy missing strategy_policy")

    return errors


def _strategy_from_candidate(strategy_candidate: Mapping[str, Any] | None) -> str | None:
    if not isinstance(strategy_candidate, Mapping):
        return None

    strategy = _string_or_none(strategy_candidate.get("strategy"))
    return strategy


def _policy_status_for_strategy(
    regime_options_policy: Mapping[str, Any],
    strategy: str,
) -> str | None:
    strategy_policy = regime_options_policy.get("strategy_policy")
    if not isinstance(strategy_policy, Mapping):
        return None

    for status in ("preferred", "allowed", "needs_review", "blocked"):
        strategies = {_clean(item) for item in _strings(strategy_policy.get(status))}
        if strategy in strategies:
            return status

    return None


def _enrich_candidate_with_fit(
    *,
    candidate: Mapping[str, Any],
    fit: Mapping[str, Any],
) -> dict[str, Any]:
    score = _float(candidate.get("score"))
    score_adjustment = _float(fit.get("score_adjustment"))

    enriched = dict(candidate)
    enriched["regime_fit"] = {
        "status": fit.get("status"),
        "policy_status": fit.get("policy_status"),
        "decision": fit.get("decision"),
        "fit_score": fit.get("fit_score"),
        "score_adjustment": fit.get("score_adjustment"),
        "warnings": list(_strings(fit.get("warnings"))),
        "blocked_reasons": list(_strings(fit.get("blocked_reasons"))),
    }
    enriched["regime_adjusted_score"] = round(score + score_adjustment, 4)
    return enriched


def _application_status(
    *,
    source_status: str,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    warnings: Sequence[str],
) -> str:
    if ready_count > 0 and source_status == "ready" and not warnings:
        return "ready"

    if ready_count > 0 or needs_review_count > 0:
        return "needs_review"

    if blocked_count > 0:
        return "blocked"

    return "needs_review"


def _blocked_fit(
    *,
    strategy: str | None,
    blocked_reasons: Sequence[str],
    regime_options_policy: Mapping[str, Any] | None = None,
    policy_status: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "regime_option_strategy_fit",
        "status": "blocked",
        "is_ready": False,
        "strategy": strategy,
        "regime_label": regime_options_policy.get("regime_label")
        if isinstance(regime_options_policy, Mapping)
        else None,
        "normalized_regime": regime_options_policy.get("normalized_regime")
        if isinstance(regime_options_policy, Mapping)
        else None,
        "policy_status": policy_status or "blocked",
        "fit_score": 0.0,
        "score_adjustment": 0.0,
        "decision": "block",
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
    }


def _blocked_application(
    *,
    symbol: str | None = None,
    market_regime: str | None = None,
    regime_options_policy: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
    blocked_reasons: Sequence[str] | None = None,
    source_candidate_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "regime_filtered_option_strategy_candidates",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "market_regime": market_regime,
        "regime_label": regime_options_policy.get("regime_label")
        if isinstance(regime_options_policy, Mapping)
        else None,
        "normalized_regime": regime_options_policy.get("normalized_regime")
        if isinstance(regime_options_policy, Mapping)
        else None,
        "directional_bias": regime_options_policy.get("directional_bias")
        if isinstance(regime_options_policy, Mapping)
        else None,
        "risk_posture": regime_options_policy.get("risk_posture")
        if isinstance(regime_options_policy, Mapping)
        else None,
        "candidate_count": 0,
        "needs_review_count": 0,
        "blocked_count": 0,
        "source_candidate_count": 0,
        "candidates": [],
        "needs_review_candidates": [],
        "blocked_candidates": [],
        "warnings": _dedupe_strings(warnings or []),
        "blocked_reasons": _dedupe_strings(blocked_reasons or []),
        "source_candidate_summary": dict(source_candidate_summary or {}),
        "source_regime_policy_summary": _source_regime_policy_summary(regime_options_policy),
        "excluded": EXCLUDED_ACTIONS,
    }


def _source_candidate_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": source.get("artifact_type"),
        "status": source.get("status"),
        "symbol": source.get("symbol"),
        "market_regime": source.get("market_regime"),
        "candidate_count": source.get("candidate_count", 0),
        "rejected_count": source.get("rejected_count", 0),
        "blocked_reasons": list(_strings(source.get("blocked_reasons"))),
        "warnings": list(_strings(source.get("warnings"))),
    }


def _source_regime_policy_summary(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        return {}

    strategy_policy = policy.get("strategy_policy")
    if not isinstance(strategy_policy, Mapping):
        strategy_policy = {}

    return {
        "artifact_type": policy.get("artifact_type"),
        "status": policy.get("status"),
        "regime_label": policy.get("regime_label"),
        "normalized_regime": policy.get("normalized_regime"),
        "directional_bias": policy.get("directional_bias"),
        "risk_posture": policy.get("risk_posture"),
        "preferred_count": len(list(_strings(strategy_policy.get("preferred")))),
        "allowed_count": len(list(_strings(strategy_policy.get("allowed")))),
        "needs_review_count": len(list(_strings(strategy_policy.get("needs_review")))),
        "blocked_count": len(list(_strings(strategy_policy.get("blocked")))),
    }


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    return [item for item in value if isinstance(item, Mapping)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    return [_clean(item) for item in value if _clean(item)]


def _string_or_none(value: Any) -> str | None:
    cleaned = _clean(value)
    return cleaned or None


def _clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)

    return output


