from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


POSITION_MAINTENANCE_POLICY_SCHEMA_VERSION = "signalforge_position_maintenance_policy.v1"

COVERED_CAPABILITIES = [
    "position_maintenance_policy",
    "review_only_position_maintenance_rules",
    "hold_take_profit_risk_cut_policy",
    "manual_defense_review_policy",
    "position_maintenance_not_automatic_action_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "position_sizing_recommendation",
]

POSITION_SIZING_KEYS = (
    "ranked_position_sizing_recommendations",
    "position_sizing_recommendation_queue",
    "position_sizing_items",
    "items",
    "data",
    "rows",
)

ELIGIBLE_POSITION_SIZING_STATUSES = {
    "ready_for_position_sizing_review",
    "constrained_for_position_sizing_review",
}

STATUS_READY = "ready_for_position_maintenance_policy"
STATUS_CONSTRAINED = "constrained_for_position_maintenance_policy"
STATUS_DATA_REVIEW = "data_review_required"
STATUS_BLOCKED = "blocked_from_position_maintenance_policy"

RECOMMEND_POLICY = "define_manual_position_maintenance_policy"
RECOMMEND_POLICY_CONSTRAINED = "define_constrained_manual_position_maintenance_policy"
RECOMMEND_DATA_REVIEW = "exclude_position_maintenance_data_review_required"
RECOMMEND_BLOCKED = "blocked_from_position_maintenance_policy_review"


def build_signalforge_position_maintenance_policy(
    position_sizing_recommendation_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    take_profit_capture_pct: float = 0.50,
    risk_cut_pct_of_budget: float = 0.50,
    delta_drift_threshold: float = 0.20,
    gamma_review_threshold: float = 0.05,
    vega_review_threshold: float = 0.40,
    theta_review_threshold: float = 0.05,
    dte_review_threshold: int = 21,
    min_position_maintenance_score: float = 0.35,
) -> dict[str, Any]:
    """Build review-only position maintenance policies.

    This artifact defines manual hold, take-profit, risk-cut, and defense review
    rules from review-approved sizing recommendations. It does not create order
    intent, route/submit orders, close/roll/defend positions automatically, model
    fills/slippage, or connect to a broker.
    """

    source_artifacts = {
        "position_sizing_recommendation_source": _source_artifact_type(position_sizing_recommendation_source),
    }

    source_items = _extract_items(position_sizing_recommendation_source, POSITION_SIZING_KEYS)
    if not source_items:
        return _blocked_result(["missing_position_sizing_recommendations"], source_artifacts=source_artifacts)

    normalized_items = [
        _normalize_maintenance_item(
            item,
            take_profit_capture_pct=float(take_profit_capture_pct),
            risk_cut_pct_of_budget=float(risk_cut_pct_of_budget),
            delta_drift_threshold=float(delta_drift_threshold),
            gamma_review_threshold=float(gamma_review_threshold),
            vega_review_threshold=float(vega_review_threshold),
            theta_review_threshold=float(theta_review_threshold),
            dte_review_threshold=int(dte_review_threshold),
            min_position_maintenance_score=float(min_position_maintenance_score),
        )
        for item in source_items
        if isinstance(item, Mapping)
    ]
    normalized_items = [item for item in normalized_items if item.get("symbol")]
    if not normalized_items:
        return _blocked_result(["missing_valid_position_sizing_symbols"], source_artifacts=source_artifacts)

    included_items = [item for item in normalized_items if item.get("included_in_position_maintenance_policy")]
    included_items = sorted(
        included_items,
        key=lambda item: (
            _safe_float(item.get("position_maintenance_score")) or -999.0,
            _safe_float(item.get("recommended_risk_budget_dollars")) or -999.0,
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )
    for rank, item in enumerate(included_items, start=1):
        item["position_maintenance_rank"] = rank

    included_by_symbol = {item.get("symbol"): item for item in included_items if item.get("symbol")}
    final_items = [included_by_symbol.get(item.get("symbol"), item) for item in normalized_items]

    summary = _summary(items=final_items, included_items=included_items)
    status = (
        "ready"
        if summary["position_maintenance_policy_count"] > 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_position_maintenance_policy",
        "schema_version": POSITION_MAINTENANCE_POLICY_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "position_maintenance_policy",
        "adapter_type": "position_maintenance_policy_builder",
        "review_scope": "position_maintenance_policy_not_automatic_action_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "historical_portfolio_replay",
                "priority": "high",
                "recommendation": "Replay portfolio construction, sizing, and maintenance policies historically before considering any broker or execution workflow.",
            }
        ],
        "position_maintenance_policy_items": final_items,
        "position_maintenance_policy_queue": included_items,
        "ranked_position_maintenance_policies": included_items,
        "position_maintenance_policy_summary": summary,
        "thresholds": {
            "take_profit_capture_pct": float(take_profit_capture_pct),
            "risk_cut_pct_of_budget": float(risk_cut_pct_of_budget),
            "delta_drift_threshold": float(delta_drift_threshold),
            "gamma_review_threshold": float(gamma_review_threshold),
            "vega_review_threshold": float(vega_review_threshold),
            "theta_review_threshold": float(theta_review_threshold),
            "dte_review_threshold": int(dte_review_threshold),
            "min_position_maintenance_score": float(min_position_maintenance_score),
        },
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "blocked_reasons": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _normalize_maintenance_item(
    item: Mapping[str, Any],
    *,
    take_profit_capture_pct: float,
    risk_cut_pct_of_budget: float,
    delta_drift_threshold: float,
    gamma_review_threshold: float,
    vega_review_threshold: float,
    theta_review_threshold: float,
    dte_review_threshold: int,
    min_position_maintenance_score: float,
) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker")))
    source_status = _clean_text(_first_value(item, ("position_sizing_status", "coverage_status", "source_status")))
    risk_flags = _merged_list(item.get("risk_flags"))
    constraint_flags = _merged_list(item.get("constraint_flags"))
    sizing_review_flags = _merged_list(item.get("sizing_review_flags"))
    portfolio_constraint_flags = _merged_list(item.get("portfolio_constraint_flags"))
    portfolio_budget_flags = _merged_list(item.get("portfolio_budget_flags"))
    data_review_reasons = _merged_list(item.get("data_review_reasons"))
    hard_block_reasons = _merged_list(item.get("hard_block_reasons"))
    maintenance_review_flags: list[str] = []

    if source_status not in ELIGIBLE_POSITION_SIZING_STATUSES:
        data_review_reasons.append("position_sizing_not_ready_for_maintenance_policy")

    position_sizing_score = _safe_float(item.get("position_sizing_score"))
    portfolio_construction_score = _safe_float(item.get("portfolio_construction_score"))
    top_contract_score = _safe_float(item.get("top_contract_candidate_score"))
    score_inputs = [value for value in (position_sizing_score, portfolio_construction_score, top_contract_score) if value is not None]
    base_score = sum(score_inputs) / len(score_inputs) if score_inputs else None
    if base_score is None:
        data_review_reasons.append("missing_position_maintenance_score_inputs")
        base_score = 0.0

    top_delta = _safe_float(item.get("top_contract_delta") or item.get("delta"))
    top_gamma = _safe_float(item.get("top_contract_gamma") or item.get("gamma"))
    top_theta = _safe_float(item.get("top_contract_theta") or item.get("theta"))
    top_vega = _safe_float(item.get("top_contract_vega") or item.get("vega"))
    abs_gamma = abs(top_gamma or 0.0)
    abs_theta = abs(top_theta or 0.0)
    abs_vega = abs(top_vega or 0.0)

    if abs_gamma >= float(gamma_review_threshold):
        maintenance_review_flags.append("gamma_exposure_manual_review")
    if abs_theta >= float(theta_review_threshold):
        maintenance_review_flags.append("theta_decay_manual_review")
    if abs_vega >= float(vega_review_threshold):
        maintenance_review_flags.append("vega_exposure_manual_review")

    risk_count = len(set(risk_flags + constraint_flags + sizing_review_flags + portfolio_constraint_flags + portfolio_budget_flags + maintenance_review_flags))
    score_penalty = min(0.35, 0.035 * risk_count)
    position_maintenance_score = round(max(0.0, min(1.0, float(base_score)) - score_penalty), 4)
    if position_maintenance_score < float(min_position_maintenance_score):
        data_review_reasons.append("below_minimum_position_maintenance_score")

    is_constrained = bool(
        risk_flags
        or constraint_flags
        or sizing_review_flags
        or portfolio_constraint_flags
        or portfolio_budget_flags
        or maintenance_review_flags
        or source_status == "constrained_for_position_sizing_review"
    )

    if hard_block_reasons:
        coverage_status = STATUS_BLOCKED
        maintenance_recommendation = RECOMMEND_BLOCKED
    elif data_review_reasons:
        coverage_status = STATUS_DATA_REVIEW
        maintenance_recommendation = RECOMMEND_DATA_REVIEW
    elif is_constrained:
        coverage_status = STATUS_CONSTRAINED
        maintenance_recommendation = RECOMMEND_POLICY_CONSTRAINED
    else:
        coverage_status = STATUS_READY
        maintenance_recommendation = RECOMMEND_POLICY

    eligible = coverage_status in {STATUS_READY, STATUS_CONSTRAINED}
    recommended_risk_budget_dollars = _safe_float(item.get("recommended_risk_budget_dollars")) or 0.0

    maintenance_policy = {
        "policy_type": "manual_position_maintenance_review_policy",
        "hold_review_rule": {
            "trigger": "scheduled_position_review",
            "cadence": "daily_or_each_new_signal_snapshot",
            "automatic_action": None,
        },
        "take_profit_review_rule": {
            "trigger": "profit_capture_review",
            "profit_capture_pct_of_planned_risk_or_credit": round(float(take_profit_capture_pct), 4),
            "automatic_action": None,
        },
        "risk_cut_review_rule": {
            "trigger": "risk_budget_drawdown_review",
            "risk_cut_pct_of_recommended_budget": round(float(risk_cut_pct_of_budget), 4),
            "risk_cut_budget_dollars": round(recommended_risk_budget_dollars * float(risk_cut_pct_of_budget), 2),
            "automatic_action": None,
        },
        "delta_drift_review_rule": {
            "trigger": "delta_drift_manual_review",
            "absolute_delta_change_threshold": round(float(delta_drift_threshold), 4),
            "starting_delta_reference": top_delta,
            "automatic_action": None,
        },
        "gamma_review_rule": {
            "trigger": "gamma_exposure_manual_review",
            "gamma_threshold": round(float(gamma_review_threshold), 4),
            "starting_gamma_reference": top_gamma,
            "automatic_action": None,
        },
        "vega_review_rule": {
            "trigger": "vega_exposure_manual_review",
            "vega_threshold": round(float(vega_review_threshold), 4),
            "starting_vega_reference": top_vega,
            "automatic_action": None,
        },
        "theta_review_rule": {
            "trigger": "theta_decay_manual_review",
            "theta_threshold": round(float(theta_review_threshold), 4),
            "starting_theta_reference": top_theta,
            "automatic_action": None,
        },
        "dte_review_rule": {
            "trigger": "time_to_expiration_manual_review",
            "dte_review_threshold": int(dte_review_threshold),
            "automatic_action": None,
        },
        "defense_review_rule": {
            "trigger": "manual_defense_review_only",
            "allowed_actions_for_review": ["hold", "reduce_risk", "roll_review", "close_review", "defer"],
            "automatic_action": None,
        },
    }

    return {
        "artifact_type": "position_maintenance_policy_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "position_maintenance_status": coverage_status,
        "eligible_for_position_maintenance_policy": eligible,
        "included_in_position_maintenance_policy": eligible,
        "manual_review_required": True,
        "maintenance_recommendation": maintenance_recommendation,
        "selected_strategy_family": _first_value(item, ("selected_strategy_family", "strategy_family")),
        "position_maintenance_score": position_maintenance_score,
        "position_sizing_score": position_sizing_score,
        "recommended_risk_budget_pct": _safe_float(item.get("recommended_risk_budget_pct")),
        "recommended_risk_budget_dollars": recommended_risk_budget_dollars,
        "recommended_risk_units": _safe_float(item.get("recommended_risk_units")),
        "quantity_recommendation": None,
        "quantity_recommendation_state": "review_only_policy_not_order_quantity",
        "maintenance_policy": maintenance_policy,
        "top_contract_symbol": item.get("top_contract_symbol") or item.get("contract_symbol"),
        "top_contract_expiration": item.get("top_contract_expiration") or item.get("expiration"),
        "top_contract_strike": item.get("top_contract_strike") or item.get("strike"),
        "top_contract_option_right": item.get("top_contract_option_right") or item.get("option_right"),
        "top_contract_delta": top_delta,
        "top_contract_gamma": top_gamma,
        "top_contract_theta": top_theta,
        "top_contract_vega": top_vega,
        "source_position_sizing_status": source_status,
        "source_position_sizing_rank": item.get("position_sizing_rank"),
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "sizing_review_flags": sorted(set(sizing_review_flags)),
        "portfolio_constraint_flags": sorted(set(portfolio_constraint_flags)),
        "portfolio_budget_flags": sorted(set(portfolio_budget_flags)),
        "maintenance_review_flags": sorted(set(maintenance_review_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": sorted(set(data_review_reasons + hard_block_reasons + risk_flags + constraint_flags + sizing_review_flags + portfolio_constraint_flags + portfolio_budget_flags + maintenance_review_flags)),
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _summary(*, items: Sequence[Mapping[str, Any]], included_items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in items)
    strategy_counts = Counter(str(item.get("selected_strategy_family")) for item in items if item.get("selected_strategy_family"))
    maintenance_strategy_counts = Counter(str(item.get("selected_strategy_family")) for item in included_items if item.get("selected_strategy_family"))
    risk_flag_counts = Counter(flag for item in items for flag in item.get("risk_flags", []))
    constraint_flag_counts = Counter(flag for item in items for flag in item.get("constraint_flags", []))
    sizing_review_flag_counts = Counter(flag for item in items for flag in item.get("sizing_review_flags", []))
    maintenance_review_flag_counts = Counter(flag for item in items for flag in item.get("maintenance_review_flags", []))
    portfolio_constraint_flag_counts = Counter(flag for item in items for flag in item.get("portfolio_constraint_flags", []))
    portfolio_budget_flag_counts = Counter(flag for item in items for flag in item.get("portfolio_budget_flags", []))
    data_review_counts = Counter(reason for item in items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in items for reason in item.get("hard_block_reasons", []))

    ready_count = coverage_counts.get(STATUS_READY, 0)
    constrained_count = coverage_counts.get(STATUS_CONSTRAINED, 0)
    data_review_count = coverage_counts.get(STATUS_DATA_REVIEW, 0)
    blocked_count = coverage_counts.get(STATUS_BLOCKED, 0)
    total_risk_budget = round(sum(_safe_float(item.get("recommended_risk_budget_dollars")) or 0.0 for item in included_items), 2)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(items),
        "source_position_sizing_recommendation_count": len(items),
        "position_maintenance_policy_count": len(included_items),
        "position_maintenance_symbol_count": len({item.get("symbol") for item in included_items if item.get("symbol")}),
        "ready_position_maintenance_symbol_count": ready_count,
        "constrained_position_maintenance_symbol_count": constrained_count,
        "data_review_symbol_count": data_review_count,
        "blocked_symbol_count": blocked_count,
        "needs_review_symbol_count": data_review_count + blocked_count,
        "manual_review_symbol_count": len(items),
        "total_maintenance_risk_budget_dollars": total_risk_budget,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_counts.items())),
        "position_maintenance_strategy_family_counts": dict(sorted(maintenance_strategy_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_flag_counts.items())),
        "sizing_review_flag_counts": dict(sorted(sizing_review_flag_counts.items())),
        "maintenance_review_flag_counts": dict(sorted(maintenance_review_flag_counts.items())),
        "portfolio_constraint_flag_counts": dict(sorted(portfolio_constraint_flag_counts.items())),
        "portfolio_budget_flag_counts": dict(sorted(portfolio_budget_flag_counts.items())),
        "data_review_reason_counts": dict(sorted(data_review_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
        "position_maintenance_exposure_preview": _aggregate_exposure(included_items),
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
        "source_position_sizing_recommendation_count": 0,
        "position_maintenance_policy_count": 0,
        "position_maintenance_symbol_count": 0,
        "ready_position_maintenance_symbol_count": 0,
        "constrained_position_maintenance_symbol_count": 0,
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "total_maintenance_risk_budget_dollars": 0.0,
        "coverage_status_counts": {},
        "strategy_family_counts": {},
        "position_maintenance_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "sizing_review_flag_counts": {},
        "maintenance_review_flag_counts": {},
        "portfolio_constraint_flag_counts": {},
        "portfolio_budget_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
        "position_maintenance_exposure_preview": _aggregate_exposure([]),
    }
    return {
        "artifact_type": "signalforge_position_maintenance_policy",
        "schema_version": POSITION_MAINTENANCE_POLICY_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "position_maintenance_policy",
        "adapter_type": "position_maintenance_policy_builder",
        "review_scope": "position_maintenance_policy_not_automatic_action_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [],
        "position_maintenance_policy_items": [],
        "position_maintenance_policy_queue": [],
        "ranked_position_maintenance_policies": [],
        "position_maintenance_policy_summary": summary,
        "thresholds": {},
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
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
