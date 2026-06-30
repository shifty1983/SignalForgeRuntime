from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


PORTFOLIO_CANDIDATE_INPUT_SCHEMA_VERSION = "signalforge_portfolio_candidate_input.v1"

COVERED_CAPABILITIES = [
    "portfolio_candidate_input",
    "optimizer_ready_candidate_normalization",
    "portfolio_constraint_precheck",
    "contract_candidate_to_portfolio_handoff",
    "portfolio_input_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "contract_candidate_scoring",
]

CONTRACT_CANDIDATE_KEYS = (
    "contract_candidate_score_queue",
    "ranked_contract_candidate_items",
    "contract_candidates",
    "items",
    "data",
    "rows",
)

CONTRACT_SCORING_ITEM_KEYS = (
    "contract_candidate_scoring_items",
    "scoring_items",
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

STATUS_READY = "ready_for_portfolio_construction"
STATUS_CONSTRAINED = "constrained_for_portfolio_construction"
STATUS_DATA_REVIEW = "data_review_required"
STATUS_BLOCKED = "blocked_from_portfolio_construction"

ELIGIBLE_CONTRACT_CANDIDATE_STATUSES = {
    "ready_for_contract_candidate_review",
    "constrained_for_contract_candidate_review",
}


def build_signalforge_portfolio_candidate_input(
    contract_candidate_scoring_source: Mapping[str, Any] | Sequence[Any] | None,
    portfolio_source: Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    max_candidates_per_symbol: int = 1,
    max_portfolio_candidate_count: int = 10,
    max_existing_positions_per_symbol: int = 1,
    max_abs_delta_per_candidate: float = 0.60,
    max_abs_vega_per_candidate: float = 1.00,
) -> dict[str, Any]:
    """Normalize ranked contract candidates into optimizer-ready portfolio inputs.

    This artifact is a portfolio-construction handoff. It does not construct a
    final portfolio, size a position, call broker APIs, route/submit orders,
    model fills or slippage, or authorize automatic maintenance actions.
    """

    source_artifacts = {
        "contract_candidate_scoring_source": _source_artifact_type(contract_candidate_scoring_source),
        "portfolio_source": _source_artifact_type(portfolio_source),
    }

    contract_candidates = _extract_items(contract_candidate_scoring_source, CONTRACT_CANDIDATE_KEYS)
    scoring_items = _extract_items(contract_candidate_scoring_source, CONTRACT_SCORING_ITEM_KEYS)
    if not contract_candidates:
        return _blocked_result(["missing_ranked_contract_candidates"], source_artifacts=source_artifacts)

    portfolio_positions = _extract_items(portfolio_source, PORTFOLIO_POSITION_KEYS)
    position_index = _index_positions(portfolio_positions)
    scoring_item_index = _index_scoring_items(scoring_items)

    grouped_candidates: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in contract_candidates:
        if not isinstance(candidate, Mapping):
            continue
        symbol = _clean_symbol(_first_value(candidate, ("symbol", "underlying_symbol", "ticker")))
        if not symbol:
            continue
        grouped_candidates[symbol].append(candidate)

    portfolio_items = [
        _build_portfolio_candidate_item(
            symbol=symbol,
            candidates=candidates,
            scoring_item=scoring_item_index.get(symbol),
            existing_positions=position_index.get(symbol, []),
            max_candidates_per_symbol=max(1, int(max_candidates_per_symbol)),
            max_existing_positions_per_symbol=max(0, int(max_existing_positions_per_symbol)),
            max_abs_delta_per_candidate=float(max_abs_delta_per_candidate),
            max_abs_vega_per_candidate=float(max_abs_vega_per_candidate),
        )
        for symbol, candidates in sorted(grouped_candidates.items())
    ]

    optimizer_ready_items = [
        item for item in portfolio_items if item.get("eligible_for_portfolio_construction") is True
    ]
    optimizer_ready_items = sorted(
        optimizer_ready_items,
        key=lambda item: (
            _safe_float(item.get("portfolio_candidate_score")) or -999.0,
            _safe_float(item.get("top_contract_candidate_score")) or -999.0,
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )[: max(1, int(max_portfolio_candidate_count))]

    for rank, item in enumerate(optimizer_ready_items, start=1):
        item["portfolio_candidate_rank"] = rank

    summary = _summary(
        portfolio_items=portfolio_items,
        optimizer_ready_items=optimizer_ready_items,
        contract_candidates=contract_candidates,
        portfolio_positions=portfolio_positions,
    )

    status = (
        "ready"
        if summary["optimizer_ready_candidate_count"] > 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_portfolio_candidate_input",
        "schema_version": PORTFOLIO_CANDIDATE_INPUT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "portfolio_candidate_input",
        "adapter_type": "portfolio_candidate_input_builder",
        "review_scope": "optimizer_input_not_portfolio_construction_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "portfolio_construction_optimizer",
                "priority": "high",
                "recommendation": "Use optimizer-ready candidates, portfolio constraints, and exposure limits to build a review-only portfolio construction recommendation.",
            }
        ],
        "portfolio_candidate_input_items": portfolio_items,
        "optimizer_candidate_input_queue": optimizer_ready_items,
        "ranked_optimizer_candidate_items": optimizer_ready_items,
        "portfolio_candidate_input_summary": summary,
        "thresholds": {
            "max_candidates_per_symbol": max(1, int(max_candidates_per_symbol)),
            "max_portfolio_candidate_count": max(1, int(max_portfolio_candidate_count)),
            "max_existing_positions_per_symbol": max(0, int(max_existing_positions_per_symbol)),
            "max_abs_delta_per_candidate": float(max_abs_delta_per_candidate),
            "max_abs_vega_per_candidate": float(max_abs_vega_per_candidate),
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


def _build_portfolio_candidate_item(
    *,
    symbol: str,
    candidates: Sequence[Mapping[str, Any]],
    scoring_item: Mapping[str, Any] | None,
    existing_positions: Sequence[Mapping[str, Any]],
    max_candidates_per_symbol: int,
    max_existing_positions_per_symbol: int,
    max_abs_delta_per_candidate: float,
    max_abs_vega_per_candidate: float,
) -> dict[str, Any]:
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (
            _safe_float(candidate.get("contract_score")) or -999.0,
            _safe_float(candidate.get("liquidity_score")) or -999.0,
            -(_safe_float(candidate.get("spread_pct")) or 999.0),
            str(candidate.get("contract_symbol") or ""),
        ),
        reverse=True,
    )
    selected_candidates = [dict(candidate) for candidate in sorted_candidates[:max_candidates_per_symbol]]
    top_candidate = selected_candidates[0] if selected_candidates else {}

    source_status = _clean_text(
        _first_value(
            top_candidate,
            ("source_contract_candidate_scoring_status", "coverage_status", "contract_candidate_scoring_status"),
        )
    ) or _clean_text(scoring_item.get("coverage_status") if scoring_item else None)

    risk_flags = _merged_list(
        top_candidate.get("risk_flags") if isinstance(top_candidate, Mapping) else None,
        scoring_item.get("risk_flags") if isinstance(scoring_item, Mapping) else None,
    )
    constraint_flags = _merged_list(
        top_candidate.get("constraint_flags") if isinstance(top_candidate, Mapping) else None,
        scoring_item.get("constraint_flags") if isinstance(scoring_item, Mapping) else None,
    )
    data_review_reasons = _merged_list(scoring_item.get("data_review_reasons") if isinstance(scoring_item, Mapping) else None)
    hard_block_reasons = _merged_list(scoring_item.get("hard_block_reasons") if isinstance(scoring_item, Mapping) else None)
    portfolio_constraint_flags: list[str] = []

    if source_status not in ELIGIBLE_CONTRACT_CANDIDATE_STATUSES:
        data_review_reasons.append("contract_candidate_not_ready_for_portfolio_construction")
    if not selected_candidates:
        data_review_reasons.append("missing_selected_contract_candidate")
    if len(existing_positions) > max_existing_positions_per_symbol:
        data_review_reasons.append("symbol_existing_position_limit_exceeded")
    elif len(existing_positions) == max_existing_positions_per_symbol and max_existing_positions_per_symbol >= 0:
        portfolio_constraint_flags.append("symbol_at_existing_position_limit")

    top_delta = _safe_float(top_candidate.get("delta") if isinstance(top_candidate, Mapping) else None)
    top_vega = _safe_float(top_candidate.get("vega") if isinstance(top_candidate, Mapping) else None)
    if top_delta is not None and abs(top_delta) > max_abs_delta_per_candidate:
        portfolio_constraint_flags.append("candidate_delta_exposure_review")
    if top_vega is not None and abs(top_vega) > max_abs_vega_per_candidate:
        portfolio_constraint_flags.append("candidate_vega_exposure_review")

    if hard_block_reasons:
        coverage_status = STATUS_BLOCKED
    elif data_review_reasons:
        coverage_status = STATUS_DATA_REVIEW
    elif risk_flags or constraint_flags or portfolio_constraint_flags or source_status == "constrained_for_contract_candidate_review":
        coverage_status = STATUS_CONSTRAINED
    else:
        coverage_status = STATUS_READY

    eligible = coverage_status in {STATUS_READY, STATUS_CONSTRAINED}
    top_contract_score = _safe_float(top_candidate.get("contract_score") if isinstance(top_candidate, Mapping) else None) or 0.0
    expected_value_score = _safe_float(
        _first_value(
            scoring_item or {},
            ("selected_expected_value_score", "expected_value_score", "risk_adjusted_expected_value_score"),
        )
    )
    expected_value_component = 0.50 if expected_value_score is None else _bounded_score(expected_value_score)
    constraint_penalty = min(0.25, 0.05 * len(set(risk_flags + constraint_flags + portfolio_constraint_flags)))
    portfolio_candidate_score = round(max(0.0, 0.65 * top_contract_score + 0.35 * expected_value_component - constraint_penalty), 4)

    selected_strategy_family = _first_value(
        top_candidate,
        ("selected_strategy_family", "strategy_family"),
    ) or (scoring_item.get("selected_strategy_family") if isinstance(scoring_item, Mapping) else None)

    return {
        "artifact_type": "portfolio_candidate_input_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "portfolio_candidate_input_status": coverage_status,
        "eligible_for_portfolio_construction": eligible,
        "manual_review_required": True,
        "selected_strategy_family": selected_strategy_family,
        "selected_expected_value_score": expected_value_score,
        "selected_expected_value_state": scoring_item.get("selected_expected_value_state") if isinstance(scoring_item, Mapping) else None,
        "portfolio_candidate_score": portfolio_candidate_score,
        "top_contract_candidate_score": top_contract_score,
        "top_contract_symbol": top_candidate.get("contract_symbol") if isinstance(top_candidate, Mapping) else None,
        "top_contract_expiration": top_candidate.get("expiration") if isinstance(top_candidate, Mapping) else None,
        "top_contract_strike": top_candidate.get("strike") if isinstance(top_candidate, Mapping) else None,
        "top_contract_option_right": top_candidate.get("option_right") if isinstance(top_candidate, Mapping) else None,
        "top_contract_delta": top_delta,
        "top_contract_gamma": _safe_float(top_candidate.get("gamma") if isinstance(top_candidate, Mapping) else None),
        "top_contract_theta": _safe_float(top_candidate.get("theta") if isinstance(top_candidate, Mapping) else None),
        "top_contract_vega": top_vega,
        "top_contract_spread_pct": _safe_float(top_candidate.get("spread_pct") if isinstance(top_candidate, Mapping) else None),
        "selected_contract_candidates": selected_candidates,
        "available_contract_candidate_count": len(candidates),
        "selected_contract_candidate_count": len(selected_candidates),
        "existing_position_count": len(existing_positions),
        "source_contract_candidate_scoring_status": source_status,
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "portfolio_constraint_flags": sorted(set(portfolio_constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": sorted(set(data_review_reasons + hard_block_reasons + risk_flags + constraint_flags + portfolio_constraint_flags)),
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


def _summary(
    *,
    portfolio_items: Sequence[Mapping[str, Any]],
    optimizer_ready_items: Sequence[Mapping[str, Any]],
    contract_candidates: Sequence[Any],
    portfolio_positions: Sequence[Any],
) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in portfolio_items)
    strategy_family_counts = Counter(str(item.get("selected_strategy_family")) for item in portfolio_items if item.get("selected_strategy_family"))
    optimizer_strategy_family_counts = Counter(str(item.get("selected_strategy_family")) for item in optimizer_ready_items if item.get("selected_strategy_family"))
    risk_flag_counts = Counter(flag for item in portfolio_items for flag in item.get("risk_flags", []))
    constraint_flag_counts = Counter(flag for item in portfolio_items for flag in item.get("constraint_flags", []))
    portfolio_constraint_flag_counts = Counter(flag for item in portfolio_items for flag in item.get("portfolio_constraint_flags", []))
    data_review_counts = Counter(reason for item in portfolio_items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in portfolio_items for reason in item.get("hard_block_reasons", []))

    ready_count = coverage_counts.get(STATUS_READY, 0)
    constrained_count = coverage_counts.get(STATUS_CONSTRAINED, 0)
    data_review_count = coverage_counts.get(STATUS_DATA_REVIEW, 0)
    blocked_count = coverage_counts.get(STATUS_BLOCKED, 0)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(portfolio_items),
        "contract_candidate_count": len(contract_candidates),
        "portfolio_position_count": len(portfolio_positions),
        "portfolio_candidate_symbol_count": ready_count + constrained_count,
        "optimizer_ready_symbol_count": len({item.get("symbol") for item in optimizer_ready_items if item.get("symbol")}),
        "optimizer_ready_candidate_count": len(optimizer_ready_items),
        "ready_portfolio_candidate_symbol_count": ready_count,
        "constrained_portfolio_candidate_symbol_count": constrained_count,
        "data_review_symbol_count": data_review_count,
        "blocked_symbol_count": blocked_count,
        "needs_review_symbol_count": data_review_count + blocked_count,
        "manual_review_symbol_count": len(portfolio_items),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "strategy_family_counts": dict(sorted(strategy_family_counts.items())),
        "optimizer_strategy_family_counts": dict(sorted(optimizer_strategy_family_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_flag_counts.items())),
        "portfolio_constraint_flag_counts": dict(sorted(portfolio_constraint_flag_counts.items())),
        "data_review_reason_counts": dict(sorted(data_review_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
        "aggregate_exposure_preview": _aggregate_exposure(optimizer_ready_items),
    }


def _aggregate_exposure(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(items),
        "gross_abs_delta": round(sum(abs(_safe_float(item.get("top_contract_delta")) or 0.0) for item in items), 4),
        "net_delta": round(sum(_safe_float(item.get("top_contract_delta")) or 0.0 for item in items), 4),
        "gross_abs_vega": round(sum(abs(_safe_float(item.get("top_contract_vega")) or 0.0) for item in items), 4),
        "net_theta": round(sum(_safe_float(item.get("top_contract_theta")) or 0.0 for item in items), 4),
        "gross_abs_gamma": round(sum(abs(_safe_float(item.get("top_contract_gamma")) or 0.0) for item in items), 4),
    }


def _blocked_result(blocked_reasons: list[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": 0,
        "contract_candidate_count": 0,
        "portfolio_position_count": 0,
        "portfolio_candidate_symbol_count": 0,
        "optimizer_ready_symbol_count": 0,
        "optimizer_ready_candidate_count": 0,
        "ready_portfolio_candidate_symbol_count": 0,
        "constrained_portfolio_candidate_symbol_count": 0,
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "coverage_status_counts": {},
        "strategy_family_counts": {},
        "optimizer_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "portfolio_constraint_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
        "aggregate_exposure_preview": {
            "candidate_count": 0,
            "gross_abs_delta": 0.0,
            "net_delta": 0.0,
            "gross_abs_vega": 0.0,
            "net_theta": 0.0,
            "gross_abs_gamma": 0.0,
        },
    }
    return {
        "artifact_type": "signalforge_portfolio_candidate_input",
        "schema_version": PORTFOLIO_CANDIDATE_INPUT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "portfolio_candidate_input",
        "adapter_type": "portfolio_candidate_input_builder",
        "review_scope": "optimizer_input_not_portfolio_construction_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [],
        "portfolio_candidate_input_items": [],
        "optimizer_candidate_input_queue": [],
        "ranked_optimizer_candidate_items": [],
        "portfolio_candidate_input_summary": summary,
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


def _index_scoring_items(items: Sequence[Any]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        symbol = _clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker")))
        if symbol and symbol not in index:
            index[symbol] = item
    return index


def _index_positions(positions: Sequence[Any]) -> dict[str, list[Mapping[str, Any]]]:
    index: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for position in positions:
        if not isinstance(position, Mapping):
            continue
        symbol = _clean_symbol(_first_value(position, ("symbol", "underlying_symbol", "ticker")))
        if symbol:
            index[symbol].append(position)
    return index


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


def _merged_list(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        if isinstance(value, str):
            merged.append(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                if item is not None:
                    merged.append(str(item))
    return merged


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


def _bounded_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
