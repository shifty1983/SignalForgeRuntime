from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_SOURCE_REFS_KEY,
    MATRIX_METADATA_STATE_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
)


STRATEGY_FAMILY_ELIGIBILITY_SCHEMA_VERSION = "signalforge_strategy_family_eligibility.v2"

COVERED_CAPABILITIES = [
    "strategy_family_eligibility",
    "policy_aligned_strategy_family_handoff",
    "favored_allowed_discouraged_blocked_family_status",
    "ev_handoff_status_separation",
    "data_review_vs_risk_constrained_handoff",
    "strategy_family_matrix_metadata_dimension_provider",
]

DEPENDS_ON_CAPABILITIES = [
    "regime_asset_options_alignment",
]

ALIGNMENT_ITEM_KEYS = (
    "regime_asset_options_alignment_items",
    "alignment_items",
    "items",
    "data",
    "rows",
)

FAMILY_ORDER = [
    "defined_risk_short_premium",
    "credit_spread",
    "debit_spread",
    "directional_long_premium",
    "long_gamma",
    "protective_put_spread",
    "defined_risk_neutral",
    "defined_risk_only",
    "wait_for_clearer_options_edge",
    "manual_review_only",
    "long_unhedged_premium",
    "short_premium_without_hedge",
    "short_put_spread_without_strong_support",
    "naked_short_premium",
]

DATA_REVIEW_REASON_TOKENS = (
    "missing_",
    "_missing",
    "not_provided",
    "not_ready",
    "malformed",
    "invalid",
    "stale",
    "mismatch",
    "schema",
    "parse",
    "unreadable",
    "insufficient_history",
    "insufficient_observations",
)

RISK_REVIEW_REASON_TOKENS = (
    "risk",
    "caution",
    "review",
    "conflict",
    "defined_risk",
    "liquidity_or_spread",
    "liquidity",
    "spread",
    "gamma",
    "theta",
    "event",
    "drawdown",
    "volatility",
    "rates",
    "stress",
)

HARD_BLOCK_FAMILIES = {
    "naked_short_premium",
    "short_premium_without_hedge",
}

EV_READY_HANDOFF = "ready_for_expected_value_scoring"
EV_CONSTRAINED_HANDOFF = "constrained_for_expected_value_scoring"
DATA_REVIEW_HANDOFF = "data_review_required"
BLOCKED_HANDOFF = "blocked_from_expected_value_scoring"


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_strategy_family_eligibility(
    alignment_source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    """Mark strategy families and separate data blockers from EV-scoreable risk.

    This artifact interprets the regime + asset + options alignment layer. It does
    not choose a specific contract, calculate expected value, call brokers, submit
    orders, model slippage, or make automatic strategy changes.
    """

    alignment_items = _extract_items(alignment_source, ALIGNMENT_ITEM_KEYS)
    source_artifacts = {"alignment_source": _source_artifact_type(alignment_source)}

    blocked_reasons: list[str] = []
    if not alignment_items:
        blocked_reasons.append("missing_alignment_items")

    if blocked_reasons:
        return _blocked_result(blocked_reasons, source_artifacts=source_artifacts)

    items = [_build_eligibility_item(item) for item in alignment_items if isinstance(item, Mapping)]
    summary = _summary(items)
    status = "ready" if summary["data_review_symbol_count"] == 0 and summary["blocked_symbol_count"] == 0 else "needs_review"
    matrix_metadata_strategy_family_summary = summary.get("matrix_metadata_strategy_family_summary", {})

    return {
        "artifact_type": "signalforge_strategy_family_eligibility",
        "schema_version": STRATEGY_FAMILY_ELIGIBILITY_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "strategy_family_eligibility",
        "adapter_type": "strategy_family_eligibility_builder",
        "review_scope": "strategy_family_policy_eligibility_not_trade_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "expected_value_scoring",
                "priority": "high",
                "recommendation": "Score ready and constrained strategy-family candidates with expected value, risk penalties, historical evidence, and portfolio constraints before selecting a candidate.",
            }
        ],
        "strategy_family_eligibility_items": items,
        "eligibility_items": items,
        "strategy_family_eligibility_summary": summary,
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_dimension_provider": "strategy_family_eligibility",
        "matrix_dimension_fields": [
            "symbol",
            "regime_state",
            "asset_behavior_state",
            "option_behavior_state",
            "strategy_id",
            "strategy_family",
            "horizon_days",
        ],
        "matrix_metadata_strategy_family_summary": matrix_metadata_strategy_family_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_strategy_family_summary.get(
            "exact_matrix_cell_ready_record_count", 0
        ),
        "matrix_metadata_needs_review_record_count": matrix_metadata_strategy_family_summary.get(
            "needs_review_record_count", 0
        ),
        "ready_to_patch_historical_replay_exports": True,
        "ready_to_build_exact_matrix_edge_summary": bool(
            matrix_metadata_strategy_family_summary.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "recommended_next_step": (
            "patch_options_strategy_setup_matcher_matrix_metadata"
            if matrix_metadata_strategy_family_summary.get("ready_to_build_exact_matrix_edge_summary")
            else "patch_options_strategy_setup_matcher_matrix_metadata"
        ),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_eligibility_item(alignment_item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(alignment_item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"

    alignment_status = _clean_text(_first_value(alignment_item, ("coverage_status", "status"))) or "needs_review"
    strategy_environment_bias = _clean_text(alignment_item.get("strategy_environment_bias")) or "review_required"
    strategy_selection_handoff = _clean_text(alignment_item.get("strategy_selection_handoff")) or "review_required"
    source_review_reasons = list(_as_string_list(alignment_item.get("needs_review_reasons")))

    allowed_from_alignment = set(_as_string_list(alignment_item.get("allowed_strategy_families")))
    discouraged_from_alignment = set(_as_string_list(alignment_item.get("discouraged_strategy_families")))
    blocked_from_alignment = set(_as_string_list(alignment_item.get("blocked_strategy_families")))

    data_review_reasons = _data_review_reasons(
        alignment_status=alignment_status,
        strategy_environment_bias=strategy_environment_bias,
        strategy_selection_handoff=strategy_selection_handoff,
        source_review_reasons=source_review_reasons,
        allowed_from_alignment=allowed_from_alignment,
    )
    risk_review_reasons = _risk_review_reasons(
        alignment_item=alignment_item,
        alignment_status=alignment_status,
        strategy_environment_bias=strategy_environment_bias,
        strategy_selection_handoff=strategy_selection_handoff,
        source_review_reasons=source_review_reasons,
        allowed_from_alignment=allowed_from_alignment,
        discouraged_from_alignment=discouraged_from_alignment,
        blocked_from_alignment=blocked_from_alignment,
    )

    favored = _favored_families(
        strategy_environment_bias=strategy_environment_bias,
        premium_bias=_clean_text(alignment_item.get("premium_bias")) or "not_provided",
        options_behavior_state=_clean_text(alignment_item.get("options_behavior_state")) or "not_provided",
        regime_options_alignment=_clean_text(alignment_item.get("regime_options_alignment")) or "not_provided",
        asset_options_alignment=_clean_text(alignment_item.get("asset_options_alignment")) or "not_provided",
        allowed_from_alignment=allowed_from_alignment,
    )

    allowed = set(allowed_from_alignment) | favored
    discouraged = set(discouraged_from_alignment)
    blocked = set(blocked_from_alignment)

    hard_block_reasons: list[str] = []
    if data_review_reasons:
        allowed = {"manual_review_only"}
        favored = set()
        discouraged = set()
        blocked = set(blocked_from_alignment)
    elif not allowed or allowed == {"manual_review_only"}:
        hard_block_reasons.append("no_ev_eligible_strategy_family")
        allowed = {"manual_review_only"}
        favored = set()
        discouraged = set()

    # Hard safety overrides: these are never eligible from this layer.
    if "naked_short_premium" in allowed:
        allowed.discard("naked_short_premium")
        blocked.add("naked_short_premium")
        risk_review_reasons.append("naked_short_premium_blocked_by_policy")
    if "defined_risk_only" in allowed:
        for family in HARD_BLOCK_FAMILIES:
            blocked.add(family)
        risk_review_reasons.append("defined_risk_only_constraint")

    ev_handoff = _ev_handoff(
        data_review_reasons=data_review_reasons,
        hard_block_reasons=hard_block_reasons,
        risk_review_reasons=risk_review_reasons,
    )
    coverage_status = _coverage_status_from_handoff(ev_handoff)

    family_statuses = _family_statuses(
        favored=favored,
        allowed=allowed,
        discouraged=discouraged,
        blocked=blocked,
        coverage_status=coverage_status,
    )
    matrix_dimension_metadata = _matrix_dimension_metadata_from_alignment(
        alignment_item,
        symbol=symbol,
    )
    strategy_family_matrix_metadata_items = _strategy_family_matrix_metadata_items(
        symbol=symbol,
        matrix_dimension_metadata=matrix_dimension_metadata,
        family_statuses=family_statuses,
        coverage_status=coverage_status,
        ev_handoff=ev_handoff,
    )
    matrix_metadata_strategy_family_summary = matrix_metadata_coverage(
        strategy_family_matrix_metadata_items
    )

    risk_flags = sorted(set(risk_review_reasons))
    constraint_flags = _constraint_flags(
        allowed=allowed,
        blocked=blocked,
        risk_flags=risk_flags,
        discouraged=discouraged,
    )
    all_review_reasons = sorted(set(source_review_reasons + data_review_reasons + risk_review_reasons + hard_block_reasons))

    return {
        "artifact_type": "strategy_family_eligibility_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "manual_review_required": coverage_status in {"constrained", "data_review_required", "blocked"},
        "ev_eligible": ev_handoff in {EV_READY_HANDOFF, EV_CONSTRAINED_HANDOFF},
        "risk_adjustment_required": ev_handoff == EV_CONSTRAINED_HANDOFF,
        "data_review_required": ev_handoff == DATA_REVIEW_HANDOFF,
        "hard_blocked": ev_handoff == BLOCKED_HANDOFF,
        "expected_value_handoff_status": ev_handoff,
        "macro_regime": alignment_item.get("macro_regime"),
        "weekly_planning_label": alignment_item.get("weekly_planning_label"),
        "asset_behavior_state": alignment_item.get("asset_behavior_state"),
        "options_behavior_state": alignment_item.get("options_behavior_state"),
        "premium_bias": alignment_item.get("premium_bias"),
        "strategy_environment_bias": strategy_environment_bias,
        "regime_options_alignment": alignment_item.get("regime_options_alignment"),
        "asset_options_alignment": alignment_item.get("asset_options_alignment"),
        "favored_strategy_families": _ordered(favored),
        "allowed_strategy_families": _ordered(allowed),
        "discouraged_strategy_families": _ordered(discouraged),
        "blocked_strategy_families": _ordered(blocked),
        "review_required_strategy_families": ["manual_review_only"] if coverage_status in {"data_review_required", "blocked"} else [],
        "strategy_family_statuses": family_statuses,
        "strategy_family_matrix_metadata_items": strategy_family_matrix_metadata_items,
        "matrix_metadata_strategy_family_summary": matrix_metadata_strategy_family_summary,
        "matrix_dimension_provider": "strategy_family_eligibility",
        "matrix_dimension_fields": [
            "symbol",
            "regime_state",
            "asset_behavior_state",
            "option_behavior_state",
            "strategy_family",
            "strategy_id",
            "horizon_days",
        ],
        "matrix_dimension_metadata": matrix_dimension_metadata,
        "strategy_family_eligibility_handoff": ev_handoff,
        "data_review_reasons": sorted(set(data_review_reasons)),
        "risk_review_reasons": sorted(set(risk_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "risk_flags": risk_flags,
        "constraint_flags": constraint_flags,
        "needs_review_reasons": all_review_reasons,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }



def _matrix_dimension_metadata_from_alignment(
    alignment_item: Mapping[str, Any],
    *,
    symbol: str,
) -> dict[str, Any]:
    """Extract explicit matrix dimensions owned or passed through by alignment.

    This function copies explicit fields and accepted aliases only. It does not
    infer regime, behavior, strategy, or horizon values.
    """

    nested = _as_mapping(
        alignment_item.get("matrix_dimension_metadata")
        or alignment_item.get(MATRIX_METADATA_KEY)
        or alignment_item.get("matrix_metadata")
    )

    return {
        "symbol": symbol,
        "regime_state": _first_matrix_value(
            nested,
            alignment_item,
            ("regime_state", "regime", "market_regime", "regime_label", "macro_regime"),
        ),
        "asset_behavior_state": _first_matrix_value(
            nested,
            alignment_item,
            ("asset_behavior_state", "asset_behavior", "asset_behavior_label", "behavior_state"),
        ),
        "option_behavior_state": _first_matrix_value(
            nested,
            alignment_item,
            (
                "option_behavior_state",
                "option_behavior",
                "option_behavior_label",
                "options_behavior_state",
            ),
        ),
        "strategy_id": _first_matrix_value(
            nested,
            alignment_item,
            ("strategy_id", "strategy", "setup_id", "scenario_id"),
        ),
        "strategy_family": _first_matrix_value(
            nested,
            alignment_item,
            ("strategy_family", "family", "strategy_type", "variant_id"),
        ),
        "horizon_days": _first_matrix_value(
            nested,
            alignment_item,
            ("horizon_days", "horizon", "window_days", "selected_window_days", "target_horizon_days"),
        ),
        "asset_class": _first_matrix_value(
            nested,
            alignment_item,
            ("asset_class", "security_type", "instrument_type"),
        ),
        "strategy_direction": _first_matrix_value(
            nested,
            alignment_item,
            ("strategy_direction", "direction", "bias"),
        ),
        "risk_structure": _first_matrix_value(
            nested,
            alignment_item,
            ("risk_structure", "risk_profile", "defined_risk_state"),
        ),
    }


def _strategy_family_matrix_metadata_items(
    *,
    symbol: str,
    matrix_dimension_metadata: Mapping[str, Any],
    family_statuses: Mapping[str, str],
    coverage_status: str,
    ev_handoff: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    base_metadata = dict(matrix_dimension_metadata)

    for family, family_status in family_statuses.items():
        if family_status == "not_applicable":
            continue

        metadata = dict(base_metadata)
        metadata["symbol"] = symbol
        metadata["strategy_family"] = family

        record = {
            "artifact_type": "strategy_family_eligibility_matrix_metadata_item",
            "symbol": symbol,
            "strategy_family": family,
            "strategy_family_status": family_status,
            "coverage_status": coverage_status,
            "strategy_family_eligibility_handoff": ev_handoff,
            "ev_eligible": ev_handoff in {EV_READY_HANDOFF, EV_CONSTRAINED_HANDOFF},
            "requires_manual_approval": True,
            "order_intent": None,
            "automatic_action": None,
            "automatic_strategy_change": None,
        }
        stamped = stamp_matrix_metadata(
            record,
            metadata,
            source_refs={
                "symbol": "strategy_family_eligibility.symbol",
                "strategy_family": "strategy_family_eligibility.strategy_family_statuses",
                "regime_state": "regime_asset_options_alignment",
                "asset_behavior_state": "regime_asset_options_alignment",
                "option_behavior_state": "regime_asset_options_alignment",
                "strategy_id": "strategy_family_eligibility_or_upstream_alignment",
                "horizon_days": "strategy_family_eligibility_or_upstream_alignment",
            },
        )
        items.append(stamped)

    return items


def _first_matrix_value(
    nested: Mapping[str, Any],
    item: Mapping[str, Any],
    keys: Sequence[str],
) -> Any:
    for key in keys:
        if key in nested and nested.get(key) is not None:
            return nested.get(key)
    return _first_value(item, keys)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _data_review_reasons(
    *,
    alignment_status: str,
    strategy_environment_bias: str,
    strategy_selection_handoff: str,
    source_review_reasons: Sequence[str],
    allowed_from_alignment: set[str],
) -> list[str]:
    reasons: list[str] = []
    for reason in source_review_reasons:
        if _is_data_review_reason(reason):
            reasons.append(reason)
    if alignment_status not in {"ready", "constrained"} and not reasons:
        if strategy_environment_bias == "review_required" or strategy_selection_handoff == "review_required":
            # If upstream only says review_required with no specific reason, keep it out of EV.
            reasons.append("alignment_review_reason_unspecified")
    if allowed_from_alignment == {"manual_review_only"} and not source_review_reasons:
        reasons.append("manual_review_only_without_ev_eligible_family")
    return sorted(set(reasons))


def _risk_review_reasons(
    *,
    alignment_item: Mapping[str, Any],
    alignment_status: str,
    strategy_environment_bias: str,
    strategy_selection_handoff: str,
    source_review_reasons: Sequence[str],
    allowed_from_alignment: set[str],
    discouraged_from_alignment: set[str],
    blocked_from_alignment: set[str],
) -> list[str]:
    reasons: list[str] = []
    for reason in source_review_reasons:
        if not _is_data_review_reason(reason) and _is_risk_review_reason(reason):
            reasons.append(reason)

    regime_options_alignment = _clean_text(alignment_item.get("regime_options_alignment")) or "not_provided"
    asset_options_alignment = _clean_text(alignment_item.get("asset_options_alignment")) or "not_provided"
    gamma_state = _clean_text(alignment_item.get("gamma_concentration_state")) or "not_provided"
    theta_state = _clean_text(alignment_item.get("theta_sensitivity_state")) or "not_provided"
    iv_expansion_state = _clean_text(alignment_item.get("iv_expansion_state")) or "not_provided"
    weekly_planning_label = _clean_text(alignment_item.get("weekly_planning_label")) or "not_provided"
    macro_regime = _clean_text(alignment_item.get("macro_regime")) or "not_provided"

    if "caution" in regime_options_alignment or "review" in regime_options_alignment:
        reasons.append(f"regime_options_alignment:{regime_options_alignment}")
    if "risk_off" in regime_options_alignment or "conflict" in regime_options_alignment:
        reasons.append(f"regime_options_alignment:{regime_options_alignment}")
    if "risk" in asset_options_alignment or "conflict" in asset_options_alignment or "defensive" in asset_options_alignment:
        reasons.append(f"asset_options_alignment:{asset_options_alignment}")
    if gamma_state in {"gamma_clustered", "strike_gamma_clustered", "expiration_gamma_clustered"}:
        reasons.append(f"gamma_concentration_state:{gamma_state}")
    if theta_state in {"high_theta_sensitivity", "elevated_theta_sensitivity"}:
        reasons.append(f"theta_sensitivity_state:{theta_state}")
    if iv_expansion_state in {"iv_spike", "iv_expanding"}:
        reasons.append(f"iv_expansion_state:{iv_expansion_state}")
    if "rates_review" in weekly_planning_label:
        reasons.append(f"weekly_planning_label:{weekly_planning_label}")
    if macro_regime in {"late_cycle_overheating", "stagflation", "credit_stress", "liquidity_stress", "deflationary_shock", "risk_off_transition"}:
        reasons.append(f"macro_regime:{macro_regime}")
    if "defined_risk_only" in allowed_from_alignment:
        reasons.append("defined_risk_only_constraint")
    if discouraged_from_alignment:
        reasons.append("discouraged_strategy_family_present")
    if blocked_from_alignment:
        reasons.append("blocked_strategy_family_present")
    if alignment_status != "ready" and not any(_is_data_review_reason(reason) for reason in source_review_reasons):
        if strategy_environment_bias == "review_required" or strategy_selection_handoff == "review_required":
            reasons.append("alignment_risk_review_required")

    return sorted(set(reasons))


def _is_data_review_reason(reason: str) -> bool:
    text = reason.lower()
    return any(token in text for token in DATA_REVIEW_REASON_TOKENS)


def _is_risk_review_reason(reason: str) -> bool:
    text = reason.lower()
    return any(token in text for token in RISK_REVIEW_REASON_TOKENS)


def _ev_handoff(
    *,
    data_review_reasons: Sequence[str],
    hard_block_reasons: Sequence[str],
    risk_review_reasons: Sequence[str],
) -> str:
    if data_review_reasons:
        return DATA_REVIEW_HANDOFF
    if hard_block_reasons:
        return BLOCKED_HANDOFF
    if risk_review_reasons:
        return EV_CONSTRAINED_HANDOFF
    return EV_READY_HANDOFF


def _coverage_status_from_handoff(handoff: str) -> str:
    if handoff == EV_READY_HANDOFF:
        return "ready"
    if handoff == EV_CONSTRAINED_HANDOFF:
        return "constrained"
    if handoff == DATA_REVIEW_HANDOFF:
        return "data_review_required"
    return "blocked"


def _constraint_flags(
    *,
    allowed: set[str],
    blocked: set[str],
    discouraged: set[str],
    risk_flags: Sequence[str],
) -> list[str]:
    flags: set[str] = set()
    if "defined_risk_only" in allowed:
        flags.add("defined_risk_only")
    if "naked_short_premium" in blocked:
        flags.add("no_naked_short_premium")
    if "short_premium_without_hedge" in blocked or "short_premium_without_hedge" in discouraged:
        flags.add("no_unhedged_short_premium")
    if "long_unhedged_premium" in discouraged:
        flags.add("discourage_long_unhedged_premium")
    for risk_flag in risk_flags:
        if "gamma" in risk_flag:
            flags.add("gamma_risk_penalty")
        if "theta" in risk_flag:
            flags.add("theta_decay_penalty")
        if "liquidity" in risk_flag or "spread" in risk_flag:
            flags.add("liquidity_penalty")
        if "macro_regime" in risk_flag or "regime" in risk_flag or "weekly_planning" in risk_flag:
            flags.add("regime_penalty")
        if "asset" in risk_flag or "drawdown" in risk_flag:
            flags.add("asset_risk_penalty")
    return sorted(flags)


def _favored_families(
    *,
    strategy_environment_bias: str,
    premium_bias: str,
    options_behavior_state: str,
    regime_options_alignment: str,
    asset_options_alignment: str,
    allowed_from_alignment: set[str],
) -> set[str]:
    favored: set[str] = set()

    if strategy_environment_bias == "defined_risk_short_premium_environment":
        favored.update({"defined_risk_short_premium", "credit_spread"})
    elif strategy_environment_bias == "short_premium_with_risk_controls_environment":
        favored.update({"defined_risk_short_premium", "credit_spread"})
    elif strategy_environment_bias == "directional_long_premium_environment":
        favored.update({"debit_spread", "directional_long_premium", "long_gamma"})
    elif strategy_environment_bias == "long_premium_or_long_gamma_environment":
        favored.update({"debit_spread", "long_gamma"})
    elif strategy_environment_bias == "protective_long_gamma_environment":
        favored.update({"long_gamma", "protective_put_spread"})
    elif strategy_environment_bias == "defensive_defined_risk_only_environment":
        favored.update({"defined_risk_only", "protective_put_spread"})
    elif strategy_environment_bias == "balanced_options_environment":
        favored.update(set())

    if not favored:
        if premium_bias == "short_premium_bias" or "short_premium" in options_behavior_state:
            favored.update({"defined_risk_short_premium", "credit_spread"})
        elif premium_bias == "long_premium_bias" or "long_premium" in options_behavior_state or "long_gamma" in options_behavior_state:
            favored.update({"debit_spread", "long_gamma"})

    if regime_options_alignment == "risk_off_supports_long_gamma_or_protection":
        favored.update({"long_gamma", "protective_put_spread"})
    if asset_options_alignment == "asset_trend_supports_directional_long_premium":
        favored.update({"debit_spread", "directional_long_premium"})
    if asset_options_alignment == "asset_trend_supports_defined_risk_short_premium":
        favored.update({"defined_risk_short_premium", "credit_spread"})

    if allowed_from_alignment:
        favored &= allowed_from_alignment
    return favored


def _family_statuses(
    *,
    favored: set[str],
    allowed: set[str],
    discouraged: set[str],
    blocked: set[str],
    coverage_status: str,
) -> dict[str, str]:
    all_families = set(FAMILY_ORDER) | favored | allowed | discouraged | blocked
    statuses: dict[str, str] = {}
    for family in _ordered(all_families):
        if family in blocked:
            statuses[family] = "blocked"
        elif coverage_status in {"data_review_required", "blocked"}:
            statuses[family] = "review_required"
        elif family in favored:
            statuses[family] = "favored_constrained" if coverage_status == "constrained" else "favored"
        elif family in allowed:
            statuses[family] = "allowed_constrained" if coverage_status == "constrained" else "allowed"
        elif family in discouraged:
            statuses[family] = "discouraged"
        else:
            statuses[family] = "not_applicable"
    return statuses


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in items)
    ready_count = coverage_counts.get("ready", 0)
    constrained_count = coverage_counts.get("constrained", 0)
    data_review_count = coverage_counts.get("data_review_required", 0)
    blocked_count = coverage_counts.get("blocked", 0)
    ev_eligible_count = sum(1 for item in items if item.get("ev_eligible") is True)
    risk_adjusted_count = sum(1 for item in items if item.get("risk_adjustment_required") is True)
    environment_counts = Counter(str(item.get("strategy_environment_bias") or "unknown") for item in items)
    favored_counts = Counter(family for item in items for family in item.get("favored_strategy_families", []))
    allowed_counts = Counter(family for item in items for family in item.get("allowed_strategy_families", []))
    discouraged_counts = Counter(family for item in items for family in item.get("discouraged_strategy_families", []))
    blocked_family_counts = Counter(family for item in items for family in item.get("blocked_strategy_families", []))
    handoff_counts = Counter(str(item.get("strategy_family_eligibility_handoff") or "unknown") for item in items)
    constraint_counts = Counter(flag for item in items for flag in item.get("constraint_flags", []))
    risk_flag_counts = Counter(flag for item in items for flag in item.get("risk_flags", []))
    data_reason_counts = Counter(reason for item in items for reason in item.get("data_review_reasons", []))
    matrix_metadata_items = [
        matrix_item
        for item in items
        for matrix_item in item.get("strategy_family_matrix_metadata_items", [])
        if isinstance(matrix_item, Mapping)
    ]
    matrix_metadata_strategy_family_summary = matrix_metadata_coverage(matrix_metadata_items)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(items),
        "ready_symbol_count": ready_count,
        "constrained_symbol_count": constrained_count,
        "ev_eligible_symbol_count": ev_eligible_count,
        "risk_adjusted_ev_symbol_count": risk_adjusted_count,
        "data_review_symbol_count": data_review_count,
        "blocked_symbol_count": blocked_count,
        "needs_review_symbol_count": data_review_count + blocked_count,
        "manual_review_symbol_count": constrained_count + data_review_count + blocked_count,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "strategy_environment_bias_counts": dict(sorted(environment_counts.items())),
        "favored_strategy_family_counts": dict(sorted(favored_counts.items())),
        "allowed_strategy_family_counts": dict(sorted(allowed_counts.items())),
        "discouraged_strategy_family_counts": dict(sorted(discouraged_counts.items())),
        "blocked_strategy_family_counts": dict(sorted(blocked_family_counts.items())),
        "handoff_counts": dict(sorted(handoff_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_strategy_family_summary": matrix_metadata_strategy_family_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_strategy_family_summary.get(
            "exact_matrix_cell_ready_record_count", 0
        ),
        "matrix_metadata_needs_review_record_count": matrix_metadata_strategy_family_summary.get(
            "needs_review_record_count", 0
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            matrix_metadata_strategy_family_summary.get("ready_to_build_exact_matrix_edge_summary")
        ),
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


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return _clean_text(source.get("artifact_type")) or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    if source is None:
        return "missing"
    return type(source).__name__


def _looks_like_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _first_value(item: Mapping[str, Any] | None, keys: Sequence[str]) -> Any:
    if item is None:
        return None
    for key in keys:
        if key in item:
            value = item.get(key)
            if value is not None:
                return value
    return None


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [clean for entry in value if (clean := _clean_text(entry))]
    clean = _clean_text(value)
    return [clean] if clean else []


def _ordered(values: set[str]) -> list[str]:
    order = {name: index for index, name in enumerate(FAMILY_ORDER)}
    return sorted(values, key=lambda value: (order.get(value, 999), value))


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
        "artifact_type": "signalforge_strategy_family_eligibility",
        "schema_version": STRATEGY_FAMILY_ELIGIBILITY_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "strategy_family_eligibility",
        "adapter_type": "strategy_family_eligibility_builder",
        "review_scope": "strategy_family_policy_eligibility_not_trade_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "strategy_family_eligibility_items": [],
        "eligibility_items": [],
        "strategy_family_eligibility_summary": {
            "covered_capabilities": list(COVERED_CAPABILITIES),
            "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
            "symbol_count": 0,
            "ready_symbol_count": 0,
            "constrained_symbol_count": 0,
            "ev_eligible_symbol_count": 0,
            "risk_adjusted_ev_symbol_count": 0,
            "data_review_symbol_count": 0,
            "blocked_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "manual_review_symbol_count": 0,
            "coverage_status_counts": {},
            "strategy_environment_bias_counts": {},
            "favored_strategy_family_counts": {},
            "allowed_strategy_family_counts": {},
            "discouraged_strategy_family_counts": {},
            "blocked_strategy_family_counts": {},
            "handoff_counts": {},
            "constraint_flag_counts": {},
            "risk_flag_counts": {},
            "data_review_reason_counts": {},
            "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
            "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
            "matrix_metadata_strategy_family_summary": matrix_metadata_coverage([]),
            "exact_matrix_cell_ready_record_count": 0,
            "matrix_metadata_needs_review_record_count": 0,
            "ready_to_build_exact_matrix_edge_summary": False,
        },
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_dimension_provider": "strategy_family_eligibility",
        "matrix_dimension_fields": [
            "symbol",
            "regime_state",
            "asset_behavior_state",
            "option_behavior_state",
            "strategy_id",
            "strategy_family",
            "horizon_days",
        ],
        "matrix_metadata_strategy_family_summary": matrix_metadata_coverage([]),
        "exact_matrix_cell_ready_record_count": 0,
        "matrix_metadata_needs_review_record_count": 0,
        "ready_to_patch_historical_replay_exports": False,
        "ready_to_build_exact_matrix_edge_summary": False,
        "recommended_next_step": "provide_alignment_items_before_matrix_metadata_stamping",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
