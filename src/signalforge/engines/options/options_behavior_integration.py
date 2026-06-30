from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTIONS_BEHAVIOR_INTEGRATION_SCHEMA_VERSION = "signalforge_options_behavior_integration.v1"

CORE_CAPABILITIES = [
    "iv_rank_percentile",
    "iv_expansion_contraction",
    "volatility_risk_premium",
    "gamma_concentration",
    "theta_sensitivity",
]

SUPPLEMENTAL_CAPABILITIES = [
    "skew_behavior",
    "term_structure_behavior",
    "liquidity_state",
    "spread_width",
    "open_interest_behavior",
    "volume_behavior",
    "delta_availability",
    "vega_sensitivity",
]

COVERED_CAPABILITIES = [
    "options_behavior_integration",
    *CORE_CAPABILITIES,
    *SUPPLEMENTAL_CAPABILITIES,
]

ITEM_KEYS_BY_SOURCE = {
    "iv_history": (
        "option_iv_history_items",
        "iv_history_items",
        "items",
        "data",
        "rows",
    ),
    "iv_expansion": (
        "option_iv_expansion_items",
        "iv_expansion_items",
        "items",
        "data",
        "rows",
    ),
    "volatility_risk_premium": (
        "option_volatility_risk_premium_items",
        "volatility_risk_premium_items",
        "items",
        "data",
        "rows",
    ),
    "gamma_concentration": (
        "option_gamma_concentration_items",
        "gamma_concentration_items",
        "items",
        "data",
        "rows",
    ),
    "theta_sensitivity": (
        "option_theta_sensitivity_items",
        "theta_sensitivity_items",
        "items",
        "data",
        "rows",
    ),
    "source_readiness": (
        "option_behavior_source_readiness_items",
        "source_readiness_items",
        "items",
        "data",
        "rows",
    ),
    "supplemental_options": (
        "options_behavior_items",
        "option_behavior_items",
        "option_analytics_items",
        "items",
        "data",
        "rows",
    ),
}


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_options_behavior_integration(
    *,
    iv_history_source: Mapping[str, Any] | Sequence[Any] | None,
    iv_expansion_source: Mapping[str, Any] | Sequence[Any] | None,
    volatility_risk_premium_source: Mapping[str, Any] | Sequence[Any] | None,
    gamma_concentration_source: Mapping[str, Any] | Sequence[Any] | None,
    theta_sensitivity_source: Mapping[str, Any] | Sequence[Any] | None,
    source_readiness_source: Mapping[str, Any] | Sequence[Any] | None = None,
    supplemental_options_source: Mapping[str, Any] | Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Merge per-symbol options analytics into one Options Behavior artifact.

    This artifact is the clean handoff from Options Behavior into regime/asset
    alignment and strategy-family eligibility. It combines already-derived,
    compact behavior artifacts. It does not request broker data, route orders,
    submit trades, or export raw option chains.
    """

    sources = {
        "iv_history": iv_history_source,
        "iv_expansion": iv_expansion_source,
        "volatility_risk_premium": volatility_risk_premium_source,
        "gamma_concentration": gamma_concentration_source,
        "theta_sensitivity": theta_sensitivity_source,
        "source_readiness": source_readiness_source,
        "supplemental_options": supplemental_options_source,
    }

    extracted = {
        name: _index_by_symbol(_extract_items(source, ITEM_KEYS_BY_SOURCE[name]))
        for name, source in sources.items()
    }

    missing_core_sources = [
        name for name in CORE_SOURCE_NAMES if not extracted[name]
    ]
    if missing_core_sources:
        return _blocked_result(
            "missing core options behavior source items",
            missing_core_sources=missing_core_sources,
            source_artifacts=_source_artifacts(sources),
        )

    symbols = sorted(
        {
            symbol
            for name in CORE_SOURCE_NAMES
            for symbol in extracted[name]
            if symbol
        }
    )
    if not symbols:
        return _blocked_result(
            "no symbols found in core options behavior sources",
            source_artifacts=_source_artifacts(sources),
        )

    items = [
        _build_integration_item(
            symbol=symbol,
            iv_item=extracted["iv_history"].get(symbol),
            expansion_item=extracted["iv_expansion"].get(symbol),
            premium_item=extracted["volatility_risk_premium"].get(symbol),
            gamma_item=extracted["gamma_concentration"].get(symbol),
            theta_item=extracted["theta_sensitivity"].get(symbol),
            readiness_item=extracted["source_readiness"].get(symbol),
            supplemental_item=extracted["supplemental_options"].get(symbol),
        )
        for symbol in symbols
    ]

    summary = _summary(items)
    status = "ready" if summary["needs_review_symbol_count"] == 0 else "needs_review"

    return {
        "artifact_type": "signalforge_options_behavior_integration",
        "schema_version": OPTIONS_BEHAVIOR_INTEGRATION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "options_behavior_integration",
        "adapter_type": "options_behavior_integration_builder",
        "review_scope": "unified_options_behavior_handoff_not_strategy_selection_or_order_execution",
        "source_artifacts": _source_artifacts(sources),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "core_capabilities": list(CORE_CAPABILITIES),
        "supplemental_capabilities": list(SUPPLEMENTAL_CAPABILITIES),
        "depends_on_capabilities": [
            "iv_rank_percentile",
            "iv_expansion_contraction",
            "volatility_risk_premium",
            "gamma_concentration",
            "theta_sensitivity",
            "option_source_readiness",
            "skew_behavior",
            "term_structure_behavior",
            "liquidity_state",
        ],
        "next_build_recommendations": [
            {
                "capability": "regime_asset_options_alignment",
                "priority": "high",
                "recommendation": "Combine macro regime, asset behavior, and unified Options Behavior into a policy-alignment artifact before strategy-family eligibility.",
            }
        ],
        "options_behavior_items": items,
        "options_behavior_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


CORE_SOURCE_NAMES = (
    "iv_history",
    "iv_expansion",
    "volatility_risk_premium",
    "gamma_concentration",
    "theta_sensitivity",
)


def _build_integration_item(
    *,
    symbol: str,
    iv_item: Mapping[str, Any] | None,
    expansion_item: Mapping[str, Any] | None,
    premium_item: Mapping[str, Any] | None,
    gamma_item: Mapping[str, Any] | None,
    theta_item: Mapping[str, Any] | None,
    readiness_item: Mapping[str, Any] | None,
    supplemental_item: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_statuses = {
        "iv_history": _item_status(iv_item),
        "iv_expansion": _item_status(expansion_item),
        "volatility_risk_premium": _item_status(premium_item),
        "gamma_concentration": _item_status(gamma_item),
        "theta_sensitivity": _item_status(theta_item),
        "source_readiness": _item_status(readiness_item, optional=True),
        "supplemental_options": _item_status(supplemental_item, optional=True),
    }
    missing_core_inputs = [
        name for name in CORE_SOURCE_NAMES if source_statuses[name] == "missing"
    ]
    non_ready_core_inputs = [
        name for name in CORE_SOURCE_NAMES if source_statuses[name] not in {"ready"}
    ]

    iv_rank_state = _first_clean_text(
        iv_item,
        ("iv_rank_state", "iv_rank_label"),
        default="not_provided",
    )
    iv_percentile_state = _first_clean_text(
        iv_item,
        ("iv_percentile_state", "iv_percentile_label"),
        default="not_provided",
    )
    current_iv = _first_number(
        iv_item,
        ("current_implied_volatility", "implied_volatility", "current_iv", "atm_iv"),
    )

    iv_expansion_state = _first_clean_text(
        expansion_item,
        ("iv_expansion_state", "iv_trend_state"),
        default="not_provided",
    )

    volatility_risk_premium_state = _first_clean_text(
        premium_item,
        ("volatility_risk_premium_state", "iv_vs_rv_state"),
        default="not_provided",
    )
    premium_bias = _first_clean_text(
        premium_item,
        ("premium_bias",),
        default="not_provided",
    )
    strategy_family_bias = _first_clean_text(
        premium_item,
        ("strategy_family_bias",),
        default="not_provided",
    )

    gamma_state = _first_clean_text(
        gamma_item,
        ("gamma_concentration_state", "gamma_state"),
        default="not_provided",
    )
    theta_state = _first_clean_text(
        theta_item,
        ("theta_sensitivity_state", "theta_state"),
        default="not_provided",
    )

    liquidity_state = _supplemental_or_readiness_state(
        supplemental_item=supplemental_item,
        readiness_item=readiness_item,
        supplemental_keys=("liquidity_state", "liquidity_regime"),
        readiness_gate_key="option_source_gate",
        ready_label="liquidity_source_ready",
        review_label="liquidity_needs_review",
    )
    spread_state = _supplemental_or_readiness_state(
        supplemental_item=supplemental_item,
        readiness_item=readiness_item,
        supplemental_keys=("spread_state", "spread_width", "spread_width_state"),
        readiness_gate_key="execution_quote_gate",
        ready_label="acceptable_spread_or_bid_ask_available",
        review_label="spread_needs_review",
    )

    delta_availability = _boolean_availability(
        supplemental_item=supplemental_item,
        readiness_item=readiness_item,
        supplemental_keys=("delta_availability", "delta_state"),
        readiness_bool_key="has_delta",
        available_label="usable_delta_available",
        missing_label="missing_delta",
    )
    vega_sensitivity = _boolean_availability(
        supplemental_item=supplemental_item,
        readiness_item=readiness_item,
        supplemental_keys=("vega_sensitivity", "vega_state"),
        readiness_bool_key="has_vega",
        available_label="usable_vega_available",
        missing_label="missing_vega",
    )

    open_interest_behavior = _first_clean_text(
        supplemental_item,
        ("open_interest_behavior", "open_interest_state", "oi_state"),
        default="covered_by_option_source" if readiness_item is not None else "not_provided",
    )
    volume_behavior = _first_clean_text(
        supplemental_item,
        ("volume_behavior", "volume_state"),
        default="covered_by_option_source" if readiness_item is not None else "not_provided",
    )
    skew_state = _first_clean_text(
        supplemental_item,
        ("skew_state", "skew_behavior", "put_call_skew_state"),
        default="not_provided",
    )
    term_structure_state = _first_clean_text(
        supplemental_item,
        ("term_structure_state", "term_structure_behavior"),
        default="not_provided",
    )

    coverage_status, readiness_reasons = _coverage_status(
        source_statuses=source_statuses,
        missing_core_inputs=missing_core_inputs,
        non_ready_core_inputs=non_ready_core_inputs,
        readiness_item=readiness_item,
    )
    options_behavior_state, options_behavior_reasons = _options_behavior_state(
        coverage_status=coverage_status,
        premium_bias=premium_bias,
        strategy_family_bias=strategy_family_bias,
        volatility_risk_premium_state=volatility_risk_premium_state,
        iv_expansion_state=iv_expansion_state,
        gamma_state=gamma_state,
        theta_state=theta_state,
        liquidity_state=liquidity_state,
        spread_state=spread_state,
    )

    return {
        "artifact_type": "options_behavior_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "options_behavior_state": options_behavior_state,
        "options_behavior_reasons": options_behavior_reasons,
        "readiness_reasons": readiness_reasons,
        "source_statuses": source_statuses,
        "missing_core_inputs": missing_core_inputs,
        "iv_rank_state": iv_rank_state,
        "iv_percentile_state": iv_percentile_state,
        "current_implied_volatility": _round(current_iv),
        "iv_expansion_state": iv_expansion_state,
        "volatility_risk_premium_state": volatility_risk_premium_state,
        "premium_bias": premium_bias,
        "strategy_family_bias": strategy_family_bias,
        "gamma_concentration_state": gamma_state,
        "dominant_gamma_strike": _first_value(gamma_item, ("dominant_strike",)),
        "dominant_gamma_expiration": _first_value(gamma_item, ("dominant_expiration",)),
        "theta_sensitivity_state": theta_state,
        "theta_direction_bias": _first_clean_text(theta_item, ("theta_direction_bias",), default="not_provided"),
        "liquidity_state": liquidity_state,
        "spread_state": spread_state,
        "open_interest_behavior": open_interest_behavior,
        "volume_behavior": volume_behavior,
        "delta_availability": delta_availability,
        "vega_sensitivity": vega_sensitivity,
        "skew_state": skew_state,
        "term_structure_state": term_structure_state,
        "option_source_gate": _first_clean_text(readiness_item, ("option_source_gate",), default="not_provided"),
        "execution_quote_gate": _first_clean_text(readiness_item, ("execution_quote_gate",), default="not_provided"),
        "strategy_selection_handoff": _strategy_selection_handoff(
            coverage_status=coverage_status,
            options_behavior_state=options_behavior_state,
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


def _coverage_status(
    *,
    source_statuses: Mapping[str, str],
    missing_core_inputs: Sequence[str],
    non_ready_core_inputs: Sequence[str],
    readiness_item: Mapping[str, Any] | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if missing_core_inputs:
        reasons.extend([f"missing_{name}" for name in missing_core_inputs])
    if non_ready_core_inputs:
        reasons.extend([f"non_ready_{name}" for name in non_ready_core_inputs])

    if readiness_item is not None:
        option_gate = _clean_text(readiness_item.get("option_source_gate"))
        quote_gate = _clean_text(readiness_item.get("execution_quote_gate"))
        if option_gate == "blocked":
            reasons.append("option_source_gate_blocked")
        elif option_gate == "review_required":
            reasons.append("option_source_gate_review_required")
        if quote_gate == "blocked":
            reasons.append("execution_quote_gate_blocked")
        elif quote_gate == "review_required":
            reasons.append("execution_quote_gate_review_required")

    return ("ready" if not reasons else "needs_review", reasons)


def _options_behavior_state(
    *,
    coverage_status: str,
    premium_bias: str,
    strategy_family_bias: str,
    volatility_risk_premium_state: str,
    iv_expansion_state: str,
    gamma_state: str,
    theta_state: str,
    liquidity_state: str,
    spread_state: str,
) -> tuple[str, list[str]]:
    if coverage_status != "ready":
        return "options_behavior_needs_review", ["one_or_more_inputs_need_review"]

    reasons: list[str] = []
    liquidity_review = liquidity_state.endswith("needs_review") or spread_state.endswith("needs_review")
    if liquidity_review:
        reasons.append("liquidity_or_spread_needs_review")

    gamma_clustered = gamma_state in {
        "gamma_clustered",
        "strike_gamma_clustered",
        "expiration_gamma_clustered",
    }
    theta_high = theta_state in {"high_theta_sensitivity", "elevated_theta_sensitivity"}
    iv_expanding = iv_expansion_state in {"iv_spike", "iv_expanding"}
    iv_contracting = iv_expansion_state in {"iv_crush", "iv_contracting"}

    if premium_bias == "short_premium_bias":
        reasons.append("iv_rich_or_short_premium_bias")
        if gamma_clustered or theta_high:
            reasons.append("defined_risk_preferred_due_to_gamma_or_theta")
            return "defined_risk_short_premium_candidate", reasons
        return "short_premium_candidate", reasons

    if premium_bias == "long_premium_bias":
        reasons.append("iv_cheap_or_long_premium_bias")
        if iv_expanding:
            reasons.append("iv_expansion_supports_long_premium")
            return "long_premium_momentum_candidate", reasons
        if gamma_clustered:
            reasons.append("gamma_cluster_supports_long_gamma_review")
            return "long_gamma_candidate", reasons
        return "long_premium_candidate", reasons

    if volatility_risk_premium_state == "iv_fair_vs_realized":
        reasons.append("iv_fair_vs_realized")
        if iv_expanding:
            return "neutral_to_long_vol_candidate", reasons
        if iv_contracting:
            return "neutral_to_short_vol_candidate", reasons
        return "neutral_options_behavior", reasons

    if strategy_family_bias not in {"not_provided", "needs_review"}:
        reasons.append("strategy_family_bias_available")
        return "strategy_bias_available", reasons

    return "neutral_options_behavior", ["no_strong_options_behavior_bias"]


def _strategy_selection_handoff(*, coverage_status: str, options_behavior_state: str) -> str:
    if coverage_status != "ready":
        return "review_required"
    if options_behavior_state in {
        "defined_risk_short_premium_candidate",
        "short_premium_candidate",
        "long_premium_momentum_candidate",
        "long_gamma_candidate",
        "long_premium_candidate",
        "neutral_to_long_vol_candidate",
        "neutral_to_short_vol_candidate",
        "neutral_options_behavior",
        "strategy_bias_available",
    }:
        return "ready_for_regime_asset_options_alignment"
    return "review_required"


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in items)
    state_counts = Counter(str(item.get("options_behavior_state") or "unknown") for item in items)
    premium_bias_counts = Counter(str(item.get("premium_bias") or "unknown") for item in items)
    strategy_family_bias_counts = Counter(str(item.get("strategy_family_bias") or "unknown") for item in items)
    gamma_counts = Counter(str(item.get("gamma_concentration_state") or "unknown") for item in items)
    theta_counts = Counter(str(item.get("theta_sensitivity_state") or "unknown") for item in items)
    iv_expansion_counts = Counter(str(item.get("iv_expansion_state") or "unknown") for item in items)
    missing_core_count = sum(1 for item in items if item.get("missing_core_inputs"))
    ready_count = coverage_counts.get("ready", 0)
    needs_review_count = len(items) - ready_count

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "core_capabilities": list(CORE_CAPABILITIES),
        "supplemental_capabilities": list(SUPPLEMENTAL_CAPABILITIES),
        "symbol_count": len(items),
        "ready_symbol_count": ready_count,
        "needs_review_symbol_count": needs_review_count,
        "missing_core_input_symbol_count": missing_core_count,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "options_behavior_state_counts": dict(sorted(state_counts.items())),
        "premium_bias_counts": dict(sorted(premium_bias_counts.items())),
        "strategy_family_bias_counts": dict(sorted(strategy_family_bias_counts.items())),
        "iv_expansion_state_counts": dict(sorted(iv_expansion_counts.items())),
        "gamma_concentration_state_counts": dict(sorted(gamma_counts.items())),
        "theta_sensitivity_state_counts": dict(sorted(theta_counts.items())),
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


def _item_status(item: Mapping[str, Any] | None, *, optional: bool = False) -> str:
    if item is None:
        return "optional_missing" if optional else "missing"
    status = _clean_text(_first_value(item, ("coverage_status", "status", "option_source_gate")))
    if status in {"ready", "pass", "passed"}:
        return "ready"
    if status in {"blocked", "block"}:
        return "blocked"
    if status in {"needs_review", "review_required", "warning"}:
        return "needs_review"
    manual_review_required = item.get("manual_review_required")
    if manual_review_required is True:
        return "needs_review"
    return "ready"


def _source_artifacts(sources: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: _source_artifact_type(source)
        for name, source in sources.items()
        if source is not None
    }


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return _clean_text(source.get("artifact_type")) or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    if source is None:
        return "missing"
    return type(source).__name__


def _supplemental_or_readiness_state(
    *,
    supplemental_item: Mapping[str, Any] | None,
    readiness_item: Mapping[str, Any] | None,
    supplemental_keys: Sequence[str],
    readiness_gate_key: str,
    ready_label: str,
    review_label: str,
) -> str:
    supplemental_value = _first_clean_text(supplemental_item, supplemental_keys)
    if supplemental_value is not None:
        return supplemental_value
    if readiness_item is None:
        return "not_provided"
    gate = _clean_text(readiness_item.get(readiness_gate_key))
    if gate == "ready":
        return ready_label
    if gate in {"review_required", "blocked"}:
        return review_label
    return "not_provided"


def _boolean_availability(
    *,
    supplemental_item: Mapping[str, Any] | None,
    readiness_item: Mapping[str, Any] | None,
    supplemental_keys: Sequence[str],
    readiness_bool_key: str,
    available_label: str,
    missing_label: str,
) -> str:
    supplemental_value = _first_clean_text(supplemental_item, supplemental_keys)
    if supplemental_value is not None:
        return supplemental_value
    if readiness_item is None:
        return "not_provided"
    value = readiness_item.get(readiness_bool_key)
    if value is True:
        return available_label
    if value is False:
        return missing_label
    return "not_provided"


def _first_value(item: Mapping[str, Any] | None, keys: Sequence[str]) -> Any:
    if item is None:
        return None
    for key in keys:
        if key in item:
            value = item.get(key)
            if value is not None:
                return value
    return None


def _first_clean_text(
    item: Mapping[str, Any] | None,
    keys: Sequence[str],
    *,
    default: str | None = None,
) -> str | None:
    value = _first_value(item, keys)
    clean_value = _clean_text(value)
    return clean_value if clean_value is not None else default


def _first_number(item: Mapping[str, Any] | None, keys: Sequence[str]) -> float | None:
    return _clean_float(_first_value(item, keys))


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


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _blocked_result(
    reason: str,
    *,
    missing_core_sources: Sequence[str] | None = None,
    source_artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_options_behavior_integration",
        "schema_version": OPTIONS_BEHAVIOR_INTEGRATION_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "options_behavior_integration",
        "adapter_type": "options_behavior_integration_builder",
        "review_scope": "unified_options_behavior_handoff_not_strategy_selection_or_order_execution",
        "source_artifacts": dict(source_artifacts or {}),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "core_capabilities": list(CORE_CAPABILITIES),
        "supplemental_capabilities": list(SUPPLEMENTAL_CAPABILITIES),
        "blocked_reasons": [reason],
        "missing_core_sources": list(missing_core_sources or []),
        "options_behavior_items": [],
        "options_behavior_summary": {
            "covered_capabilities": list(COVERED_CAPABILITIES),
            "core_capabilities": list(CORE_CAPABILITIES),
            "supplemental_capabilities": list(SUPPLEMENTAL_CAPABILITIES),
            "symbol_count": 0,
            "ready_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "missing_core_input_symbol_count": 0,
            "coverage_status_counts": {},
            "options_behavior_state_counts": {},
            "premium_bias_counts": {},
            "strategy_family_bias_counts": {},
            "iv_expansion_state_counts": {},
            "gamma_concentration_state_counts": {},
            "theta_sensitivity_state_counts": {},
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }




