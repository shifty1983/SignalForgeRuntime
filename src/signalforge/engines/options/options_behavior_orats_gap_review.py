from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_SCHEMA_VERSION = (
    "signalforge_options_behavior_orats_gap_review.v1"
)

REQUIRED_FOR_ETF_MVP = "required_for_etf_mvp"
PARTIAL_FOR_ETF_MVP = "partial_for_etf_mvp"
DEFERRED_FOR_ETF_MVP = "deferred_for_etf_mvp"
VENDOR_ENHANCEMENT = "vendor_enhancement"


ORATS_ALIGNED_CAPABILITY_CONTRACT: tuple[dict[str, Any], ...] = (
    {
        "capability": "iv_level",
        "orats_benchmark_area": "implied_volatility_summary",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Determines whether premium buying, premium selling, or neutral-volatility structures are more appropriate.",
        "minimum_signalforge_fields": ["implied_volatility"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options_behavior.behavior_classifier.classify_iv_behavior",
            "avg_implied_volatility",
        ],
    },
    {
        "capability": "iv_rank_percentile",
        "orats_benchmark_area": "iv_rank_percentile_history",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Compares current IV to its own historical distribution before selling or buying volatility.",
        "minimum_signalforge_fields": ["implied_volatility", "quote_date", "iv_history"],
        "signalforge_status": "gap",
        "signalforge_evidence": [],
    },
    {
        "capability": "iv_expansion_contraction",
        "orats_benchmark_area": "iv_change_history",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Distinguishes expanding volatility from contracting volatility for debit/credit strategy fit.",
        "minimum_signalforge_fields": ["implied_volatility", "quote_date", "prior_implied_volatility"],
        "signalforge_status": "gap",
        "signalforge_evidence": [],
    },
    {
        "capability": "skew_behavior",
        "orats_benchmark_area": "skew_surface_shape",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Identifies put-skew, call-skew, balanced skew, or distorted skew for verticals, collars, calendars, and spreads.",
        "minimum_signalforge_fields": ["implied_volatility", "strike", "right", "moneyness"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options.skew.compute_skew",
            "signalforge.engines.options.skew.compute_put_call_skew",
            "signalforge.engines.options_behavior.behavior_classifier.classify_skew_behavior",
        ],
    },
    {
        "capability": "term_structure_behavior",
        "orats_benchmark_area": "term_structure_surface_shape",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Separates contango, backwardation, and flat term structures for calendar/diagonal/debit/credit fit.",
        "minimum_signalforge_fields": ["implied_volatility", "expiration", "days_to_expiration"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options.term_structure.compute_term_structure",
            "signalforge.engines.options.term_structure.compare_front_back_iv",
            "signalforge.engines.options.term_structure.classify_term_structure",
            "signalforge.engines.options_behavior.behavior_classifier.classify_term_structure_behavior",
        ],
    },
    {
        "capability": "liquidity_state",
        "orats_benchmark_area": "quotes_liquidity_open_interest",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Blocks illiquid chains before strategy selection.",
        "minimum_signalforge_fields": ["bid", "ask", "volume", "open_interest"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options.liquidity.add_liquidity_metrics",
            "signalforge.engines.options.liquidity.classify_liquidity",
            "signalforge.engines.options_behavior.behavior_classifier.classify_liquidity_behavior",
        ],
    },
    {
        "capability": "spread_width",
        "orats_benchmark_area": "bid_ask_quote_quality",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Prevents strategy selection when bid/ask spreads are too wide.",
        "minimum_signalforge_fields": ["bid", "ask"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options.liquidity.add_liquidity_metrics",
            "spread_pct",
            "execution_quote_gate",
        ],
    },
    {
        "capability": "open_interest_behavior",
        "orats_benchmark_area": "open_interest_activity",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Verifies contract participation and chain depth.",
        "minimum_signalforge_fields": ["open_interest"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options.liquidity.add_liquidity_metrics",
            "total_open_interest",
        ],
    },
    {
        "capability": "volume_behavior",
        "orats_benchmark_area": "option_volume_activity",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Confirms activity and current participation in the chain.",
        "minimum_signalforge_fields": ["volume"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options.liquidity.add_liquidity_metrics",
            "total_volume",
        ],
    },
    {
        "capability": "gamma_concentration",
        "orats_benchmark_area": "greeks_risk_distribution",
        "mvp_requirement": PARTIAL_FOR_ETF_MVP,
        "decision_use": "Detects strike/expiry gamma clustering that can change risk, pinning, and strategy width selection.",
        "minimum_signalforge_fields": ["gamma", "strike", "expiration", "open_interest"],
        "signalforge_status": "partial",
        "signalforge_evidence": [
            "avg_abs_gamma exists",
            "needs strike/expiration gamma concentration aggregation",
        ],
    },
    {
        "capability": "delta_availability",
        "orats_benchmark_area": "greeks_contract_selection",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Checks whether required deltas exist for directional, neutral, and spread structures.",
        "minimum_signalforge_fields": ["delta"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options.option_behavior_source_readiness has_delta",
            "contract-level delta fields are accepted",
        ],
    },
    {
        "capability": "theta_sensitivity",
        "orats_benchmark_area": "greeks_decay_exposure",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Distinguishes theta-positive from theta-negative structures and decay risk.",
        "minimum_signalforge_fields": ["theta"],
        "signalforge_status": "partial",
        "signalforge_evidence": [
            "source readiness accepts theta",
            "needs theta behavior classifier output",
        ],
    },
    {
        "capability": "vega_sensitivity",
        "orats_benchmark_area": "greeks_volatility_exposure",
        "mvp_requirement": REQUIRED_FOR_ETF_MVP,
        "decision_use": "Measures volatility sensitivity for debit, credit, calendar, and volatility expansion/contraction strategies.",
        "minimum_signalforge_fields": ["vega"],
        "signalforge_status": "covered",
        "signalforge_evidence": [
            "signalforge.engines.options_behavior.behavior_classifier.classify_greek_behavior",
            "avg_abs_vega",
        ],
    },
    {
        "capability": "event_premium",
        "orats_benchmark_area": "earnings_event_premium",
        "mvp_requirement": DEFERRED_FOR_ETF_MVP,
        "decision_use": "Single-name earnings/event premium filter. Mostly not needed for ETF-first MVP.",
        "minimum_signalforge_fields": ["event_date", "implied_event_move"],
        "signalforge_status": "deferred",
        "signalforge_evidence": ["ETF-first scope defers single-name event premium"],
    },
    {
        "capability": "proprietary_vol_surface_forecast",
        "orats_benchmark_area": "smoothed_iv_surface_forecast",
        "mvp_requirement": VENDOR_ENHANCEMENT,
        "decision_use": "Potential vendor enhancement, not required for deterministic SignalForge strategy eligibility.",
        "minimum_signalforge_fields": ["vendor_surface_forecast"],
        "signalforge_status": "vendor_enhancement",
        "signalforge_evidence": ["Not required for SignalForge ETF MVP"],
    },
)


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "implied_volatility": ("implied_volatility", "iv", "impliedvolatility"),
    "quote_date": ("quote_date", "date", "timestamp"),
    "prior_implied_volatility": ("prior_implied_volatility", "previous_implied_volatility", "prior_iv"),
    "iv_history": ("iv_history", "iv_percentile", "iv_rank", "historical_implied_volatility"),
    "strike": ("strike", "strike_price"),
    "right": ("right", "option_type", "type", "contract_type"),
    "moneyness": ("moneyness", "underlying_price", "underlying_last_price"),
    "expiration": ("expiration", "expiry", "expiration_date"),
    "days_to_expiration": ("days_to_expiration", "dte"),
    "bid": ("bid", "bid_price", "bidprice"),
    "ask": ("ask", "ask_price", "askprice"),
    "volume": ("volume",),
    "open_interest": ("open_interest", "openinterest", "openInterest"),
    "gamma": ("gamma",),
    "delta": ("delta",),
    "theta": ("theta",),
    "vega": ("vega",),
    "event_date": ("event_date", "earnings_date", "catalyst_date"),
    "implied_event_move": ("implied_event_move", "event_premium", "earnings_premium"),
    "vendor_surface_forecast": ("vendor_surface_forecast", "smv_volatility", "orats_smv"),
}


def build_signalforge_options_behavior_orats_gap_review(
    option_source: Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    signalforge_capabilities: Mapping[str, Any] | Sequence[str] | None = None,
    etf_first: bool = True,
) -> dict[str, Any]:
    """Build an ORATS-aligned gap review for SignalForge Options Behavior.

    This is a feature/decision-level review. It does not call vendors, brokers,
    routes orders, or export raw option rows.
    """

    available_fields = _available_fields(option_source)
    declared_capabilities = _declared_capabilities(signalforge_capabilities)

    items = [
        _capability_item(
            contract_item,
            available_fields=available_fields,
            declared_capabilities=declared_capabilities,
            etf_first=etf_first,
        )
        for contract_item in ORATS_ALIGNED_CAPABILITY_CONTRACT
    ]

    summary = _summary(items)
    status = _overall_status(summary)

    return {
        "artifact_type": "signalforge_options_behavior_orats_gap_review",
        "schema_version": OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "options_behavior_orats_gap_review",
        "adapter_type": "options_behavior_orats_gap_review_builder",
        "review_scope": "feature_decision_level_not_raw_vendor_replication",
        "benchmark_vendor": "ORATS",
        "benchmark_use": "gap_analysis_yardstick_only",
        "etf_first": bool(etf_first),
        "source_artifacts": {
            "option_source": _artifact_type(option_source),
            "signalforge_capabilities": _artifact_type(signalforge_capabilities),
        },
        "available_source_fields": sorted(available_fields),
        "declared_signalforge_capabilities": sorted(declared_capabilities),
        "capability_items": items,
        "orats_gap_review_summary": summary,
        "next_build_recommendations": _next_build_recommendations(items),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _capability_item(
    contract_item: Mapping[str, Any],
    *,
    available_fields: set[str],
    declared_capabilities: set[str],
    etf_first: bool,
) -> dict[str, Any]:
    capability = str(contract_item["capability"])
    minimum_fields = list(contract_item.get("minimum_signalforge_fields") or [])
    missing_fields = [
        field for field in minimum_fields if not _field_available(field, available_fields)
    ]

    baseline_status = str(contract_item.get("signalforge_status") or "gap")
    mvp_requirement = str(contract_item.get("mvp_requirement") or REQUIRED_FOR_ETF_MVP)

    if capability in declared_capabilities:
        baseline_status = "covered"

    if etf_first and mvp_requirement == DEFERRED_FOR_ETF_MVP:
        coverage_status = "deferred"
        gap_severity = "not_required_for_etf_mvp"
    elif mvp_requirement == VENDOR_ENHANCEMENT:
        coverage_status = "vendor_enhancement"
        gap_severity = "optional_vendor_enhancement"
    elif baseline_status == "covered":
        coverage_status = "covered"
        gap_severity = "none"
    elif baseline_status == "partial":
        coverage_status = "partial"
        gap_severity = "medium"
    else:
        coverage_status = "gap"
        gap_severity = "high" if mvp_requirement == REQUIRED_FOR_ETF_MVP else "medium"

    source_field_state = "not_evaluated"
    if available_fields:
        source_field_state = "ready" if not missing_fields else "missing_fields"

    return {
        "capability": capability,
        "orats_benchmark_area": contract_item.get("orats_benchmark_area"),
        "mvp_requirement": mvp_requirement,
        "decision_use": contract_item.get("decision_use"),
        "coverage_status": coverage_status,
        "gap_severity": gap_severity,
        "minimum_signalforge_fields": minimum_fields,
        "source_field_state": source_field_state,
        "missing_source_fields": missing_fields,
        "signalforge_evidence": list(contract_item.get("signalforge_evidence") or []),
        "required_for_strategy_selection": mvp_requirement
        in {REQUIRED_FOR_ETF_MVP, PARTIAL_FOR_ETF_MVP},
        "manual_review_required": coverage_status in {"gap", "partial"},
    }


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("coverage_status")) for item in items)
    severity_counts = Counter(str(item.get("gap_severity")) for item in items)

    required_items = [
        item
        for item in items
        if item.get("mvp_requirement") == REQUIRED_FOR_ETF_MVP
    ]
    required_gaps = [
        item
        for item in required_items
        if item.get("coverage_status") == "gap"
    ]
    required_partials = [
        item
        for item in required_items
        if item.get("coverage_status") == "partial"
    ]

    return {
        "capability_count": len(items),
        "required_for_etf_mvp_count": len(required_items),
        "covered_count": status_counts.get("covered", 0),
        "partial_count": status_counts.get("partial", 0),
        "gap_count": status_counts.get("gap", 0),
        "deferred_count": status_counts.get("deferred", 0),
        "vendor_enhancement_count": status_counts.get("vendor_enhancement", 0),
        "high_severity_gap_count": severity_counts.get("high", 0),
        "required_gap_count": len(required_gaps),
        "required_partial_count": len(required_partials),
        "covered_capabilities": _capabilities_with_status(items, "covered"),
        "partial_capabilities": _capabilities_with_status(items, "partial"),
        "gap_capabilities": _capabilities_with_status(items, "gap"),
        "deferred_capabilities": _capabilities_with_status(items, "deferred"),
        "vendor_enhancement_capabilities": _capabilities_with_status(
            items,
            "vendor_enhancement",
        ),
    }


def _overall_status(summary: Mapping[str, Any]) -> str:
    if int(summary.get("required_gap_count") or 0) > 0:
        return "needs_review"
    if int(summary.get("required_partial_count") or 0) > 0:
        return "needs_review"
    return "ready"


def _next_build_recommendations(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    for item in items:
        capability = str(item.get("capability"))
        if item.get("coverage_status") == "gap":
            recommendations.append(
                {
                    "capability": capability,
                    "priority": "high"
                    if item.get("gap_severity") == "high"
                    else "medium",
                    "recommendation": _recommendation_text(capability),
                }
            )
        elif item.get("coverage_status") == "partial":
            recommendations.append(
                {
                    "capability": capability,
                    "priority": "medium",
                    "recommendation": _recommendation_text(capability),
                }
            )

    return recommendations


def _recommendation_text(capability: str) -> str:
    return {
        "iv_rank_percentile": "Add rolling IV history snapshots and classify current IV rank/percentile by symbol.",
        "iv_expansion_contraction": "Add prior-snapshot IV comparison to classify IV expansion, contraction, or stable IV.",
        "gamma_concentration": "Aggregate gamma by strike and expiration to detect clustered gamma risk.",
        "theta_sensitivity": "Promote theta from source-readiness coverage into an explicit theta behavior classifier output.",
    }.get(capability, f"Build explicit Options Behavior classifier support for {capability}.")


def _available_fields(source: Mapping[str, Any] | Sequence[Any] | None) -> set[str]:
    rows = _extract_rows(source)
    fields: set[str] = set()

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for key, value in row.items():
            if value is None:
                continue
            fields.add(str(key))

    if isinstance(source, Mapping):
        for key in ("available_fields", "source_fields", "fields"):
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(
                value,
                (str, bytes, bytearray),
            ):
                fields.update(str(item) for item in value)

    return fields


def _field_available(field: str, available_fields: set[str]) -> bool:
    aliases = _FIELD_ALIASES.get(field, (field,))
    normalized_available = {_normalize_field_name(value) for value in available_fields}
    return any(_normalize_field_name(alias) in normalized_available for alias in aliases)


def _extract_rows(source: Mapping[str, Any] | Sequence[Any] | None) -> list[Any]:
    if source is None:
        return []

    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)

    if not isinstance(source, Mapping):
        return []

    direct_keys = (
        "option_rows",
        "options",
        "option_chain",
        "option_chains",
        "contracts",
        "rows",
        "data",
    )

    for key in direct_keys:
        value = source.get(key)
        if _looks_like_rows(value):
            return list(value)

    for key in ("payload", "result", "import_result", "data"):
        nested = source.get(key)
        if isinstance(nested, Mapping):
            nested_rows = _extract_rows(nested)
            if nested_rows:
                return nested_rows

    return []


def _looks_like_rows(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _declared_capabilities(
    signalforge_capabilities: Mapping[str, Any] | Sequence[str] | None,
) -> set[str]:
    if signalforge_capabilities is None:
        return set()

    if isinstance(signalforge_capabilities, Sequence) and not isinstance(
        signalforge_capabilities,
        (str, bytes, bytearray),
    ):
        return {str(item) for item in signalforge_capabilities}

    if not isinstance(signalforge_capabilities, Mapping):
        return set()

    capabilities: set[str] = set()
    for key in (
        "covered_capabilities",
        "capabilities",
        "implemented_capabilities",
        "option_behavior_capabilities",
    ):
        value = signalforge_capabilities.get(key)
        if isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            capabilities.update(str(item) for item in value)

    return capabilities


def _capabilities_with_status(
    items: Sequence[Mapping[str, Any]],
    status: str,
) -> list[str]:
    return sorted(
        str(item["capability"])
        for item in items
        if item.get("coverage_status") == status
    )


def _artifact_type(source: Any) -> str | None:
    if isinstance(source, Mapping):
        value = source.get("artifact_type")
        return str(value) if value is not None else None
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    return None


def _normalize_field_name(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")




