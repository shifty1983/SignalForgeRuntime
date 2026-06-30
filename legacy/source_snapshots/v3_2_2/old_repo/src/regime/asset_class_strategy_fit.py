from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.options_strategy.catalog import UNDEFINED_RISK_STRATEGIES
from src.signalforge.engines.regime.asset_class_policy import EXCLUDED_ACTIONS, normalize_asset_class


VALID_FIT_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}

ASSET_CLASS_POLICY_STATUS_SCORES = {
    "preferred": 3.0,
    "allowed": 2.0,
    "needs_review": 1.0,
    "blocked": 0.0,
}

ASSET_CLASS_SCORE_ADJUSTMENTS = {
    "preferred": 1.0,
    "allowed": 0.5,
    "needs_review": -0.5,
    "blocked": 0.0,
}

ASSET_CLASS_FIT_DECISIONS = {
    "preferred": "favor",
    "allowed": "allow",
    "needs_review": "manual_review",
    "blocked": "block",
}


def evaluate_asset_class_strategy_fit(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    regime_asset_class_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Evaluate one strategy candidate against the regime asset-class policy.

    This is a policy/fit layer only. It does not classify the symbol, choose
    strikes/expirations, submit orders, model fills, or create automatic
    maintenance/defense actions.
    """

    strategy = _strategy_from_candidate(strategy_candidate)
    asset_class = _asset_class_from_candidate(strategy_candidate)
    input_errors = _fit_input_errors(
        strategy_candidate=strategy_candidate,
        regime_asset_class_policy=regime_asset_class_policy,
        strategy=strategy,
        asset_class=asset_class,
    )
    if input_errors:
        return _blocked_fit(
            strategy=strategy,
            asset_class=asset_class,
            blocked_reasons=input_errors,
        )

    assert isinstance(regime_asset_class_policy, Mapping)
    assert strategy is not None
    assert asset_class is not None

    if strategy in UNDEFINED_RISK_STRATEGIES:
        return _blocked_fit(
            strategy=strategy,
            asset_class=asset_class,
            blocked_reasons=["undefined risk strategies are hard-blocked"],
            regime_asset_class_policy=regime_asset_class_policy,
            policy_status="blocked",
        )

    policy_status = _policy_status_for_asset_class_strategy(
        regime_asset_class_policy=regime_asset_class_policy,
        asset_class=asset_class,
        strategy=strategy,
    )
    if policy_status is None:
        return {
            "artifact_type": "regime_asset_class_strategy_fit",
            "status": "needs_review",
            "is_ready": False,
            "strategy": strategy,
            "asset_class": asset_class,
            "regime_label": regime_asset_class_policy.get("regime_label"),
            "normalized_regime": regime_asset_class_policy.get("normalized_regime"),
            "policy_status": "not_found",
            "fit_score": 1.0,
            "score_adjustment": -0.5,
            "decision": "manual_review",
            "warnings": ["strategy or asset class not found in asset-class policy; manual review required"],
            "blocked_reasons": [],
            "excluded": EXCLUDED_ACTIONS,
        }

    if policy_status == "blocked":
        return _blocked_fit(
            strategy=strategy,
            asset_class=asset_class,
            blocked_reasons=["strategy blocked by regime asset-class policy"],
            regime_asset_class_policy=regime_asset_class_policy,
            policy_status=policy_status,
        )

    status = "needs_review" if policy_status == "needs_review" else "ready"
    warnings = []
    if policy_status == "needs_review":
        warnings.append("strategy requires manual review for this asset class under current regime")

    return {
        "artifact_type": "regime_asset_class_strategy_fit",
        "status": status,
        "is_ready": status == "ready",
        "strategy": strategy,
        "asset_class": asset_class,
        "regime_label": regime_asset_class_policy.get("regime_label"),
        "normalized_regime": regime_asset_class_policy.get("normalized_regime"),
        "policy_status": policy_status,
        "fit_score": ASSET_CLASS_POLICY_STATUS_SCORES[policy_status],
        "score_adjustment": ASSET_CLASS_SCORE_ADJUSTMENTS[policy_status],
        "decision": ASSET_CLASS_FIT_DECISIONS[policy_status],
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
    }


def apply_asset_class_policy_to_strategy_candidates(
    *,
    strategy_candidates: Mapping[str, Any] | None,
    regime_asset_class_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Apply the regime asset-class policy to a generated strategy-candidate set.

    Output groups:
    - candidates: ready candidates only
    - needs_review_candidates: possible but require review
    - blocked_candidates: blocked by asset-class policy or defined-risk gate
    """

    input_errors = _application_input_errors(
        strategy_candidates=strategy_candidates,
        regime_asset_class_policy=regime_asset_class_policy,
    )
    if input_errors:
        return _blocked_application(blocked_reasons=input_errors)

    assert isinstance(strategy_candidates, Mapping)
    assert isinstance(regime_asset_class_policy, Mapping)

    source_status = _clean(strategy_candidates.get("status"))
    if source_status == "blocked":
        return _blocked_application(
            regime_asset_class_policy=regime_asset_class_policy,
            warnings=_strings(strategy_candidates.get("warnings")),
            blocked_reasons=_strings(strategy_candidates.get("blocked_reasons"))
            or ["source strategy candidates are blocked"],
            source_candidate_summary=_source_candidate_summary(strategy_candidates),
        )

    ready_candidates: list[dict[str, Any]] = []
    needs_review_candidates: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []
    warnings: list[str] = list(_strings(strategy_candidates.get("warnings")))
    blocked_reasons: list[str] = []

    for candidate in _mapping_list(strategy_candidates.get("candidates")):
        fit = evaluate_asset_class_strategy_fit(
            strategy_candidate=candidate,
            regime_asset_class_policy=regime_asset_class_policy,
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
            -_float(candidate.get("asset_class_adjusted_score")),
            candidate.get("asset_class", ""),
            candidate.get("strategy", ""),
        ),
    )
    needs_review_candidates = sorted(
        needs_review_candidates,
        key=lambda candidate: (
            -_float(candidate.get("asset_class_adjusted_score")),
            candidate.get("asset_class", ""),
            candidate.get("strategy", ""),
        ),
    )
    blocked_candidates = sorted(
        blocked_candidates,
        key=lambda candidate: (
            candidate.get("asset_class", ""),
            candidate.get("strategy", ""),
        ),
    )

    status = _application_status(
        source_status=source_status,
        ready_count=len(ready_candidates),
        needs_review_count=len(needs_review_candidates),
        blocked_count=len(blocked_candidates),
        warnings=warnings,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("no strategy candidates remain after asset-class policy")

    return {
        "artifact_type": "regime_asset_class_filtered_strategy_candidates",
        "status": status,
        "is_ready": status == "ready",
        "regime_label": regime_asset_class_policy.get("regime_label"),
        "normalized_regime": regime_asset_class_policy.get("normalized_regime"),
        "candidate_count": len(ready_candidates),
        "needs_review_count": len(needs_review_candidates),
        "blocked_count": len(blocked_candidates),
        "source_candidate_count": int(strategy_candidates.get("candidate_count", 0) or 0),
        "candidates": ready_candidates,
        "needs_review_candidates": needs_review_candidates,
        "blocked_candidates": blocked_candidates,
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_candidate_summary": _source_candidate_summary(strategy_candidates),
        "source_asset_class_policy_summary": _source_asset_class_policy_summary(regime_asset_class_policy),
        "excluded": EXCLUDED_ACTIONS,
    }


def _fit_input_errors(
    *,
    strategy_candidate: Mapping[str, Any] | None,
    regime_asset_class_policy: Mapping[str, Any] | None,
    strategy: str | None,
    asset_class: str | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(strategy_candidate, Mapping):
        errors.append("strategy_candidate must be a mapping")
    else:
        if not strategy:
            errors.append("strategy is required")
        if not asset_class:
            errors.append("asset_class is required")

    if not isinstance(regime_asset_class_policy, Mapping):
        errors.append("regime_asset_class_policy must be a mapping")
    elif _clean(regime_asset_class_policy.get("status")) == "blocked":
        errors.append("regime asset-class policy is blocked")
    elif not isinstance(regime_asset_class_policy.get("asset_class_policy_details"), Sequence):
        errors.append("regime asset-class policy missing asset_class_policy_details")

    return errors


def _application_input_errors(
    *,
    strategy_candidates: Mapping[str, Any] | None,
    regime_asset_class_policy: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(strategy_candidates, Mapping):
        errors.append("strategy_candidates must be a mapping")
    elif _clean(strategy_candidates.get("status")) not in {
        "ready",
        "needs_review",
        "blocked",
    }:
        errors.append("invalid strategy candidate status")

    if not isinstance(regime_asset_class_policy, Mapping):
        errors.append("regime_asset_class_policy must be a mapping")
    elif _clean(regime_asset_class_policy.get("status")) == "blocked":
        errors.append("regime asset-class policy is blocked")
    elif not isinstance(regime_asset_class_policy.get("asset_class_policy_details"), Sequence):
        errors.append("regime asset-class policy missing asset_class_policy_details")

    return errors


def _strategy_from_candidate(strategy_candidate: Mapping[str, Any] | None) -> str | None:
    if not isinstance(strategy_candidate, Mapping):
        return None

    return _string_or_none(strategy_candidate.get("strategy"))


def _asset_class_from_candidate(strategy_candidate: Mapping[str, Any] | None) -> str | None:
    if not isinstance(strategy_candidate, Mapping):
        return None

    value = (
        strategy_candidate.get("asset_class")
        or strategy_candidate.get("asset_class_name")
        or strategy_candidate.get("market")
    )
    normalized = normalize_asset_class(value)
    return normalized or None


def _policy_status_for_asset_class_strategy(
    *,
    regime_asset_class_policy: Mapping[str, Any],
    asset_class: str,
    strategy: str,
) -> str | None:
    for detail in _mapping_list(regime_asset_class_policy.get("asset_class_policy_details")):
        if _clean(detail.get("asset_class")) != asset_class:
            continue

        strategy_policy = detail.get("strategy_policy")
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
    enriched["asset_class"] = fit.get("asset_class") or _asset_class_from_candidate(candidate)
    enriched["asset_class_fit"] = {
        "status": fit.get("status"),
        "policy_status": fit.get("policy_status"),
        "decision": fit.get("decision"),
        "fit_score": fit.get("fit_score"),
        "score_adjustment": fit.get("score_adjustment"),
        "warnings": list(_strings(fit.get("warnings"))),
        "blocked_reasons": list(_strings(fit.get("blocked_reasons"))),
    }
    enriched["asset_class_adjusted_score"] = round(score + score_adjustment, 4)
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
    asset_class: str | None,
    blocked_reasons: Sequence[str],
    regime_asset_class_policy: Mapping[str, Any] | None = None,
    policy_status: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "regime_asset_class_strategy_fit",
        "status": "blocked",
        "is_ready": False,
        "strategy": strategy,
        "asset_class": asset_class,
        "regime_label": regime_asset_class_policy.get("regime_label")
        if isinstance(regime_asset_class_policy, Mapping)
        else None,
        "normalized_regime": regime_asset_class_policy.get("normalized_regime")
        if isinstance(regime_asset_class_policy, Mapping)
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
    regime_asset_class_policy: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
    blocked_reasons: Sequence[str] | None = None,
    source_candidate_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "regime_asset_class_filtered_strategy_candidates",
        "status": "blocked",
        "is_ready": False,
        "regime_label": regime_asset_class_policy.get("regime_label")
        if isinstance(regime_asset_class_policy, Mapping)
        else None,
        "normalized_regime": regime_asset_class_policy.get("normalized_regime")
        if isinstance(regime_asset_class_policy, Mapping)
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
        "source_asset_class_policy_summary": _source_asset_class_policy_summary(regime_asset_class_policy),
        "excluded": EXCLUDED_ACTIONS,
    }


def _source_candidate_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": source.get("artifact_type"),
        "status": source.get("status"),
        "candidate_count": source.get("candidate_count", 0),
        "rejected_count": source.get("rejected_count", 0),
        "blocked_reasons": list(_strings(source.get("blocked_reasons"))),
        "warnings": list(_strings(source.get("warnings"))),
    }


def _source_asset_class_policy_summary(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        return {}

    details = _mapping_list(policy.get("asset_class_policy_details"))
    return {
        "artifact_type": policy.get("artifact_type"),
        "status": policy.get("status"),
        "regime_label": policy.get("regime_label"),
        "normalized_regime": policy.get("normalized_regime"),
        "asset_class_count": len(details),
        "preferred_asset_class_count": len(
            [detail for detail in details if detail.get("asset_class_status") == "preferred"]
        ),
        "needs_review_asset_class_count": len(
            [detail for detail in details if detail.get("asset_class_status") == "needs_review"]
        ),
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
