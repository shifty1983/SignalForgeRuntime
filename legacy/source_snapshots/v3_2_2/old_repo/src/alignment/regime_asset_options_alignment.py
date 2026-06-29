from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    matrix_metadata_coverage,
    stamp_matrix_metadata,
)


REGIME_ASSET_OPTIONS_ALIGNMENT_SCHEMA_VERSION = "signalforge_regime_asset_options_alignment.v1"

MATRIX_DIMENSION_FIELDS = [
    "symbol",
    "regime_state",
    "asset_behavior_state",
    "option_behavior_state",
]


COVERED_CAPABILITIES = [
    "regime_asset_options_alignment",
    "macro_regime_alignment",
    "asset_options_alignment",
    "options_behavior_alignment",
    "policy_environment_bias",
]

DEPENDS_ON_CAPABILITIES = [
    "macro_regime",
    "asset_behavior",
    "options_behavior_integration",
]

REGIME_ITEM_KEYS = (
    "latest_weekly_overlay_row",
    "latest_ready_regime_row",
    "latest_macro_regime_row",
    "regime_row",
)
ASSET_ITEM_KEYS = (
    "asset_behaviors",
    "asset_behavior_items",
    "items",
    "data",
    "rows",
)
OPTIONS_ITEM_KEYS = (
    "options_behavior_items",
    "option_behavior_items",
    "items",
    "data",
    "rows",
)

RISK_OFF_REGIMES = {
    "deflationary_shock",
    "credit_stress",
    "liquidity_stress",
    "risk_off_transition",
}
RISK_ON_REGIMES = {"goldilocks", "reflation"}
CAUTION_REGIMES = {
    "late_cycle_overheating",
    "stagflation",
    "disinflationary_slowdown",
    "neutral_mixed",
}

REGIME_ALIASES = {
    "overheating": "late_cycle_overheating",
    "late_cycle": "late_cycle_overheating",
    "mixed": "neutral_mixed",
    "deflationary_slowdown": "disinflationary_slowdown",
    "disinflationary_slowdown_with_rates_review": "disinflationary_slowdown",
}


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_regime_asset_options_alignment(
    *,
    regime_source: Mapping[str, Any] | None,
    asset_behavior_source: Mapping[str, Any] | Sequence[Any] | None,
    options_behavior_source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    """Combine regime, asset behavior, and Options Behavior into policy alignment.

    This artifact interprets already-derived behavior artifacts. It does not choose
    final strategies, call brokers, submit orders, model slippage, or make any
    automatic strategy changes.
    """

    regime_context = _extract_regime_context(regime_source)
    asset_items = _index_by_symbol(_extract_items(asset_behavior_source, ASSET_ITEM_KEYS))
    options_items = _index_by_symbol(_extract_items(options_behavior_source, OPTIONS_ITEM_KEYS))

    blocked_reasons: list[str] = []
    if regime_context["coverage_status"] == "missing":
        blocked_reasons.append("missing_regime_context")
    if not asset_items:
        blocked_reasons.append("missing_asset_behavior_items")
    if not options_items:
        blocked_reasons.append("missing_options_behavior_items")

    source_artifacts = {
        "regime_source": _source_artifact_type(regime_source),
        "asset_behavior_source": _source_artifact_type(asset_behavior_source),
        "options_behavior_source": _source_artifact_type(options_behavior_source),
    }

    if blocked_reasons:
        return _blocked_result(blocked_reasons, source_artifacts=source_artifacts)

    symbols = sorted(set(asset_items) | set(options_items))
    items = [
        _build_alignment_item(
            symbol=symbol,
            regime_context=regime_context,
            asset_item=asset_items.get(symbol),
            options_item=options_items.get(symbol),
        )
        for symbol in symbols
    ]

    summary = _summary(items)
    matrix_dimension_summary = _matrix_dimension_summary(items)
    status = "ready" if summary["needs_review_symbol_count"] == 0 else "needs_review"

    return {
        "artifact_type": "signalforge_regime_asset_options_alignment",
        "schema_version": REGIME_ASSET_OPTIONS_ALIGNMENT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "regime_asset_options_alignment",
        "adapter_type": "regime_asset_options_alignment_builder",
        "review_scope": "policy_alignment_before_strategy_family_eligibility_not_trade_selection",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "strategy_family_eligibility",
                "priority": "high",
                "recommendation": "Use regime/asset/options alignment to mark strategy families as favored, allowed, discouraged, blocked, or review_required.",
            }
        ],
        "regime_context": regime_context,
        "alignment_items": items,
        "regime_asset_options_alignment_items": items,
        "alignment_summary": summary,
        "matrix_dimension_provider": "regime_asset_options_alignment",
        "matrix_dimension_fields": list(MATRIX_DIMENSION_FIELDS),
        "matrix_dimension_summary": matrix_dimension_summary,
        "ready_to_patch_historical_replay_exports": True,
        "ready_to_build_exact_matrix_edge_summary": False,
        "recommended_next_step": "patch_strategy_family_eligibility_matrix_metadata",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_alignment_item(
    *,
    symbol: str,
    regime_context: Mapping[str, Any],
    asset_item: Mapping[str, Any] | None,
    options_item: Mapping[str, Any] | None,
) -> dict[str, Any]:
    needs_review_reasons: list[str] = []
    if asset_item is None:
        needs_review_reasons.append("missing_asset_behavior")
    if options_item is None:
        needs_review_reasons.append("missing_options_behavior")
    if regime_context.get("coverage_status") != "ready":
        needs_review_reasons.append("regime_context_needs_review")

    asset_status = _item_status(asset_item)
    options_status = _item_status(options_item)
    if asset_status != "ready":
        needs_review_reasons.append("asset_behavior_not_ready")
    if options_status != "ready":
        needs_review_reasons.append("options_behavior_not_ready")

    macro_regime = _clean_text(regime_context.get("macro_regime")) or "not_provided"
    weekly_risk_environment = _clean_text(regime_context.get("weekly_risk_environment")) or "not_provided"
    weekly_volatility_regime = _clean_text(regime_context.get("weekly_volatility_regime")) or "not_provided"
    event_risk = regime_context.get("weekly_event_risk") is True

    asset_behavior_state = _first_clean_text(asset_item, ("behavior_state", "asset_behavior_state"), default="not_provided")
    trend_behavior = _first_clean_text(asset_item, ("trend_behavior", "trend_state"), default="not_provided")
    trend_quality = _first_clean_text(asset_item, ("trend_quality", "trend_quality_state"), default="not_provided")
    relative_strength_state = _first_clean_text(asset_item, ("relative_strength_state", "relative_strength_behavior"), default="not_provided")
    volatility_behavior = _first_clean_text(asset_item, ("volatility_behavior", "volatility_state"), default="not_provided")
    drawdown_behavior = _first_clean_text(asset_item, ("drawdown_behavior", "drawdown_state"), default="not_provided")
    beta_state = _first_clean_text(asset_item, ("beta_state", "beta_profile"), default="not_provided")
    liquidity_state = _first_clean_text(asset_item, ("liquidity_state", "asset_liquidity_state"), default="not_provided")

    options_behavior_state = _first_clean_text(options_item, ("options_behavior_state",), default="not_provided")
    premium_bias = _first_clean_text(options_item, ("premium_bias",), default="not_provided")
    strategy_family_bias = _first_clean_text(options_item, ("strategy_family_bias",), default="not_provided")
    volatility_risk_premium_state = _first_clean_text(options_item, ("volatility_risk_premium_state",), default="not_provided")
    iv_expansion_state = _first_clean_text(options_item, ("iv_expansion_state",), default="not_provided")
    gamma_state = _first_clean_text(options_item, ("gamma_concentration_state", "gamma_state"), default="not_provided")
    theta_state = _first_clean_text(options_item, ("theta_sensitivity_state", "theta_state"), default="not_provided")
    option_liquidity_state = _first_clean_text(options_item, ("liquidity_state",), default="not_provided")
    spread_state = _first_clean_text(options_item, ("spread_state",), default="not_provided")
    skew_state = _first_clean_text(options_item, ("skew_state",), default="not_provided")
    term_structure_state = _first_clean_text(options_item, ("term_structure_state",), default="not_provided")

    regime_options_alignment = _regime_options_alignment(
        macro_regime=macro_regime,
        weekly_risk_environment=weekly_risk_environment,
        weekly_volatility_regime=weekly_volatility_regime,
        event_risk=event_risk,
        options_behavior_state=options_behavior_state,
        premium_bias=premium_bias,
        iv_expansion_state=iv_expansion_state,
        gamma_state=gamma_state,
        theta_state=theta_state,
    )
    asset_options_alignment = _asset_options_alignment(
        asset_behavior_state=asset_behavior_state,
        trend_behavior=trend_behavior,
        relative_strength_state=relative_strength_state,
        volatility_behavior=volatility_behavior,
        drawdown_behavior=drawdown_behavior,
        options_behavior_state=options_behavior_state,
        premium_bias=premium_bias,
        gamma_state=gamma_state,
    )
    allowed, discouraged, blocked = _strategy_family_sets(
        macro_regime=macro_regime,
        regime_options_alignment=regime_options_alignment,
        asset_options_alignment=asset_options_alignment,
        options_behavior_state=options_behavior_state,
        premium_bias=premium_bias,
        strategy_family_bias=strategy_family_bias,
        gamma_state=gamma_state,
        theta_state=theta_state,
        event_risk=event_risk,
    )
    strategy_environment_bias = _strategy_environment_bias(
        needs_review=bool(needs_review_reasons),
        macro_regime=macro_regime,
        regime_options_alignment=regime_options_alignment,
        asset_options_alignment=asset_options_alignment,
        premium_bias=premium_bias,
        options_behavior_state=options_behavior_state,
        gamma_state=gamma_state,
    )

    if option_liquidity_state.endswith("needs_review") or spread_state.endswith("needs_review"):
        needs_review_reasons.append("option_liquidity_or_spread_needs_review")
    if options_behavior_state == "options_behavior_needs_review":
        needs_review_reasons.append("options_behavior_needs_review")

    coverage_status = "ready" if not needs_review_reasons else "needs_review"
    regime_state = macro_regime
    matrix_dimension_metadata = {
        "symbol": symbol,
        "regime_state": regime_state,
        "asset_behavior_state": asset_behavior_state,
        "option_behavior_state": options_behavior_state,
    }
    matrix_dimension_missing_fields = _missing_matrix_dimension_fields(matrix_dimension_metadata)
    matrix_dimension_state = (
        "ready"
        if coverage_status == "ready" and not matrix_dimension_missing_fields
        else "needs_review"
    )

    item = {
        "artifact_type": "regime_asset_options_alignment_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "macro_regime": macro_regime,
        "regime_state": regime_state,
        "policy_regime_label": regime_context.get("policy_regime_label"),
        "weekly_planning_label": regime_context.get("weekly_planning_label"),
        "weekly_risk_environment": weekly_risk_environment,
        "weekly_volatility_regime": weekly_volatility_regime,
        "weekly_liquidity_regime": regime_context.get("weekly_liquidity_regime"),
        "weekly_rates_regime": regime_context.get("weekly_rates_regime"),
        "weekly_event_risk": event_risk,
        "asset_behavior_state": asset_behavior_state,
        "trend_behavior": trend_behavior,
        "trend_quality": trend_quality,
        "relative_strength_state": relative_strength_state,
        "volatility_behavior": volatility_behavior,
        "drawdown_behavior": drawdown_behavior,
        "beta_state": beta_state,
        "asset_liquidity_state": liquidity_state,
        "options_behavior_state": options_behavior_state,
        "premium_bias": premium_bias,
        "strategy_family_bias": strategy_family_bias,
        "volatility_risk_premium_state": volatility_risk_premium_state,
        "iv_expansion_state": iv_expansion_state,
        "gamma_concentration_state": gamma_state,
        "theta_sensitivity_state": theta_state,
        "option_liquidity_state": option_liquidity_state,
        "spread_state": spread_state,
        "skew_state": skew_state,
        "term_structure_state": term_structure_state,
        "matrix_dimension_metadata": matrix_dimension_metadata,
        "matrix_dimension_state": matrix_dimension_state,
        "matrix_dimension_missing_fields": matrix_dimension_missing_fields,
        "matrix_dimension_source_refs": {
            "regime_state": "regime_context.macro_regime",
            "asset_behavior_state": "asset_behavior_item.asset_behavior_state",
            "option_behavior_state": "options_behavior_item.options_behavior_state",
            "symbol": "alignment_item.symbol",
        },
        "regime_options_alignment": regime_options_alignment,
        "asset_options_alignment": asset_options_alignment,
        "strategy_environment_bias": strategy_environment_bias,
        "allowed_strategy_families": allowed,
        "discouraged_strategy_families": discouraged,
        "blocked_strategy_families": blocked,
        "needs_review_reasons": sorted(set(needs_review_reasons)),
        "strategy_selection_handoff": (
            "ready_for_strategy_family_eligibility" if coverage_status == "ready" else "review_required"
        ),
        "manual_review_required": coverage_status != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    return stamp_matrix_metadata(
        item,
        metadata=matrix_dimension_metadata,
        source_refs={
            "regime_state": "regime_context.macro_regime",
            "asset_behavior_state": "asset_behavior_item.asset_behavior_state",
            "option_behavior_state": "options_behavior_item.options_behavior_state",
            "symbol": "alignment_item.symbol",
        },
    )


def _extract_regime_context(regime_source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(regime_source, Mapping):
        return {"coverage_status": "missing"}

    row = _first_mapping(regime_source, REGIME_ITEM_KEYS) or {}
    macro_regime = _normalize_regime(
        _first_clean_text(
            regime_source,
            ("macro_regime", "macro_regime_label", "policy_regime_label", "source_macro_regime_label"),
        )
        or _first_clean_text(row, ("macro_regime", "macro_regime_label", "regime_label", "policy_regime_label"))
    )
    policy_regime_label = _normalize_regime(
        _first_clean_text(regime_source, ("policy_regime_label", "macro_regime_label"))
        or _first_clean_text(row, ("policy_regime_label", "macro_regime_label", "regime_label"))
    )
    status = _clean_text(regime_source.get("status")) or "ready"
    is_ready = regime_source.get("is_ready")
    coverage_status = "ready" if status == "ready" and is_ready is not False and macro_regime else "needs_review"

    return {
        "coverage_status": coverage_status,
        "artifact_type": regime_source.get("artifact_type"),
        "macro_regime": macro_regime or "not_provided",
        "policy_regime_label": policy_regime_label or macro_regime or "not_provided",
        "weekly_planning_label": _first_clean_text(regime_source, ("weekly_planning_label",)) or _first_clean_text(row, ("weekly_planning_label",)),
        "weekly_risk_environment": _first_clean_text(regime_source, ("weekly_risk_environment",)) or _first_clean_text(row, ("risk_environment", "weekly_risk_environment")),
        "weekly_volatility_regime": _first_clean_text(regime_source, ("weekly_volatility_regime",)) or _first_clean_text(row, ("volatility_regime", "weekly_volatility_regime")),
        "weekly_liquidity_regime": _first_clean_text(regime_source, ("weekly_liquidity_regime",)) or _first_clean_text(row, ("liquidity_regime", "weekly_liquidity_regime")),
        "weekly_rates_regime": _first_clean_text(regime_source, ("weekly_rates_regime",)) or _first_clean_text(row, ("rates_regime", "weekly_rates_regime")),
        "weekly_event_risk": _first_bool(regime_source, ("weekly_event_risk", "event_risk")) if _first_bool(regime_source, ("weekly_event_risk", "event_risk")) is not None else _first_bool(row, ("event_risk", "weekly_event_risk")),
        "as_of_date": _first_clean_text(regime_source, ("as_of_date", "latest_date", "weekly_overlay_date")) or _first_clean_text(row, ("date", "as_of_date")),
    }


def _regime_options_alignment(
    *,
    macro_regime: str,
    weekly_risk_environment: str,
    weekly_volatility_regime: str,
    event_risk: bool,
    options_behavior_state: str,
    premium_bias: str,
    iv_expansion_state: str,
    gamma_state: str,
    theta_state: str,
) -> str:
    gamma_clustered = gamma_state in {"gamma_clustered", "strike_gamma_clustered", "expiration_gamma_clustered"}
    high_theta = theta_state in {"high_theta_sensitivity", "elevated_theta_sensitivity"}
    long_premium = premium_bias == "long_premium_bias" or options_behavior_state in {
        "long_premium_candidate",
        "long_premium_momentum_candidate",
        "long_gamma_candidate",
    }
    short_premium = premium_bias == "short_premium_bias" or options_behavior_state in {
        "short_premium_candidate",
        "defined_risk_short_premium_candidate",
    }
    iv_expanding = iv_expansion_state in {"iv_spike", "iv_expanding"}

    if event_risk:
        if short_premium:
            return "event_risk_requires_defined_risk_review"
        return "event_risk_supports_convexity_review"
    if macro_regime in RISK_OFF_REGIMES or weekly_risk_environment in {"risk_off", "stress", "risk_off_stress"}:
        if long_premium or iv_expanding:
            return "risk_off_supports_long_gamma_or_protection"
        if short_premium:
            return "risk_off_conflicts_with_short_premium"
        return "risk_off_requires_defensive_review"
    if macro_regime in RISK_ON_REGIMES:
        if long_premium:
            return "risk_on_supports_directional_long_premium"
        if short_premium:
            return "risk_on_allows_defined_risk_short_premium"
        return "risk_on_neutral_options_alignment"
    if macro_regime in CAUTION_REGIMES:
        if short_premium and (gamma_clustered or high_theta):
            return "caution_regime_defined_risk_short_premium_only"
        if long_premium and iv_expanding:
            return "caution_regime_long_vol_with_review"
        return "caution_regime_balanced_options_review"
    if "volatility" in weekly_volatility_regime and long_premium:
        return "volatility_regime_supports_long_vol_review"
    return "regime_options_neutral_alignment"


def _asset_options_alignment(
    *,
    asset_behavior_state: str,
    trend_behavior: str,
    relative_strength_state: str,
    volatility_behavior: str,
    drawdown_behavior: str,
    options_behavior_state: str,
    premium_bias: str,
    gamma_state: str,
) -> str:
    constructive_asset = asset_behavior_state in {"constructive", "bullish", "risk_on_confirmation"} or trend_behavior in {"uptrend", "strong_uptrend"}
    defensive_asset = asset_behavior_state in {"defensive", "bearish", "risk_off"} or trend_behavior in {"downtrend", "strong_downtrend"}
    high_vol_asset = volatility_behavior in {"high_vol", "elevated_volatility", "high_volatility"}
    deep_drawdown = drawdown_behavior in {"deep_drawdown", "severe_drawdown"}
    long_premium = premium_bias == "long_premium_bias" or options_behavior_state in {"long_premium_candidate", "long_premium_momentum_candidate", "long_gamma_candidate"}
    short_premium = premium_bias == "short_premium_bias" or options_behavior_state in {"short_premium_candidate", "defined_risk_short_premium_candidate"}
    gamma_clustered = gamma_state in {"gamma_clustered", "strike_gamma_clustered", "expiration_gamma_clustered"}

    if constructive_asset and long_premium:
        return "asset_trend_supports_directional_long_premium"
    if constructive_asset and short_premium:
        return "asset_trend_supports_defined_risk_short_premium"
    if defensive_asset and long_premium:
        return "defensive_asset_supports_long_gamma_or_put_spread_review"
    if defensive_asset and short_premium:
        return "defensive_asset_conflicts_with_short_premium"
    if high_vol_asset or deep_drawdown or gamma_clustered:
        return "asset_risk_requires_defined_risk_review"
    if relative_strength_state in {"relative_strength_leader", "strong_relative_strength"} and long_premium:
        return "relative_strength_supports_directional_convexity"
    return "asset_options_neutral_alignment"


def _strategy_family_sets(
    *,
    macro_regime: str,
    regime_options_alignment: str,
    asset_options_alignment: str,
    options_behavior_state: str,
    premium_bias: str,
    strategy_family_bias: str,
    gamma_state: str,
    theta_state: str,
    event_risk: bool,
) -> tuple[list[str], list[str], list[str]]:
    allowed: set[str] = set()
    discouraged: set[str] = set()
    blocked: set[str] = set()

    if premium_bias == "short_premium_bias" or "short_premium" in options_behavior_state or "credit_spread" in strategy_family_bias:
        allowed.update({"defined_risk_short_premium", "credit_spread"})
        discouraged.add("long_unhedged_premium")
    if premium_bias == "long_premium_bias" or "long_premium" in options_behavior_state or "long_gamma" in strategy_family_bias:
        allowed.update({"debit_spread", "long_gamma", "directional_long_premium"})
        discouraged.add("naked_short_premium")
    if "neutral" in options_behavior_state:
        allowed.update({"defined_risk_neutral", "wait_for_clearer_options_edge"})

    gamma_clustered = gamma_state in {"gamma_clustered", "strike_gamma_clustered", "expiration_gamma_clustered"}
    high_theta = theta_state in {"high_theta_sensitivity", "elevated_theta_sensitivity"}
    if gamma_clustered or high_theta or event_risk:
        allowed.add("defined_risk_only")
        blocked.add("naked_short_premium")

    if macro_regime in RISK_OFF_REGIMES or regime_options_alignment == "risk_off_conflicts_with_short_premium":
        allowed.update({"defined_risk_only", "protective_put_spread", "long_gamma"})
        blocked.add("naked_short_premium")
        discouraged.add("short_premium_without_hedge")
    if asset_options_alignment == "defensive_asset_conflicts_with_short_premium":
        blocked.add("naked_short_premium")
        discouraged.add("short_put_spread_without_strong_support")

    if not allowed:
        allowed.add("manual_review_only")

    return sorted(allowed), sorted(discouraged), sorted(blocked)


def _strategy_environment_bias(
    *,
    needs_review: bool,
    macro_regime: str,
    regime_options_alignment: str,
    asset_options_alignment: str,
    premium_bias: str,
    options_behavior_state: str,
    gamma_state: str,
) -> str:
    if needs_review:
        return "review_required"
    gamma_clustered = gamma_state in {"gamma_clustered", "strike_gamma_clustered", "expiration_gamma_clustered"}
    if macro_regime in RISK_OFF_REGIMES and gamma_clustered:
        return "defensive_defined_risk_only_environment"
    if regime_options_alignment == "risk_off_supports_long_gamma_or_protection":
        return "protective_long_gamma_environment"
    if premium_bias == "short_premium_bias" and options_behavior_state == "defined_risk_short_premium_candidate":
        return "defined_risk_short_premium_environment"
    if premium_bias == "long_premium_bias" and asset_options_alignment in {
        "asset_trend_supports_directional_long_premium",
        "relative_strength_supports_directional_convexity",
    }:
        return "directional_long_premium_environment"
    if premium_bias == "long_premium_bias":
        return "long_premium_or_long_gamma_environment"
    if premium_bias == "short_premium_bias":
        return "short_premium_with_risk_controls_environment"
    return "balanced_options_environment"



def _matrix_dimension_summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    state_counts = Counter(str(item.get("matrix_dimension_state") or "unknown") for item in items)
    mapped_field_counts: Counter[str] = Counter()
    missing_field_counts: Counter[str] = Counter()

    for item in items:
        metadata = item.get("matrix_dimension_metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        for field in MATRIX_DIMENSION_FIELDS:
            if _has_matrix_dimension_value(metadata.get(field)):
                mapped_field_counts[field] += 1
            else:
                missing_field_counts[field] += 1

    ready_count = int(state_counts.get("ready", 0))
    needs_review_count = len(items) - ready_count
    return {
        "provider": "regime_asset_options_alignment",
        "matrix_dimension_fields": list(MATRIX_DIMENSION_FIELDS),
        "item_count": len(items),
        "ready_item_count": ready_count,
        "needs_review_item_count": needs_review_count,
        "matrix_dimension_state_counts": dict(sorted(state_counts.items())),
        "mapped_field_counts": dict(sorted(mapped_field_counts.items())),
        "missing_field_counts": dict(sorted(missing_field_counts.items())),
        "ready_to_build_exact_matrix_edge_summary": False,
        "matrix_metadata_coverage": matrix_metadata_coverage(items),
        "recommended_next_step": "patch_strategy_family_eligibility_matrix_metadata",
    }


def _missing_matrix_dimension_fields(metadata: Mapping[str, Any]) -> list[str]:
    return [field for field in MATRIX_DIMENSION_FIELDS if not _has_matrix_dimension_value(metadata.get(field))]


def _has_matrix_dimension_value(value: Any) -> bool:
    text = _clean_text(value)
    return text is not None and text not in {"not_provided", "missing", "unknown", "none", "null"}


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in items)
    regime_alignment_counts = Counter(str(item.get("regime_options_alignment") or "unknown") for item in items)
    asset_alignment_counts = Counter(str(item.get("asset_options_alignment") or "unknown") for item in items)
    environment_counts = Counter(str(item.get("strategy_environment_bias") or "unknown") for item in items)
    option_state_counts = Counter(str(item.get("options_behavior_state") or "unknown") for item in items)
    ready_count = coverage_counts.get("ready", 0)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(items),
        "ready_symbol_count": ready_count,
        "needs_review_symbol_count": len(items) - ready_count,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "regime_options_alignment_counts": dict(sorted(regime_alignment_counts.items())),
        "asset_options_alignment_counts": dict(sorted(asset_alignment_counts.items())),
        "strategy_environment_bias_counts": dict(sorted(environment_counts.items())),
        "options_behavior_state_counts": dict(sorted(option_state_counts.items())),
        "blocked_strategy_family_counts": dict(sorted(Counter(family for item in items for family in item.get("blocked_strategy_families", [])).items())),
        "allowed_strategy_family_counts": dict(sorted(Counter(family for item in items for family in item.get("allowed_strategy_families", [])).items())),
    }


def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)
    if not isinstance(source, Mapping):
        return []
    for key in keys:
        value = source.get(key)
        if _looks_like_items(value):
            return list(value)
    for parent_key in ("result", "payload", "data", "import_result"):
        parent = source.get(parent_key)
        if isinstance(parent, Mapping):
            for key in keys:
                value = parent.get(key)
                if _looks_like_items(value):
                    return list(value)
    return []


def _index_by_symbol(items: Sequence[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        symbol = _clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker", "underlying")))
        if symbol is None:
            continue
        indexed[symbol] = dict(item)
        indexed[symbol]["symbol"] = symbol
    return indexed


def _item_status(item: Mapping[str, Any] | None) -> str:
    if item is None:
        return "missing"
    status = _clean_text(_first_value(item, ("coverage_status", "status")))
    if status in {"ready", "pass", "passed"}:
        return "ready"
    if status in {"blocked", "block"}:
        return "blocked"
    if status in {"needs_review", "review_required", "warning"}:
        return "needs_review"
    if item.get("is_ready") is False or item.get("manual_review_required") is True:
        return "needs_review"
    return "ready"


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return _clean_text(source.get("artifact_type")) or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    if source is None:
        return "missing"
    return type(source).__name__


def _first_mapping(source: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any] | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _first_value(item: Mapping[str, Any] | None, keys: Sequence[str]) -> Any:
    if item is None:
        return None
    for key in keys:
        if key in item:
            value = item.get(key)
            if value is not None:
                return value
    return None


def _first_clean_text(item: Mapping[str, Any] | None, keys: Sequence[str], *, default: str | None = None) -> str | None:
    value = _first_value(item, keys)
    clean_value = _clean_text(value)
    return clean_value if clean_value is not None else default


def _first_bool(item: Mapping[str, Any] | None, keys: Sequence[str]) -> bool | None:
    value = _first_value(item, keys)
    return value if isinstance(value, bool) else None


def _normalize_regime(value: Any) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    return REGIME_ALIASES.get(text, text)


def _looks_like_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _blocked_result(blocked_reasons: Sequence[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_regime_asset_options_alignment",
        "schema_version": REGIME_ASSET_OPTIONS_ALIGNMENT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "regime_asset_options_alignment",
        "adapter_type": "regime_asset_options_alignment_builder",
        "review_scope": "policy_alignment_before_strategy_family_eligibility_not_trade_selection",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "regime_context": {"coverage_status": "missing"},
        "alignment_items": [],
        "regime_asset_options_alignment_items": [],
        "alignment_summary": {
            "covered_capabilities": list(COVERED_CAPABILITIES),
            "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
            "symbol_count": 0,
            "ready_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "coverage_status_counts": {},
            "regime_options_alignment_counts": {},
            "asset_options_alignment_counts": {},
            "strategy_environment_bias_counts": {},
            "options_behavior_state_counts": {},
            "blocked_strategy_family_counts": {},
            "allowed_strategy_family_counts": {},
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
