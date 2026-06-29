from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


REGIME_DIRECTIONAL_POLICY_SCHEMA_VERSION = "signalforge_regime_directional_policy.v1"

DIRECTIONAL_STANCES = {
    "long_bias",
    "short_bias",
    "neutral_bias",
}

DEFAULT_ASSET_CLASSES = (
    "equities",
    "bonds",
    "credit",
    "commodities",
    "currencies",
    "volatility",
)


def build_signalforge_regime_directional_policy(
    regime_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(regime_source, Mapping):
        return _blocked_result("regime source must be a mapping")

    policies = _extract_asset_class_policies(regime_source)
    if not policies:
        return _blocked_result("regime source does not contain asset class policy")

    context = _extract_regime_context(regime_source)

    directional_policies = [
        _build_asset_class_directional_policy(policy, context)
        for policy in policies
    ]

    directional_policies = sorted(
        directional_policies,
        key=lambda item: str(item.get("asset_class")),
    )

    warning_items = _build_warning_items(regime_source, directional_policies)
    status = "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_regime_directional_policy",
        "schema_version": REGIME_DIRECTIONAL_POLICY_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "regime_directional_policy",
        "adapter_type": "regime_directional_policy_builder",
        "source_artifact_type": regime_source.get("artifact_type"),
        "source_status": regime_source.get("status"),
        "macro_regime_label": context.get("macro_regime_label"),
        "macro_regime": context.get("macro_regime"),
        "macro_regime_score": context.get("macro_regime_score"),
        "macro_regime_confidence": context.get("macro_regime_confidence"),
        "policy_regime_label": context.get("policy_regime_label"),
        "weekly_planning_label": context.get("weekly_planning_label"),
        "market_confirmation": context.get("market_confirmation"),
        "aggregate_market_bias": context.get("aggregate_market_bias"),
        "risk_environment": context.get("risk_environment"),
        "rates_regime": context.get("rates_regime"),
        "liquidity_regime": context.get("liquidity_regime"),
        "volatility_regime": context.get("volatility_regime"),
        "asset_class_directional_policies": directional_policies,
        "regime_directional_summary": _directional_summary(directional_policies),
        "blocker_items": [],
        "warning_items": warning_items,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_asset_class_directional_policy(
    policy: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    asset_class = _clean_text(policy.get("asset_class")) or "unknown"
    policy_bucket = _clean_policy_bucket(
        policy.get("policy_bucket")
        or policy.get("bucket")
        or policy.get("status")
        or policy.get("action")
    )
    directional_bias = _clean_text(
        policy.get("directional_bias")
        or policy.get("bias")
        or policy.get("asset_class_bias")
        or policy.get("policy_bias")
    )

    stance, reasons, conflicts = _infer_stance(
        asset_class=asset_class,
        policy_bucket=policy_bucket,
        directional_bias=directional_bias,
        context=context,
    )

    scores = _stance_scores(stance, policy_bucket, directional_bias)
    policy_gate = _policy_gate(policy_bucket)
    manual_review_required = policy_gate in {"review_required", "blocked"} or bool(conflicts)

    return {
        "artifact_type": "regime_asset_class_directional_policy",
        "asset_class": asset_class,
        "policy_bucket": policy_bucket,
        "policy_gate": policy_gate,
        "directional_bias": directional_bias,
        "regime_directional_stance": stance,
        "stance_score": scores["stance_score"],
        "long_score": scores["long_score"],
        "short_score": scores["short_score"],
        "neutral_score": scores["neutral_score"],
        "manual_review_required": manual_review_required,
        "policy_reason": policy.get("reason") or policy.get("policy_reason"),
        "stance_reasons": reasons,
        "conflict_reasons": conflicts,
        "source_policy": dict(policy),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _infer_stance(
    *,
    asset_class: str,
    policy_bucket: str,
    directional_bias: str | None,
    context: Mapping[str, Any],
) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    conflicts: list[str] = []

    macro = _clean_text(context.get("macro_regime_label"))
    composite_macro = _clean_text(context.get("macro_regime"))
    policy_regime = _clean_text(context.get("policy_regime_label"))
    regime = policy_regime or composite_macro or macro
    risk = _clean_text(context.get("risk_environment"))
    rates = _clean_text(context.get("rates_regime"))
    vol = _clean_text(context.get("volatility_regime"))
    market_confirmation = _clean_text(context.get("market_confirmation"))
    aggregate_market_bias = _clean_text(context.get("aggregate_market_bias"))

    if policy_bucket == "blocked":
        reasons.append("asset_class_policy_blocked_direction_neutralized")
        return "neutral_bias", reasons, conflicts
    
    if directional_bias:
        bias_stance = _stance_from_directional_bias(directional_bias)
        if bias_stance:
            reasons.append(f"directional_bias_{directional_bias}")
            return bias_stance, reasons, conflicts    

    composite_stance = _composite_macro_stance(asset_class=asset_class, regime=regime)
    if composite_stance:
        stance, reason = composite_stance
        reasons.append(reason)
        return stance, reasons, conflicts

    if asset_class == "equities":
        if _contains_any(regime, {"expansion", "overheating", "risk_on"}):
            reasons.append("equity_supported_by_growth_or_risk_on_regime")
            return "long_bias", reasons, conflicts
        if _contains_any(regime, {"contraction", "recession", "risk_off"}):
            reasons.append("equity_challenged_by_risk_off_or_contraction_regime")
            return "short_bias", reasons, conflicts

    if asset_class == "bonds":
        if _contains_any(rates, {"rising", "tightening"}) or _contains_any(regime, {"overheating", "inflation"}):
            reasons.append("duration_challenged_by_rising_rates_or_inflation")
            return "short_bias", reasons, conflicts
        if _contains_any(rates, {"falling", "easing"}) or _contains_any(regime, {"contraction", "recession", "deflation"}):
            reasons.append("duration_supported_by_falling_rates_or_slowdown")
            return "long_bias", reasons, conflicts

    if asset_class == "commodities":
        if _contains_any(regime, {"overheating", "inflation", "stagflation"}):
            reasons.append("commodities_supported_by_inflation_sensitive_regime")
            return "long_bias", reasons, conflicts
        if _contains_any(regime, {"deflation", "contraction"}):
            reasons.append("commodities_challenged_by_deflation_or_contraction")
            return "short_bias", reasons, conflicts

    if asset_class == "credit":
        if _contains_any(risk, {"risk_on"}) or _contains_any(aggregate_market_bias, {"risk_on"}):
            reasons.append("credit_supported_by_risk_on_conditions")
            return "long_bias", reasons, conflicts
        if _contains_any(risk, {"risk_off"}) or _contains_any(aggregate_market_bias, {"risk_off"}):
            reasons.append("credit_challenged_by_risk_off_conditions")
            return "short_bias", reasons, conflicts

    if asset_class == "volatility":
        if _contains_any(risk, {"risk_on"}) or _contains_any(vol, {"compression"}):
            reasons.append("volatility_challenged_by_risk_on_or_vol_compression")
            return "short_bias", reasons, conflicts
        if _contains_any(risk, {"risk_off"}) or _contains_any(vol, {"expansion"}):
            reasons.append("volatility_supported_by_risk_off_or_vol_expansion")
            return "long_bias", reasons, conflicts

    if asset_class == "currencies":
        reasons.append("currency_policy_requires_pair_or_dollar_confirmation")
        return "neutral_bias", reasons, conflicts

    if market_confirmation and "contradict" in market_confirmation:
        reasons.append("regime_market_confirmation_conflict")
        conflicts.append("market_confirmation_contradicts_regime")
        return "neutral_bias", reasons, conflicts

    if policy_bucket == "preferred":
        reasons.append("preferred_policy_without_specific_direction_defaults_long")
        return "long_bias", reasons, conflicts

    reasons.append("no_clear_directional_edge")
    return "neutral_bias", reasons, conflicts


def _composite_macro_stance(*, asset_class: str, regime: str | None) -> tuple[str, str] | None:
    if not regime:
        return None

    risk_on_regimes = {"goldilocks", "reflation", "risk_on"}
    late_cycle_regimes = {"late_cycle_overheating", "overheating"}
    stress_regimes = {
        "credit_stress",
        "liquidity_stress",
        "deflationary_shock",
        "risk_off_transition",
        "risk_off",
    }
    slowdown_regimes = {"disinflationary_slowdown", "deflationary_slowdown"}
    inflation_stress_regimes = {"stagflation"}
    neutral_regimes = {"neutral_mixed", "mixed", "neutral", "range_bound"}

    if regime in neutral_regimes:
        return "neutral_bias", f"{asset_class}_neutral_under_{regime}"

    if asset_class == "equities":
        if regime in risk_on_regimes:
            return "long_bias", f"equities_supported_by_{regime}"
        if regime in late_cycle_regimes:
            return "neutral_bias", f"equities_need_review_under_{regime}"
        if regime in stress_regimes | slowdown_regimes | inflation_stress_regimes:
            return "short_bias", f"equities_challenged_by_{regime}"

    if asset_class == "bonds":
        if regime in {"reflation"} | late_cycle_regimes | inflation_stress_regimes:
            return "short_bias", f"duration_challenged_by_{regime}"
        if regime in stress_regimes | slowdown_regimes:
            return "long_bias", f"duration_supported_by_{regime}"
        if regime == "goldilocks":
            return "neutral_bias", "duration_neutral_under_goldilocks"

    if asset_class == "credit":
        if regime in risk_on_regimes:
            return "long_bias", f"credit_supported_by_{regime}"
        if regime in stress_regimes | slowdown_regimes | inflation_stress_regimes:
            return "short_bias", f"credit_challenged_by_{regime}"
        if regime in late_cycle_regimes:
            return "neutral_bias", f"credit_requires_spread_confirmation_under_{regime}"

    if asset_class == "commodities":
        if regime in {"reflation"} | late_cycle_regimes | inflation_stress_regimes:
            return "long_bias", f"commodities_supported_by_{regime}"
        if regime in stress_regimes | slowdown_regimes:
            return "short_bias", f"commodities_challenged_by_{regime}"

    if asset_class == "volatility":
        if regime in risk_on_regimes:
            return "short_bias", f"volatility_challenged_by_{regime}"
        if regime in stress_regimes | slowdown_regimes | inflation_stress_regimes:
            return "long_bias", f"volatility_supported_by_{regime}"
        if regime in late_cycle_regimes:
            return "neutral_bias", f"volatility_requires_confirmation_under_{regime}"

    if asset_class == "currencies":
        return "neutral_bias", "currency_policy_requires_pair_or_dollar_confirmation"

    return None

def _stance_from_directional_bias(directional_bias: str) -> str | None:
    text = directional_bias.lower()

    if _contains_any(text, {"bearish", "short", "pressure", "challenged"}):
        return "short_bias"

    if _contains_any(text, {"bullish", "long", "support", "supported", "inflation_sensitive"}):
        return "long_bias"

    if _contains_any(text, {"neutral", "balanced", "range", "review", "sensitive", "risk", "avoid", "blocked"}):
        return "neutral_bias"

    return None


def _stance_scores(
    stance: str,
    policy_bucket: str,
    directional_bias: str | None,
) -> dict[str, float]:
    if stance == "long_bias":
        scores = {"long_score": 0.70, "short_score": 0.10, "neutral_score": 0.20}
    elif stance == "short_bias":
        scores = {"long_score": 0.10, "short_score": 0.70, "neutral_score": 0.20}
    else:
        scores = {"long_score": 0.20, "short_score": 0.20, "neutral_score": 0.60}

    if policy_bucket == "preferred" and stance in {"long_bias", "short_bias"}:
        key = "long_score" if stance == "long_bias" else "short_score"
        scores[key] = min(scores[key] + 0.10, 0.95)
        scores["neutral_score"] = max(scores["neutral_score"] - 0.05, 0.0)

    if policy_bucket in {"needs_review", "blocked"}:
        if stance in {"long_bias", "short_bias"}:
            key = "long_score" if stance == "long_bias" else "short_score"
            scores[key] = max(scores[key] - 0.10, 0.0)
        scores["neutral_score"] = min(scores["neutral_score"] + 0.10, 0.95)

    if directional_bias and _contains_any(directional_bias, {"risk", "review", "sensitive"}):
        scores["neutral_score"] = min(scores["neutral_score"] + 0.05, 0.95)

    return {
        "stance_score": round(max(scores.values()), 4),
        "long_score": round(scores["long_score"], 4),
        "short_score": round(scores["short_score"], 4),
        "neutral_score": round(scores["neutral_score"], 4),
    }


def _policy_gate(policy_bucket: str) -> str:
    if policy_bucket == "blocked":
        return "blocked"
    if policy_bucket == "needs_review":
        return "review_required"
    return "allowed"


def _extract_asset_class_policies(regime_source: Mapping[str, Any]) -> list[dict[str, Any]]:
    policy_source = (
        regime_source.get("latest_regime_asset_class_policy")
        or regime_source.get("asset_class_policy")
        or regime_source.get("asset_class_policies")
    )
    return _normalize_policy_source(policy_source)


def _normalize_policy_source(policy_source: Any) -> list[dict[str, Any]]:
    if not policy_source:
        return []

    if isinstance(policy_source, Mapping):
        for nested_key in (
            "asset_class_policies",
            "asset_class_policy",
            "policy_by_asset_class",
            "policies",
        ):
            nested = policy_source.get(nested_key)
            if nested is not None:
                return _normalize_policy_source(nested)

        if policy_source.get("asset_class"):
            asset_class = _clean_text(policy_source.get("asset_class"))
            return [_normalize_policy_item(asset_class, policy_source)] if asset_class else []

        metadata_keys = {
            "artifact_type",
            "schema_version",
            "status",
            "is_ready",
            "requires_manual_approval",
            "summary",
            "metadata",
            "warnings",
            "blocked_reasons",
            "explicit_exclusions",
            "asset_class_policy_details",
            "growth_regime",
            "inflation_regime",
            "rates_regime",
            "liquidity_regime",
            "risk_environment",
            "volatility_regime",
            "regime_label",
            "normalized_regime",
            "event_risk",
            "excluded",
        }

        policies = []
        for key, value in policy_source.items():
            if key in metadata_keys:
                continue

            asset_class = _clean_text(key)
            if not asset_class:
                continue

            if isinstance(value, Mapping):
                policies.append(_normalize_policy_item(asset_class, value))
            else:
                policies.append(
                    {
                        "asset_class": asset_class,
                        "policy_bucket": _clean_policy_bucket(value),
                        "directional_bias": None,
                        "reason": None,
                    }
                )

        return policies

    if isinstance(policy_source, Sequence) and not isinstance(policy_source, (str, bytes, bytearray)):
        policies = []
        for item in policy_source:
            if not isinstance(item, Mapping):
                continue
            asset_class = _clean_text(item.get("asset_class"))
            if asset_class:
                policies.append(_normalize_policy_item(asset_class, item))
        return policies

    return []


def _normalize_policy_item(asset_class: str, item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(item),
        "asset_class": asset_class,
        "policy_bucket": _clean_policy_bucket(
            item.get("policy_bucket")
            or item.get("bucket")
            or item.get("status")
            or item.get("action")
        ),
        "directional_bias": _clean_text(
            item.get("directional_bias")
            or item.get("bias")
            or item.get("asset_class_bias")
            or item.get("policy_bias")
        ),
        "reason": item.get("reason") or item.get("policy_reason"),
    }


def _extract_regime_context(regime_source: Mapping[str, Any]) -> dict[str, Any]:
    weekly_overlay = regime_source.get("latest_weekly_overlay_row")
    macro_row = regime_source.get("latest_macro_regime_row")

    context = {
        "macro_regime_label": regime_source.get("macro_regime_label"),
        "macro_regime": regime_source.get("macro_regime"),
        "macro_regime_score": regime_source.get("macro_regime_score"),
        "macro_regime_confidence": regime_source.get("macro_regime_confidence"),
        "policy_regime_label": regime_source.get("policy_regime_label"),
        "weekly_planning_label": regime_source.get("weekly_planning_label"),
        "market_confirmation": regime_source.get("market_confirmation"),
        "aggregate_market_bias": regime_source.get("aggregate_market_bias"),
        "risk_environment": regime_source.get("weekly_risk_environment"),
        "rates_regime": regime_source.get("weekly_rates_regime"),
        "liquidity_regime": regime_source.get("weekly_liquidity_regime"),
        "volatility_regime": regime_source.get("weekly_volatility_regime"),
    }

    if isinstance(weekly_overlay, Mapping):
        context["risk_environment"] = context["risk_environment"] or weekly_overlay.get("risk_environment")
        context["rates_regime"] = context["rates_regime"] or weekly_overlay.get("rates_regime")
        context["liquidity_regime"] = context["liquidity_regime"] or weekly_overlay.get("liquidity_regime")
        context["volatility_regime"] = context["volatility_regime"] or weekly_overlay.get("volatility_regime")

    if isinstance(macro_row, Mapping):
        context["macro_regime_label"] = context["macro_regime_label"] or macro_row.get("regime_label")
        context["macro_regime"] = context["macro_regime"] or macro_row.get("macro_regime")
        context["macro_regime_score"] = context["macro_regime_score"] or macro_row.get("macro_regime_score")
        context["macro_regime_confidence"] = context["macro_regime_confidence"] or macro_row.get("macro_regime_confidence")
        context["policy_regime_label"] = context["policy_regime_label"] or macro_row.get("regime_label")
        context["risk_environment"] = context["risk_environment"] or macro_row.get("risk_environment")
        context["rates_regime"] = context["rates_regime"] or macro_row.get("rates_regime")
        context["liquidity_regime"] = context["liquidity_regime"] or macro_row.get("liquidity_regime")
        context["volatility_regime"] = context["volatility_regime"] or macro_row.get("volatility_regime")

    return context


def _directional_summary(policies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stance_counts = Counter(str(item.get("regime_directional_stance")) for item in policies)
    bucket_counts = Counter(str(item.get("policy_bucket")) for item in policies)
    gate_counts = Counter(str(item.get("policy_gate")) for item in policies)

    return {
        "asset_class_count": len(policies),
        "stance_counts": dict(sorted(stance_counts.items())),
        "policy_bucket_counts": dict(sorted(bucket_counts.items())),
        "policy_gate_counts": dict(sorted(gate_counts.items())),
        "long_bias_asset_classes": sorted(
            str(item.get("asset_class"))
            for item in policies
            if item.get("regime_directional_stance") == "long_bias"
        ),
        "short_bias_asset_classes": sorted(
            str(item.get("asset_class"))
            for item in policies
            if item.get("regime_directional_stance") == "short_bias"
        ),
        "neutral_bias_asset_classes": sorted(
            str(item.get("asset_class"))
            for item in policies
            if item.get("regime_directional_stance") == "neutral_bias"
        ),
        "review_required_asset_classes": sorted(
            str(item.get("asset_class"))
            for item in policies
            if item.get("policy_gate") == "review_required"
        ),
        "blocked_asset_classes": sorted(
            str(item.get("asset_class"))
            for item in policies
            if item.get("policy_gate") == "blocked"
        ),
        "manual_review_asset_classes": sorted(
            str(item.get("asset_class"))
            for item in policies
            if item.get("manual_review_required")
        ),
    }


def _build_warning_items(
    regime_source: Mapping[str, Any],
    policies: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    warnings = []

    source_status = _clean_text(regime_source.get("status"))
    if source_status not in {None, "ready"}:
        warnings.append(
            {
                "reason": "regime source is not ready",
                "source_status": source_status,
            }
        )

    observed = {str(item.get("asset_class")) for item in policies if item.get("asset_class")}
    missing = sorted(set(DEFAULT_ASSET_CLASSES) - observed)

    if missing:
        warnings.append(
            {
                "reason": "directional policy missing default asset classes",
                "missing_asset_classes": missing,
            }
        )

    return warnings


def _clean_policy_bucket(value: Any) -> str:
    text = _clean_text(value)
    if text in {"preferred", "allowed", "needs_review", "blocked"}:
        return text
    return "allowed"


def _contains_any(value: Any, needles: set[str]) -> bool:
    if value is None:
        return False
    text = str(value).lower()
    return any(needle in text for needle in needles)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_regime_directional_policy",
        "schema_version": REGIME_DIRECTIONAL_POLICY_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "regime_directional_policy",
        "adapter_type": "regime_directional_policy_builder",
        "asset_class_directional_policies": [],
        "regime_directional_summary": {
            "asset_class_count": 0,
            "stance_counts": {},
            "policy_bucket_counts": {},
            "policy_gate_counts": {},
            "long_bias_asset_classes": [],
            "short_bias_asset_classes": [],
            "neutral_bias_asset_classes": [],
            "review_required_asset_classes": [],
            "blocked_asset_classes": [],
            "manual_review_asset_classes": [],
        },
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
