from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


POSITION_SIZING_RECOMMENDATION_SCHEMA_VERSION = "signalforge_position_sizing_recommendation.v1"

COVERED_CAPABILITIES = [
    "position_sizing_recommendation",
    "risk_budget_position_sizing",
    "portfolio_construction_to_sizing_handoff",
    "review_only_position_size_guidance",
    "position_sizing_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "portfolio_construction_optimizer",
]

PORTFOLIO_CONSTRUCTION_KEYS = (
    "ranked_portfolio_construction_items",
    "portfolio_construction_recommendation_queue",
    "portfolio_construction_items",
    "items",
    "data",
    "rows",
)

ELIGIBLE_PORTFOLIO_CONSTRUCTION_STATUSES = {
    "ready_for_portfolio_allocation_review",
    "constrained_for_portfolio_allocation_review",
}

STATUS_READY = "ready_for_position_sizing_review"
STATUS_CONSTRAINED = "constrained_for_position_sizing_review"
STATUS_DATA_REVIEW = "data_review_required"
STATUS_BLOCKED = "blocked_from_position_sizing"

RECOMMEND_SIZE = "review_position_size_recommendation"
RECOMMEND_SIZE_CONSTRAINED = "review_constrained_position_size_recommendation"
RECOMMEND_DATA_REVIEW = "exclude_position_sizing_data_review_required"
RECOMMEND_BLOCKED = "blocked_from_position_sizing_review"


def build_signalforge_position_sizing_recommendation(
    portfolio_construction_optimizer_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    portfolio_equity: float = 100000.0,
    base_risk_per_trade_pct: float = 0.01,
    constrained_risk_multiplier: float = 0.50,
    max_risk_per_trade_pct: float = 0.015,
    max_total_new_risk_pct: float = 0.03,
    min_position_sizing_score: float = 0.40,
) -> dict[str, Any]:
    """Build review-only position sizing recommendations.

    This artifact converts portfolio construction recommendations into risk-budget
    guidance. It does not create order intent, compute broker quantities for
    submission, route/submit orders, model fills/slippage, or authorize automatic
    position maintenance.
    """

    source_artifacts = {
        "portfolio_construction_optimizer_source": _source_artifact_type(portfolio_construction_optimizer_source),
    }

    source_items = _extract_items(portfolio_construction_optimizer_source, PORTFOLIO_CONSTRUCTION_KEYS)
    if not source_items:
        return _blocked_result(["missing_portfolio_construction_recommendations"], source_artifacts=source_artifacts)

    normalized_items = [
        _normalize_sizing_item(
            item,
            portfolio_equity=float(portfolio_equity),
            base_risk_per_trade_pct=float(base_risk_per_trade_pct),
            constrained_risk_multiplier=float(constrained_risk_multiplier),
            max_risk_per_trade_pct=float(max_risk_per_trade_pct),
            min_position_sizing_score=float(min_position_sizing_score),
        )
        for item in source_items
        if isinstance(item, Mapping)
    ]
    normalized_items = [item for item in normalized_items if item.get("symbol")]
    if not normalized_items:
        return _blocked_result(["missing_valid_portfolio_construction_symbols"], source_artifacts=source_artifacts)

    sizing_queue = [item for item in normalized_items if item.get("eligible_for_position_sizing_review")]
    sizing_queue = _apply_total_risk_budget(
        sizing_queue,
        all_items=normalized_items,
        portfolio_equity=float(portfolio_equity),
        max_total_new_risk_pct=float(max_total_new_risk_pct),
    )

    for rank, item in enumerate([item for item in sizing_queue if item.get("included_in_position_sizing_review")], start=1):
        item["position_sizing_rank"] = rank

    # Preserve excluded/data-review items alongside queue items for a complete audit trail.
    queue_by_symbol = {item.get("symbol"): item for item in sizing_queue if item.get("symbol")}
    final_items = [queue_by_symbol.get(item.get("symbol"), item) for item in normalized_items]
    included_items = [item for item in final_items if item.get("included_in_position_sizing_review")]

    summary = _summary(
        items=final_items,
        included_items=included_items,
        portfolio_equity=float(portfolio_equity),
    )

    status = (
        "ready"
        if summary["position_sizing_recommendation_count"] > 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_position_sizing_recommendation",
        "schema_version": POSITION_SIZING_RECOMMENDATION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "position_sizing_recommendation",
        "adapter_type": "position_sizing_recommendation_builder",
        "review_scope": "position_sizing_recommendation_not_order_intent_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "position_maintenance_policy",
                "priority": "high",
                "recommendation": "Use review-approved position sizing recommendations to define hold, take-profit, risk-cut, and manual-defense rules before any execution workflow.",
            }
        ],
        "position_sizing_items": final_items,
        "position_sizing_recommendation_queue": included_items,
        "ranked_position_sizing_recommendations": included_items,
        "position_sizing_recommendation_summary": summary,
        "thresholds": {
            "portfolio_equity": float(portfolio_equity),
            "base_risk_per_trade_pct": float(base_risk_per_trade_pct),
            "constrained_risk_multiplier": float(constrained_risk_multiplier),
            "max_risk_per_trade_pct": float(max_risk_per_trade_pct),
            "max_total_new_risk_pct": float(max_total_new_risk_pct),
            "min_position_sizing_score": float(min_position_sizing_score),
        },
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "blocked_reasons": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _normalize_sizing_item(
    item: Mapping[str, Any],
    *,
    portfolio_equity: float,
    base_risk_per_trade_pct: float,
    constrained_risk_multiplier: float,
    max_risk_per_trade_pct: float,
    min_position_sizing_score: float,
) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker")))
    source_status = _clean_text(
        _first_value(item, ("portfolio_construction_status", "coverage_status", "source_status"))
    )
    risk_flags = _merged_list(item.get("risk_flags"))
    constraint_flags = _merged_list(item.get("constraint_flags"))
    portfolio_constraint_flags = _merged_list(item.get("portfolio_constraint_flags"))
    portfolio_budget_flags = _merged_list(item.get("portfolio_budget_flags"))
    data_review_reasons = _merged_list(item.get("data_review_reasons"))
    hard_block_reasons = _merged_list(item.get("hard_block_reasons"))
    sizing_review_flags: list[str] = []

    if source_status not in ELIGIBLE_PORTFOLIO_CONSTRUCTION_STATUSES:
        data_review_reasons.append("portfolio_construction_not_ready_for_position_sizing")

    portfolio_construction_score = _safe_float(item.get("portfolio_construction_score"))
    portfolio_candidate_score = _safe_float(item.get("portfolio_candidate_score"))
    top_contract_score = _safe_float(item.get("top_contract_candidate_score"))
    score_inputs = [value for value in (portfolio_construction_score, portfolio_candidate_score, top_contract_score) if value is not None]
    base_score = sum(score_inputs) / len(score_inputs) if score_inputs else None
    if base_score is None:
        data_review_reasons.append("missing_position_sizing_score_inputs")
        base_score = 0.0

    risk_count = len(set(risk_flags + constraint_flags + portfolio_constraint_flags + portfolio_budget_flags))
    score_penalty = min(0.30, 0.04 * risk_count)
    position_sizing_score = round(max(0.0, min(1.0, float(base_score)) - score_penalty), 4)
    if position_sizing_score < float(min_position_sizing_score):
        sizing_review_flags.append("below_minimum_position_sizing_score")

    is_constrained = bool(
        risk_flags
        or constraint_flags
        or portfolio_constraint_flags
        or portfolio_budget_flags
        or source_status == "constrained_for_portfolio_allocation_review"
    )
    sizing_multiplier = float(constrained_risk_multiplier) if is_constrained else 1.0
    # Scale the base risk by score, while respecting the hard max per-trade cap.
    recommended_risk_pct = min(float(max_risk_per_trade_pct), max(0.0, float(base_risk_per_trade_pct) * sizing_multiplier * position_sizing_score))
    recommended_risk_budget = round(max(0.0, float(portfolio_equity) * recommended_risk_pct), 2)

    if hard_block_reasons:
        coverage_status = STATUS_BLOCKED
        sizing_recommendation = RECOMMEND_BLOCKED
    elif data_review_reasons or sizing_review_flags:
        coverage_status = STATUS_DATA_REVIEW
        sizing_recommendation = RECOMMEND_DATA_REVIEW
    elif is_constrained:
        coverage_status = STATUS_CONSTRAINED
        sizing_recommendation = RECOMMEND_SIZE_CONSTRAINED
    else:
        coverage_status = STATUS_READY
        sizing_recommendation = RECOMMEND_SIZE

    eligible = coverage_status in {STATUS_READY, STATUS_CONSTRAINED}

    return {
        "artifact_type": "position_sizing_recommendation_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "position_sizing_status": coverage_status,
        "eligible_for_position_sizing_review": eligible,
        "included_in_position_sizing_review": eligible,
        "manual_review_required": True,
        "sizing_recommendation": sizing_recommendation,
        "selected_strategy_family": _first_value(item, ("selected_strategy_family", "strategy_family")),
        "portfolio_construction_score": portfolio_construction_score,
        "portfolio_candidate_score": portfolio_candidate_score,
        "top_contract_candidate_score": top_contract_score,
        "position_sizing_score": position_sizing_score,
        "recommended_risk_budget_pct": round(recommended_risk_pct, 6),
        "recommended_risk_budget_dollars": recommended_risk_budget,
        "recommended_risk_units": round(recommended_risk_pct / float(base_risk_per_trade_pct), 4) if base_risk_per_trade_pct else None,
        "sizing_multiplier": round(sizing_multiplier, 4),
        "quantity_recommendation": None,
        "quantity_recommendation_state": "review_only_risk_budget_not_order_quantity",
        "top_contract_symbol": item.get("top_contract_symbol") or item.get("contract_symbol"),
        "top_contract_expiration": item.get("top_contract_expiration") or item.get("expiration"),
        "top_contract_strike": item.get("top_contract_strike") or item.get("strike"),
        "top_contract_option_right": item.get("top_contract_option_right") or item.get("option_right"),
        "top_contract_delta": _safe_float(item.get("top_contract_delta") or item.get("delta")),
        "top_contract_gamma": _safe_float(item.get("top_contract_gamma") or item.get("gamma")),
        "top_contract_theta": _safe_float(item.get("top_contract_theta") or item.get("theta")),
        "top_contract_vega": _safe_float(item.get("top_contract_vega") or item.get("vega")),
        "top_contract_spread_pct": _safe_float(item.get("top_contract_spread_pct") or item.get("spread_pct")),
        "source_portfolio_construction_status": source_status,
        "source_portfolio_construction_rank": item.get("portfolio_construction_rank"),
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "portfolio_constraint_flags": sorted(set(portfolio_constraint_flags)),
        "portfolio_budget_flags": sorted(set(portfolio_budget_flags)),
        "sizing_review_flags": sorted(set(sizing_review_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": sorted(
            set(
                data_review_reasons
                + hard_block_reasons
                + risk_flags
                + constraint_flags
                + portfolio_constraint_flags
                + portfolio_budget_flags
                + sizing_review_flags
            )
        ),
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _apply_total_risk_budget(
    queue_items: Sequence[Mapping[str, Any]],
    *,
    all_items: Sequence[Mapping[str, Any]],
    portfolio_equity: float,
    max_total_new_risk_pct: float,
) -> list[dict[str, Any]]:
    max_total_risk_budget = max(0.0, float(portfolio_equity) * float(max_total_new_risk_pct))
    running_total = 0.0
    output: list[dict[str, Any]] = []

    ranked_items = sorted(
        [dict(item) for item in queue_items],
        key=lambda item: (
            _safe_float(item.get("position_sizing_score")) or -999.0,
            _safe_float(item.get("recommended_risk_budget_dollars")) or -999.0,
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )

    for item in ranked_items:
        budget = _safe_float(item.get("recommended_risk_budget_dollars")) or 0.0
        total_flags = list(item.get("portfolio_budget_flags") or [])
        if running_total + budget > max_total_risk_budget:
            total_flags.append("total_new_risk_budget_exceeded")
            item["coverage_status"] = STATUS_DATA_REVIEW
            item["position_sizing_status"] = STATUS_DATA_REVIEW
            item["eligible_for_position_sizing_review"] = False
            item["included_in_position_sizing_review"] = False
            item["sizing_recommendation"] = RECOMMEND_DATA_REVIEW
            item["portfolio_budget_flags"] = sorted(set(total_flags))
            item["needs_review_reasons"] = sorted(set(_merged_list(item.get("needs_review_reasons")) + total_flags))
        else:
            running_total += budget
            item["portfolio_budget_flags"] = sorted(set(total_flags))
        output.append(item)

    return output


def _summary(*, items: Sequence[Mapping[str, Any]], included_items: Sequence[Mapping[str, Any]], portfolio_equity: float) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in items)
    strategy_counts = Counter(str(item.get("selected_strategy_family")) for item in items if item.get("selected_strategy_family"))
    sizing_strategy_counts = Counter(str(item.get("selected_strategy_family")) for item in included_items if item.get("selected_strategy_family"))
    risk_flag_counts = Counter(flag for item in items for flag in item.get("risk_flags", []))
    constraint_flag_counts = Counter(flag for item in items for flag in item.get("constraint_flags", []))
    portfolio_constraint_flag_counts = Counter(flag for item in items for flag in item.get("portfolio_constraint_flags", []))
    portfolio_budget_flag_counts = Counter(flag for item in items for flag in item.get("portfolio_budget_flags", []))
    sizing_review_flag_counts = Counter(flag for item in items for flag in item.get("sizing_review_flags", []))
    data_review_counts = Counter(reason for item in items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in items for reason in item.get("hard_block_reasons", []))

    ready_count = coverage_counts.get(STATUS_READY, 0)
    constrained_count = coverage_counts.get(STATUS_CONSTRAINED, 0)
    data_review_count = coverage_counts.get(STATUS_DATA_REVIEW, 0)
    blocked_count = coverage_counts.get(STATUS_BLOCKED, 0)
    total_recommended_risk = round(sum(_safe_float(item.get("recommended_risk_budget_dollars")) or 0.0 for item in included_items), 2)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(items),
        "source_portfolio_construction_candidate_count": len(items),
        "position_sizing_recommendation_count": len(included_items),
        "position_sizing_symbol_count": len({item.get("symbol") for item in included_items if item.get("symbol")}),
        "ready_position_sizing_symbol_count": ready_count,
        "constrained_position_sizing_symbol_count": constrained_count,
        "data_review_symbol_count": data_review_count,
        "blocked_symbol_count": blocked_count,
        "needs_review_symbol_count": data_review_count + blocked_count,
        "manual_review_symbol_count": len(items),
        "portfolio_equity": float(portfolio_equity),
        "total_recommended_risk_budget_dollars": total_recommended_risk,
        "total_recommended_risk_budget_pct": round(total_recommended_risk / float(portfolio_equity), 6) if portfolio_equity else 0.0,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_counts.items())),
        "position_sizing_strategy_family_counts": dict(sorted(sizing_strategy_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_flag_counts.items())),
        "portfolio_constraint_flag_counts": dict(sorted(portfolio_constraint_flag_counts.items())),
        "portfolio_budget_flag_counts": dict(sorted(portfolio_budget_flag_counts.items())),
        "sizing_review_flag_counts": dict(sorted(sizing_review_flag_counts.items())),
        "data_review_reason_counts": dict(sorted(data_review_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
        "position_sizing_exposure_preview": _aggregate_exposure(included_items),
    }


def _aggregate_exposure(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(items),
        "gross_abs_delta": round(sum(abs(_safe_float(item.get("top_contract_delta")) or 0.0) for item in items), 4),
        "net_delta": round(sum(_safe_float(item.get("top_contract_delta")) or 0.0 for item in items), 4),
        "gross_abs_gamma": round(sum(abs(_safe_float(item.get("top_contract_gamma")) or 0.0) for item in items), 4),
        "gross_abs_vega": round(sum(abs(_safe_float(item.get("top_contract_vega")) or 0.0) for item in items), 4),
        "net_theta": round(sum(_safe_float(item.get("top_contract_theta")) or 0.0 for item in items), 4),
    }


def _blocked_result(blocked_reasons: list[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": 0,
        "source_portfolio_construction_candidate_count": 0,
        "position_sizing_recommendation_count": 0,
        "position_sizing_symbol_count": 0,
        "ready_position_sizing_symbol_count": 0,
        "constrained_position_sizing_symbol_count": 0,
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "portfolio_equity": 0.0,
        "total_recommended_risk_budget_dollars": 0.0,
        "total_recommended_risk_budget_pct": 0.0,
        "coverage_status_counts": {},
        "strategy_family_counts": {},
        "position_sizing_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "portfolio_constraint_flag_counts": {},
        "portfolio_budget_flag_counts": {},
        "sizing_review_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
        "position_sizing_exposure_preview": _aggregate_exposure([]),
    }
    return {
        "artifact_type": "signalforge_position_sizing_recommendation",
        "schema_version": POSITION_SIZING_RECOMMENDATION_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "position_sizing_recommendation",
        "adapter_type": "position_sizing_recommendation_builder",
        "review_scope": "position_sizing_recommendation_not_order_intent_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [],
        "position_sizing_items": [],
        "position_sizing_recommendation_queue": [],
        "ranked_position_sizing_recommendations": [],
        "position_sizing_recommendation_summary": summary,
        "thresholds": {},
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, list):
        return list(source)
    if not isinstance(source, Mapping):
        return []
    for key in keys:
        value = source.get(key)
        if isinstance(value, list):
            return list(value)
    for value in source.values():
        if isinstance(value, Mapping):
            nested = _extract_items(value, keys)
            if nested:
                return nested
    return []


def _source_artifact_type(source: Any) -> str:
    if source is None:
        return "missing"
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or source.get("contract") or "mapping")
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    return type(source).__name__


def _first_value(source: Mapping[str, Any], keys: Sequence[str]) -> Any:
    if not isinstance(source, Mapping):
        return None
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _merged_list(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value:
                merged.append(value)
            continue
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            for item in value:
                if item not in (None, ""):
                    merged.append(str(item))
            continue
        merged.append(str(value))
    return merged


def _clean_symbol(value: Any) -> str:
    return "" if value is None else str(value).strip().upper()


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
