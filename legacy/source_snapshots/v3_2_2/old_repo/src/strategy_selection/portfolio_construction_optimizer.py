from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


PORTFOLIO_CONSTRUCTION_OPTIMIZER_SCHEMA_VERSION = "signalforge_portfolio_construction_optimizer.v1"

COVERED_CAPABILITIES = [
    "portfolio_construction_optimizer",
    "review_only_portfolio_construction_recommendation",
    "portfolio_exposure_budget_check",
    "optimizer_candidate_ranking",
    "portfolio_optimizer_not_position_sizing_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "portfolio_candidate_input",
]

PORTFOLIO_CANDIDATE_KEYS = (
    "ranked_optimizer_candidate_items",
    "optimizer_candidate_input_queue",
    "portfolio_candidate_input_items",
    "items",
    "data",
    "rows",
)

PORTFOLIO_POSITION_KEYS = (
    "positions",
    "open_positions",
    "portfolio_positions",
    "items",
    "data",
    "rows",
)

ELIGIBLE_PORTFOLIO_CANDIDATE_STATUSES = {
    "ready_for_portfolio_construction",
    "constrained_for_portfolio_construction",
}

STATUS_READY = "ready_for_portfolio_allocation_review"
STATUS_CONSTRAINED = "constrained_for_portfolio_allocation_review"
STATUS_DATA_REVIEW = "data_review_required"
STATUS_BLOCKED = "blocked_from_portfolio_construction"

RECOMMEND_INCLUDE = "include_candidate_for_portfolio_review"
RECOMMEND_INCLUDE_CONSTRAINED = "include_candidate_with_constraints_for_portfolio_review"
RECOMMEND_EXCLUDE_REVIEW = "exclude_candidate_data_review_required"
RECOMMEND_BLOCKED = "blocked_from_portfolio_review"


def build_signalforge_portfolio_construction_optimizer(
    portfolio_candidate_input_source: Mapping[str, Any] | Sequence[Any] | None,
    portfolio_source: Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    max_optimizer_candidate_count: int = 5,
    max_net_abs_delta: float = 1.00,
    max_gross_abs_delta: float = 2.00,
    max_gross_abs_gamma: float = 0.25,
    max_gross_abs_vega: float = 2.00,
    max_strategy_family_count: int = 3,
    min_portfolio_construction_score: float = 0.40,
) -> dict[str, Any]:
    """Build a review-only portfolio construction recommendation.

    This artifact selects and ranks optimizer-ready candidates under simple
    exposure and concentration budgets. It does not size positions, create order
    intent, call broker APIs, route/submit orders, model fills/slippage, or
    authorize automatic position maintenance.
    """

    source_artifacts = {
        "portfolio_candidate_input_source": _source_artifact_type(portfolio_candidate_input_source),
        "portfolio_source": _source_artifact_type(portfolio_source),
    }

    source_candidates = _extract_items(portfolio_candidate_input_source, PORTFOLIO_CANDIDATE_KEYS)
    if not source_candidates:
        return _blocked_result(["missing_optimizer_ready_candidates"], source_artifacts=source_artifacts)

    existing_positions = _extract_items(portfolio_source, PORTFOLIO_POSITION_KEYS)
    existing_exposure = _aggregate_position_exposure(existing_positions)

    normalized_candidates = [
        _normalize_candidate(candidate, min_portfolio_construction_score=min_portfolio_construction_score)
        for candidate in source_candidates
        if isinstance(candidate, Mapping)
    ]
    normalized_candidates = [candidate for candidate in normalized_candidates if candidate.get("symbol")]
    if not normalized_candidates:
        return _blocked_result(["missing_valid_portfolio_candidate_symbols"], source_artifacts=source_artifacts)

    ranked_source_candidates = sorted(
        normalized_candidates,
        key=lambda item: (
            _safe_float(item.get("portfolio_construction_score")) or -999.0,
            _safe_float(item.get("portfolio_candidate_score")) or -999.0,
            _safe_float(item.get("top_contract_candidate_score")) or -999.0,
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )

    optimized_items = _apply_portfolio_budgets(
        ranked_source_candidates,
        max_optimizer_candidate_count=max(1, int(max_optimizer_candidate_count)),
        max_net_abs_delta=float(max_net_abs_delta),
        max_gross_abs_delta=float(max_gross_abs_delta),
        max_gross_abs_gamma=float(max_gross_abs_gamma),
        max_gross_abs_vega=float(max_gross_abs_vega),
        max_strategy_family_count=max(1, int(max_strategy_family_count)),
        existing_exposure=existing_exposure,
    )

    for rank, item in enumerate(
        [item for item in optimized_items if item.get("included_in_portfolio_construction_review")], start=1
    ):
        item["portfolio_construction_rank"] = rank

    included_items = [item for item in optimized_items if item.get("included_in_portfolio_construction_review")]
    summary = _summary(
        source_candidates=normalized_candidates,
        optimized_items=optimized_items,
        included_items=included_items,
        existing_positions=existing_positions,
        existing_exposure=existing_exposure,
    )

    status = (
        "ready"
        if summary["portfolio_construction_candidate_count"] > 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_portfolio_construction_optimizer",
        "schema_version": PORTFOLIO_CONSTRUCTION_OPTIMIZER_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "portfolio_construction_optimizer",
        "adapter_type": "portfolio_construction_optimizer_builder",
        "review_scope": "portfolio_construction_recommendation_not_position_sizing_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "position_sizing_recommendation",
                "priority": "high",
                "recommendation": "Use portfolio construction recommendations and risk budgets to create review-only position sizing recommendations before any execution workflow.",
            }
        ],
        "portfolio_construction_items": optimized_items,
        "portfolio_construction_recommendation_queue": included_items,
        "ranked_portfolio_construction_items": included_items,
        "portfolio_construction_optimizer_summary": summary,
        "thresholds": {
            "max_optimizer_candidate_count": max(1, int(max_optimizer_candidate_count)),
            "max_net_abs_delta": float(max_net_abs_delta),
            "max_gross_abs_delta": float(max_gross_abs_delta),
            "max_gross_abs_gamma": float(max_gross_abs_gamma),
            "max_gross_abs_vega": float(max_gross_abs_vega),
            "max_strategy_family_count": max(1, int(max_strategy_family_count)),
            "min_portfolio_construction_score": float(min_portfolio_construction_score),
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


def _normalize_candidate(candidate: Mapping[str, Any], *, min_portfolio_construction_score: float) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(candidate, ("symbol", "underlying_symbol", "ticker")))
    source_status = _clean_text(
        _first_value(candidate, ("portfolio_candidate_input_status", "coverage_status", "source_status"))
    )
    risk_flags = _merged_list(candidate.get("risk_flags"))
    constraint_flags = _merged_list(candidate.get("constraint_flags"))
    portfolio_constraint_flags = _merged_list(candidate.get("portfolio_constraint_flags"))
    data_review_reasons = _merged_list(candidate.get("data_review_reasons"))
    hard_block_reasons = _merged_list(candidate.get("hard_block_reasons"))
    optimizer_review_flags: list[str] = []

    if source_status not in ELIGIBLE_PORTFOLIO_CANDIDATE_STATUSES:
        data_review_reasons.append("portfolio_candidate_not_ready_for_optimizer")

    portfolio_candidate_score = _safe_float(candidate.get("portfolio_candidate_score"))
    top_contract_score = _safe_float(candidate.get("top_contract_candidate_score"))
    base_score = portfolio_candidate_score if portfolio_candidate_score is not None else top_contract_score
    if base_score is None:
        data_review_reasons.append("missing_portfolio_candidate_score")
        base_score = 0.0

    constraint_penalty = min(
        0.25,
        0.04 * len(set(risk_flags + constraint_flags + portfolio_constraint_flags)),
    )
    score = round(max(0.0, min(1.0, float(base_score)) - constraint_penalty), 4)
    if score < float(min_portfolio_construction_score):
        optimizer_review_flags.append("below_minimum_portfolio_construction_score")

    if hard_block_reasons:
        coverage_status = STATUS_BLOCKED
        recommendation = RECOMMEND_BLOCKED
    elif data_review_reasons:
        coverage_status = STATUS_DATA_REVIEW
        recommendation = RECOMMEND_EXCLUDE_REVIEW
    elif optimizer_review_flags:
        coverage_status = STATUS_DATA_REVIEW
        recommendation = RECOMMEND_EXCLUDE_REVIEW
    elif risk_flags or constraint_flags or portfolio_constraint_flags or source_status == "constrained_for_portfolio_construction":
        coverage_status = STATUS_CONSTRAINED
        recommendation = RECOMMEND_INCLUDE_CONSTRAINED
    else:
        coverage_status = STATUS_READY
        recommendation = RECOMMEND_INCLUDE

    return {
        "artifact_type": "portfolio_construction_optimizer_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "portfolio_construction_status": coverage_status,
        "portfolio_recommendation": recommendation,
        "included_in_portfolio_construction_review": coverage_status in {STATUS_READY, STATUS_CONSTRAINED},
        "eligible_for_position_sizing_review": coverage_status in {STATUS_READY, STATUS_CONSTRAINED},
        "manual_review_required": True,
        "selected_strategy_family": _first_value(candidate, ("selected_strategy_family", "strategy_family")),
        "portfolio_construction_score": score,
        "portfolio_candidate_score": portfolio_candidate_score,
        "top_contract_candidate_score": top_contract_score,
        "top_contract_symbol": candidate.get("top_contract_symbol") or candidate.get("contract_symbol"),
        "top_contract_expiration": candidate.get("top_contract_expiration") or candidate.get("expiration"),
        "top_contract_strike": candidate.get("top_contract_strike") or candidate.get("strike"),
        "top_contract_option_right": candidate.get("top_contract_option_right") or candidate.get("option_right"),
        "top_contract_delta": _safe_float(candidate.get("top_contract_delta") or candidate.get("delta")),
        "top_contract_gamma": _safe_float(candidate.get("top_contract_gamma") or candidate.get("gamma")),
        "top_contract_theta": _safe_float(candidate.get("top_contract_theta") or candidate.get("theta")),
        "top_contract_vega": _safe_float(candidate.get("top_contract_vega") or candidate.get("vega")),
        "available_contract_candidate_count": _safe_int(candidate.get("available_contract_candidate_count")),
        "selected_contract_candidate_count": _safe_int(candidate.get("selected_contract_candidate_count")),
        "source_portfolio_candidate_input_status": source_status,
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "portfolio_constraint_flags": sorted(set(portfolio_constraint_flags)),
        "optimizer_review_flags": sorted(set(optimizer_review_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": sorted(
            set(data_review_reasons + hard_block_reasons + risk_flags + constraint_flags + portfolio_constraint_flags + optimizer_review_flags)
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


def _apply_portfolio_budgets(
    ranked_candidates: Sequence[Mapping[str, Any]],
    *,
    max_optimizer_candidate_count: int,
    max_net_abs_delta: float,
    max_gross_abs_delta: float,
    max_gross_abs_gamma: float,
    max_gross_abs_vega: float,
    max_strategy_family_count: int,
    existing_exposure: Mapping[str, float],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    output: list[dict[str, Any]] = []
    strategy_counts: Counter[str] = Counter()
    running_net_delta = float(existing_exposure.get("net_delta", 0.0))
    running_gross_abs_delta = float(existing_exposure.get("gross_abs_delta", 0.0))
    running_gross_abs_gamma = float(existing_exposure.get("gross_abs_gamma", 0.0))
    running_gross_abs_vega = float(existing_exposure.get("gross_abs_vega", 0.0))

    for candidate in ranked_candidates:
        item = dict(candidate)
        budget_flags: list[str] = []
        if not item.get("included_in_portfolio_construction_review"):
            item["portfolio_budget_flags"] = []
            output.append(item)
            continue

        if len(selected) >= max_optimizer_candidate_count:
            budget_flags.append("optimizer_candidate_count_limit")

        strategy_family = str(item.get("selected_strategy_family") or "unknown")
        if strategy_counts[strategy_family] >= max_strategy_family_count:
            budget_flags.append("strategy_family_concentration_limit")

        delta = _safe_float(item.get("top_contract_delta")) or 0.0
        gamma = _safe_float(item.get("top_contract_gamma")) or 0.0
        vega = _safe_float(item.get("top_contract_vega")) or 0.0

        next_net_delta = running_net_delta + delta
        next_gross_abs_delta = running_gross_abs_delta + abs(delta)
        next_gross_abs_gamma = running_gross_abs_gamma + abs(gamma)
        next_gross_abs_vega = running_gross_abs_vega + abs(vega)

        if abs(next_net_delta) > max_net_abs_delta:
            budget_flags.append("net_delta_budget_exceeded")
        if next_gross_abs_delta > max_gross_abs_delta:
            budget_flags.append("gross_delta_budget_exceeded")
        if next_gross_abs_gamma > max_gross_abs_gamma:
            budget_flags.append("gross_gamma_budget_exceeded")
        if next_gross_abs_vega > max_gross_abs_vega:
            budget_flags.append("gross_vega_budget_exceeded")

        item["portfolio_budget_flags"] = sorted(set(budget_flags))
        if budget_flags:
            item["coverage_status"] = STATUS_DATA_REVIEW
            item["portfolio_construction_status"] = STATUS_DATA_REVIEW
            item["portfolio_recommendation"] = "exclude_candidate_portfolio_budget_review_required"
            item["included_in_portfolio_construction_review"] = False
            item["eligible_for_position_sizing_review"] = False
            item["needs_review_reasons"] = sorted(set(_merged_list(item.get("needs_review_reasons")) + budget_flags))
            item["portfolio_constraint_flags"] = sorted(set(_merged_list(item.get("portfolio_constraint_flags")) + budget_flags))
        else:
            running_net_delta = next_net_delta
            running_gross_abs_delta = next_gross_abs_delta
            running_gross_abs_gamma = next_gross_abs_gamma
            running_gross_abs_vega = next_gross_abs_vega
            strategy_counts[strategy_family] += 1
            selected.append(item)

        output.append(item)

    return output


def _summary(
    *,
    source_candidates: Sequence[Mapping[str, Any]],
    optimized_items: Sequence[Mapping[str, Any]],
    included_items: Sequence[Mapping[str, Any]],
    existing_positions: Sequence[Any],
    existing_exposure: Mapping[str, float],
) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in optimized_items)
    strategy_family_counts = Counter(str(item.get("selected_strategy_family")) for item in optimized_items if item.get("selected_strategy_family"))
    included_strategy_family_counts = Counter(str(item.get("selected_strategy_family")) for item in included_items if item.get("selected_strategy_family"))
    risk_flag_counts = Counter(flag for item in optimized_items for flag in item.get("risk_flags", []))
    constraint_flag_counts = Counter(flag for item in optimized_items for flag in item.get("constraint_flags", []))
    portfolio_constraint_flag_counts = Counter(flag for item in optimized_items for flag in item.get("portfolio_constraint_flags", []))
    budget_flag_counts = Counter(flag for item in optimized_items for flag in item.get("portfolio_budget_flags", []))
    data_review_counts = Counter(reason for item in optimized_items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in optimized_items for reason in item.get("hard_block_reasons", []))
    optimizer_review_counts = Counter(reason for item in optimized_items for reason in item.get("optimizer_review_flags", []))

    ready_count = coverage_counts.get(STATUS_READY, 0)
    constrained_count = coverage_counts.get(STATUS_CONSTRAINED, 0)
    data_review_count = coverage_counts.get(STATUS_DATA_REVIEW, 0)
    blocked_count = coverage_counts.get(STATUS_BLOCKED, 0)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(optimized_items),
        "source_optimizer_candidate_count": len(source_candidates),
        "portfolio_position_count": len(existing_positions),
        "portfolio_construction_candidate_count": len(included_items),
        "portfolio_construction_symbol_count": len({item.get("symbol") for item in included_items if item.get("symbol")}),
        "ready_portfolio_construction_symbol_count": ready_count,
        "constrained_portfolio_construction_symbol_count": constrained_count,
        "data_review_symbol_count": data_review_count,
        "blocked_symbol_count": blocked_count,
        "needs_review_symbol_count": data_review_count + blocked_count,
        "manual_review_symbol_count": len(optimized_items),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_family_counts.items())),
        "portfolio_construction_strategy_family_counts": dict(sorted(included_strategy_family_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_flag_counts.items())),
        "portfolio_constraint_flag_counts": dict(sorted(portfolio_constraint_flag_counts.items())),
        "portfolio_budget_flag_counts": dict(sorted(budget_flag_counts.items())),
        "optimizer_review_flag_counts": dict(sorted(optimizer_review_counts.items())),
        "data_review_reason_counts": dict(sorted(data_review_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
        "existing_exposure_preview": dict(existing_exposure),
        "optimized_exposure_preview": _aggregate_candidate_exposure(included_items),
    }


def _aggregate_candidate_exposure(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(items),
        "gross_abs_delta": round(sum(abs(_safe_float(item.get("top_contract_delta")) or 0.0) for item in items), 4),
        "net_delta": round(sum(_safe_float(item.get("top_contract_delta")) or 0.0 for item in items), 4),
        "gross_abs_gamma": round(sum(abs(_safe_float(item.get("top_contract_gamma")) or 0.0) for item in items), 4),
        "gross_abs_vega": round(sum(abs(_safe_float(item.get("top_contract_vega")) or 0.0) for item in items), 4),
        "net_theta": round(sum(_safe_float(item.get("top_contract_theta")) or 0.0 for item in items), 4),
    }


def _aggregate_position_exposure(positions: Sequence[Any]) -> dict[str, float]:
    mapping_positions = [position for position in positions if isinstance(position, Mapping)]
    return {
        "position_count": float(len(mapping_positions)),
        "gross_abs_delta": round(sum(abs(_safe_float(position.get("delta")) or 0.0) for position in mapping_positions), 4),
        "net_delta": round(sum(_safe_float(position.get("delta")) or 0.0 for position in mapping_positions), 4),
        "gross_abs_gamma": round(sum(abs(_safe_float(position.get("gamma")) or 0.0) for position in mapping_positions), 4),
        "gross_abs_vega": round(sum(abs(_safe_float(position.get("vega")) or 0.0) for position in mapping_positions), 4),
        "net_theta": round(sum(_safe_float(position.get("theta")) or 0.0 for position in mapping_positions), 4),
    }


def _blocked_result(blocked_reasons: list[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": 0,
        "source_optimizer_candidate_count": 0,
        "portfolio_position_count": 0,
        "portfolio_construction_candidate_count": 0,
        "portfolio_construction_symbol_count": 0,
        "ready_portfolio_construction_symbol_count": 0,
        "constrained_portfolio_construction_symbol_count": 0,
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "coverage_status_counts": {},
        "strategy_family_counts": {},
        "portfolio_construction_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "portfolio_constraint_flag_counts": {},
        "portfolio_budget_flag_counts": {},
        "optimizer_review_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
        "existing_exposure_preview": _aggregate_position_exposure([]),
        "optimized_exposure_preview": _aggregate_candidate_exposure([]),
    }
    return {
        "artifact_type": "signalforge_portfolio_construction_optimizer",
        "schema_version": PORTFOLIO_CONSTRUCTION_OPTIMIZER_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "portfolio_construction_optimizer",
        "adapter_type": "portfolio_construction_optimizer_builder",
        "review_scope": "portfolio_construction_recommendation_not_position_sizing_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [],
        "portfolio_construction_items": [],
        "portfolio_construction_recommendation_queue": [],
        "ranked_portfolio_construction_items": [],
        "portfolio_construction_optimizer_summary": summary,
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
        if value is not None:
            return value
    return None


def _merged_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value if item is not None]
    return []


def _clean_symbol(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
