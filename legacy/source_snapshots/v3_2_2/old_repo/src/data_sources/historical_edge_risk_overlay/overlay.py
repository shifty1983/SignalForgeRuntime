from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ARTIFACT_TYPE = "signalforge_historical_edge_risk_overlay"
SCHEMA_VERSION = "signalforge_historical_edge_risk_overlay.v1"
CONTRACT = "historical_edge_risk_overlay"

COVERED_CAPABILITIES = [
    "historical_edge_risk_overlay",
    "risk_adjusted_historical_edge_interpretation",
    "strategy_adjusted_edge_risk_review",
    "maintenance_trigger_risk_overlay",
    "historical_edge_risk_overlay_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "historical_edge_validation",
    "quantconnect_replay_result_import_validator",
    "position_maintenance_policy",
]

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]


def build_signalforge_historical_edge_risk_overlay(
    historical_edge_validation_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []

    if not isinstance(historical_edge_validation_source, Mapping):
        blocked_reasons.append("missing_historical_edge_validation_source")
        historical_edge_validation_source = {}

    if historical_edge_validation_source.get("artifact_type") != "signalforge_historical_edge_validation":
        blocked_reasons.append("invalid_historical_edge_validation_artifact_type")

    contract_summary = _mapping(historical_edge_validation_source.get("contract_outcome_edge_summary"))
    portfolio_summary = _mapping(historical_edge_validation_source.get("portfolio_replay_edge_summary"))
    maintenance_summary = _mapping(historical_edge_validation_source.get("maintenance_trigger_edge_summary"))
    source_summary = _mapping(historical_edge_validation_source.get("historical_edge_validation_summary"))

    if not contract_summary:
        blocked_reasons.append("missing_contract_outcome_edge_summary")
    if not portfolio_summary:
        blocked_reasons.append("missing_portfolio_replay_edge_summary")
    if not maintenance_summary:
        blocked_reasons.append("missing_maintenance_trigger_edge_summary")

    risk_overlay_summary = _risk_overlay_summary(
        contract_summary=contract_summary,
        portfolio_summary=portfolio_summary,
        maintenance_summary=maintenance_summary,
    )

    is_ready = not blocked_reasons
    status = "ready" if is_ready else "blocked"

    return {
        "adapter_type": "historical_edge_risk_overlay_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": status,
        "is_ready": is_ready,
        "requires_manual_approval": True,
        "review_scope": "historical_edge_risk_overlay_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),

        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),

        "source_artifacts": {
            "historical_edge_validation_source": _source_artifact_type(historical_edge_validation_source),
        },

        "request_id": source_summary.get("request_id"),
        "replay_start": source_summary.get("replay_start"),
        "replay_end": source_summary.get("replay_end"),
        "symbol_count": source_summary.get("symbol_count"),
        "replay_candidate_count": source_summary.get("replay_candidate_count"),
        "table_row_counts": source_summary.get("table_row_counts", {}),

        "risk_overlay_summary": risk_overlay_summary,
        "risk_overlay_state": risk_overlay_summary.get("risk_overlay_state"),
        "risk_overlay_review_status": risk_overlay_summary.get("risk_overlay_review_status"),
        "risk_adjusted_edge_score": risk_overlay_summary.get("risk_adjusted_edge_score"),
        "risk_overlay_flags": risk_overlay_summary.get("risk_overlay_flags", []),
        "live_readiness_state": risk_overlay_summary.get("live_readiness_state"),

        "historical_edge_state": contract_summary.get("historical_edge_state"),
        "historical_edge_score": contract_summary.get("historical_edge_score"),
        "average_strategy_adjusted_return": contract_summary.get("average_strategy_adjusted_return"),
        "strategy_adjusted_win_rate": contract_summary.get("strategy_adjusted_win_rate"),
        "average_strategy_adjusted_max_adverse_excursion": contract_summary.get(
            "average_strategy_adjusted_max_adverse_excursion"
        ),
        "average_strategy_adjusted_max_favorable_excursion": contract_summary.get(
            "average_strategy_adjusted_max_favorable_excursion"
        ),
        "maintenance_trigger_rate": maintenance_summary.get("trigger_rate"),
        "maintenance_trigger_type_counts": maintenance_summary.get("trigger_type_counts", {}),

        "next_build_recommendations": _next_build_recommendations(risk_overlay_summary),

        "order_intent": None,
        "broker_order_id": None,
        "portfolio_action": None,
        "position_size": None,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }


def _risk_overlay_summary(
    *,
    contract_summary: Mapping[str, Any],
    portfolio_summary: Mapping[str, Any],
    maintenance_summary: Mapping[str, Any],
) -> dict[str, Any]:
    historical_edge_state = str(contract_summary.get("historical_edge_state") or "")
    historical_edge_score = _safe_float(contract_summary.get("historical_edge_score"))

    average_strategy_adjusted_return = _safe_float(
        contract_summary.get("average_strategy_adjusted_return")
    )
    strategy_adjusted_win_rate = _safe_float(
        contract_summary.get("strategy_adjusted_win_rate", contract_summary.get("win_rate"))
    )
    average_strategy_adjusted_max_adverse_excursion = _safe_float(
        contract_summary.get("average_strategy_adjusted_max_adverse_excursion")
    )
    average_strategy_adjusted_max_favorable_excursion = _safe_float(
        contract_summary.get("average_strategy_adjusted_max_favorable_excursion")
    )

    trigger_rate = _safe_float(maintenance_summary.get("trigger_rate"))
    triggered_count = int(_safe_float(maintenance_summary.get("triggered_count")))
    trigger_type_counts = dict(_mapping(maintenance_summary.get("trigger_type_counts")))

    max_abs_net_delta = _safe_float(portfolio_summary.get("max_abs_net_delta"))
    max_gross_abs_gamma = _safe_float(portfolio_summary.get("max_gross_abs_gamma"))
    max_gross_abs_vega = _safe_float(portfolio_summary.get("max_gross_abs_vega"))

    flags: list[str] = []
    review_reasons: list[str] = []
    penalties: dict[str, float] = {}

    positive_edge = (
        average_strategy_adjusted_return > 0
        and strategy_adjusted_win_rate >= 0.50
        and historical_edge_state == "historical_positive_edge_candidate"
    )

    if positive_edge:
        flags.append("positive_strategy_adjusted_edge")

    if average_strategy_adjusted_max_adverse_excursion <= -1.0:
        flags.append("severe_strategy_adjusted_adverse_excursion")
        review_reasons.append("Strategy-adjusted adverse excursion is severe.")
        penalties["severe_adverse_excursion_penalty"] = 0.35
    elif average_strategy_adjusted_max_adverse_excursion <= -0.50:
        flags.append("moderate_strategy_adjusted_adverse_excursion")
        review_reasons.append("Strategy-adjusted adverse excursion is elevated.")
        penalties["moderate_adverse_excursion_penalty"] = 0.15

    if trigger_rate >= 1.0:
        flags.append("full_maintenance_trigger_review")
        review_reasons.append("Every replayed candidate triggered maintenance review.")
        penalties["maintenance_trigger_penalty"] = 0.25
    elif trigger_rate >= 0.50:
        flags.append("elevated_maintenance_trigger_review")
        review_reasons.append("Maintenance trigger rate is elevated.")
        penalties["maintenance_trigger_penalty"] = 0.15

    if "risk_cut_review" in trigger_type_counts:
        flags.append("risk_cut_review_triggered")
        review_reasons.append("Risk-cut review was triggered.")

    if max_abs_net_delta > 1.0:
        flags.append("high_net_delta_exposure_review")
        review_reasons.append("Max absolute net delta is elevated.")
        penalties["net_delta_penalty"] = 0.10

    if max_gross_abs_gamma > 0.05:
        flags.append("high_gamma_exposure_review")
        review_reasons.append("Max gross absolute gamma is elevated.")
        penalties["gamma_penalty"] = 0.10

    adverse_to_return_ratio = _safe_ratio(
        abs(average_strategy_adjusted_max_adverse_excursion),
        abs(average_strategy_adjusted_return),
    )

    if adverse_to_return_ratio >= 2.0 and average_strategy_adjusted_return > 0:
        flags.append("adverse_excursion_exceeds_return_by_two_x")
        review_reasons.append("Average adverse excursion is more than two times average adjusted return.")
        penalties.setdefault("adverse_to_return_ratio_penalty", 0.10)

    risk_penalty_total = min(sum(penalties.values()), 1.0)
    risk_adjusted_edge_score = _clamp(historical_edge_score - risk_penalty_total, 0.0, 1.0)

    severe_risk = any(
        flag in flags
        for flag in [
            "severe_strategy_adjusted_adverse_excursion",
            "full_maintenance_trigger_review",
            "risk_cut_review_triggered",
        ]
    )

    if positive_edge and severe_risk:
        risk_overlay_state = "positive_strategy_adjusted_edge_with_severe_risk_review"
        risk_overlay_review_status = "needs_review"
        live_readiness_state = "not_live_ready_without_scaleout"
    elif positive_edge and review_reasons:
        risk_overlay_state = "positive_strategy_adjusted_edge_with_risk_review"
        risk_overlay_review_status = "needs_review"
        live_readiness_state = "not_live_ready_without_review"
    elif positive_edge:
        risk_overlay_state = "risk_adjusted_positive_edge_candidate"
        risk_overlay_review_status = "ready_for_scaleout_review"
        live_readiness_state = "not_live_ready_without_scaleout"
    elif historical_edge_state == "historical_mixed_edge_candidate":
        risk_overlay_state = "mixed_edge_with_risk_review"
        risk_overlay_review_status = "needs_review"
        live_readiness_state = "not_live_ready"
    else:
        risk_overlay_state = "negative_or_unproven_edge"
        risk_overlay_review_status = "needs_review"
        live_readiness_state = "not_live_ready"

    return {
        "risk_overlay_state": risk_overlay_state,
        "risk_overlay_review_status": risk_overlay_review_status,
        "live_readiness_state": live_readiness_state,
        "risk_adjusted_edge_score": _round(risk_adjusted_edge_score),
        "raw_historical_edge_score": _round(historical_edge_score),
        "risk_penalty_total": _round(risk_penalty_total),
        "risk_penalties": {key: _round(value) for key, value in sorted(penalties.items())},
        "risk_overlay_flags": list(dict.fromkeys(flags)),
        "risk_overlay_flag_count": len(list(dict.fromkeys(flags))),
        "risk_overlay_review_reasons": list(dict.fromkeys(review_reasons)),
        "positive_strategy_adjusted_edge": positive_edge,
        "severe_risk_review_required": severe_risk,
        "average_strategy_adjusted_return": _round(average_strategy_adjusted_return),
        "strategy_adjusted_win_rate": _round(strategy_adjusted_win_rate),
        "average_strategy_adjusted_max_adverse_excursion": _round(
            average_strategy_adjusted_max_adverse_excursion
        ),
        "average_strategy_adjusted_max_favorable_excursion": _round(
            average_strategy_adjusted_max_favorable_excursion
        ),
        "adverse_to_return_ratio": _round(adverse_to_return_ratio),
        "maintenance_trigger_rate": _round(trigger_rate),
        "maintenance_triggered_count": triggered_count,
        "maintenance_trigger_type_counts": trigger_type_counts,
        "max_abs_net_delta": _round(max_abs_net_delta),
        "max_gross_abs_gamma": _round(max_gross_abs_gamma),
        "max_gross_abs_vega": _round(max_gross_abs_vega),
        "thresholds": {
            "severe_adverse_excursion_lte": -1.0,
            "moderate_adverse_excursion_lte": -0.50,
            "full_maintenance_trigger_rate_gte": 1.0,
            "elevated_maintenance_trigger_rate_gte": 0.50,
            "high_net_delta_exposure_gt": 1.0,
            "high_gamma_exposure_gt": 0.05,
            "adverse_to_return_ratio_review_gte": 2.0,
        },
    }


def _next_build_recommendations(risk_overlay_summary: Mapping[str, Any]) -> list[dict[str, str]]:
    state = str(risk_overlay_summary.get("risk_overlay_state") or "")

    if state == "positive_strategy_adjusted_edge_with_severe_risk_review":
        return [
            {
                "capability": "risk_adjusted_position_maintenance_policy",
                "priority": "high",
                "recommendation": "Use the positive strategy-adjusted edge, but require risk-cut and adverse-excursion review before scaleout.",
            },
            {
                "capability": "historical_replay_scaleout",
                "priority": "high",
                "recommendation": "Replay across more dates, symbols, regimes, and option candidates before treating the edge as robust.",
            },
        ]

    return [
        {
            "capability": "historical_replay_scaleout",
            "priority": "high",
            "recommendation": "Expand replay coverage before using edge evidence for live workflow design.",
        }
    ]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or "provided_unknown_artifact")
    if source is None:
        return "missing"
    return type(source).__name__


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _round(value: float) -> float:
    return round(float(value), 6)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)
