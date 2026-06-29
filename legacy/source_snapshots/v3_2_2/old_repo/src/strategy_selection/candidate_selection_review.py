from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CANDIDATE_SELECTION_REVIEW_SCHEMA_VERSION = "signalforge_candidate_selection_review.v1"

COVERED_CAPABILITIES = [
    "candidate_selection_review",
    "risk_adjusted_ev_candidate_ranking",
    "final_review_handoff",
    "candidate_review_not_contract_selection_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "expected_value_scoring",
]

EXPECTED_VALUE_ITEM_KEYS = (
    "expected_value_items",
    "ev_items",
    "items",
    "data",
    "rows",
)

READY_FOR_CANDIDATE_REVIEW = "ready_for_candidate_review"
CONSTRAINED_FOR_CANDIDATE_REVIEW = "constrained_for_candidate_review"
DATA_REVIEW_REQUIRED = "data_review_required"
BLOCKED_FROM_CANDIDATE_REVIEW = "blocked_from_candidate_review"
NOT_RECOMMENDED_FOR_CANDIDATE_REVIEW = "not_recommended_for_candidate_review"

POSITIVE_EV_STATE = "positive_expected_value_candidate"
MARGINAL_EV_STATE = "marginal_expected_value_candidate"

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
]


def build_signalforge_candidate_selection_review(
    expected_value_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    max_candidates: int = 25,
) -> dict[str, Any]:
    """Rank positive/marginal EV candidates for final human review.

    This artifact consumes risk-adjusted expected value scoring and creates a
    candidate-review queue. It does not select option contracts, call broker APIs,
    route orders, submit orders, model fills, model slippage, or authorize any
    automatic strategy change.
    """

    ev_items = _extract_items(expected_value_source, EXPECTED_VALUE_ITEM_KEYS)
    source_artifacts = {"expected_value_source": _source_artifact_type(expected_value_source)}

    blocked_reasons: list[str] = []
    if not ev_items:
        blocked_reasons.append("missing_expected_value_items")

    if blocked_reasons:
        return _blocked_result(blocked_reasons, source_artifacts=source_artifacts)

    items = [_build_candidate_review_item(item) for item in ev_items if isinstance(item, Mapping)]
    ranked_candidates = _rank_candidate_items(items)[: max(0, int(max_candidates))]
    ranked_symbols = {str(item.get("symbol")) for item in ranked_candidates}

    for item in items:
        if item.get("symbol") in ranked_symbols:
            item["selected_for_final_review"] = True
            item["candidate_review_rank"] = _rank_for_symbol(ranked_candidates, str(item.get("symbol")))
        else:
            item["selected_for_final_review"] = False
            item["candidate_review_rank"] = None

    summary = _summary(items)
    status = "ready" if summary["data_review_symbol_count"] == 0 and summary["blocked_symbol_count"] == 0 else "needs_review"

    return {
        "artifact_type": "signalforge_candidate_selection_review",
        "schema_version": CANDIDATE_SELECTION_REVIEW_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "candidate_selection_review",
        "adapter_type": "candidate_selection_review_builder",
        "review_scope": "ranked_candidate_review_not_contract_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "candidate_final_review_export",
                "priority": "high",
                "recommendation": "Export ranked positive/marginal EV candidates into a final review queue before any contract selection or execution workflow.",
            }
        ],
        "candidate_selection_review_items": items,
        "candidate_review_items": items,
        "candidate_selection_review_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_candidate_review_item(ev_item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(ev_item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    ev_handoff = _clean_text(
        _first_value(
            ev_item,
            (
                "expected_value_handoff_status",
                "candidate_handoff_status",
                "handoff_status",
                "coverage_status",
            ),
        )
    ) or DATA_REVIEW_REQUIRED

    coverage_status = _clean_text(ev_item.get("coverage_status")) or "unknown"
    ev_state = _clean_text(ev_item.get("expected_value_state")) or _clean_text(ev_item.get("best_expected_value_state")) or "unknown"
    best_family = _clean_text(ev_item.get("best_strategy_family"))
    best_score = _safe_float(ev_item.get("best_expected_value_score"))
    candidates = _candidate_scores(ev_item.get("candidate_strategy_family_scores"))

    risk_flags = _as_string_list(ev_item.get("risk_flags"))
    constraint_flags = _as_string_list(ev_item.get("constraint_flags"))
    data_review_reasons = _as_string_list(ev_item.get("data_review_reasons"))
    hard_block_reasons = _as_string_list(ev_item.get("hard_block_reasons"))
    needs_review_reasons = _as_string_list(ev_item.get("needs_review_reasons"))

    if ev_handoff == DATA_REVIEW_REQUIRED or ev_item.get("data_review_required") is True:
        candidate_review_status = "data_review_required"
        final_review_handoff = DATA_REVIEW_REQUIRED
        selected_family = None
        selected_score = None
        selected_ev_state = "not_scored_data_review_required"
    elif ev_handoff == BLOCKED_FROM_CANDIDATE_REVIEW or ev_item.get("hard_blocked") is True:
        candidate_review_status = "blocked"
        final_review_handoff = "blocked_from_final_review"
        selected_family = None
        selected_score = None
        selected_ev_state = "not_scored_blocked"
    elif ev_handoff in {READY_FOR_CANDIDATE_REVIEW, CONSTRAINED_FOR_CANDIDATE_REVIEW} and best_family:
        candidate_review_status = "constrained_candidate_review" if ev_handoff == CONSTRAINED_FOR_CANDIDATE_REVIEW or risk_flags or constraint_flags else "ready_candidate_review"
        final_review_handoff = "ready_for_final_review" if candidate_review_status == "ready_candidate_review" else "constrained_for_final_review"
        selected_family = best_family
        selected_score = best_score
        selected_ev_state = ev_state
    else:
        candidate_review_status = "not_recommended"
        final_review_handoff = NOT_RECOMMENDED_FOR_CANDIDATE_REVIEW
        selected_family = best_family
        selected_score = best_score
        selected_ev_state = ev_state

    review_reasons = sorted(
        set(
            data_review_reasons
            + hard_block_reasons
            + needs_review_reasons
            + risk_flags
            + constraint_flags
        )
    )

    return {
        "artifact_type": "candidate_selection_review_item",
        "symbol": symbol,
        "coverage_status": candidate_review_status,
        "candidate_review_status": candidate_review_status,
        "final_review_handoff_status": final_review_handoff,
        "selected_for_final_review": False,
        "candidate_review_rank": None,
        "expected_value_state": ev_state,
        "expected_value_handoff_status": ev_handoff,
        "ev_coverage_status": coverage_status,
        "ev_scoreable": ev_item.get("ev_scoreable") is True,
        "risk_adjustment_required": ev_item.get("risk_adjustment_required") is True,
        "data_review_required": candidate_review_status == "data_review_required",
        "hard_blocked": candidate_review_status == "blocked",
        "manual_review_required": True,
        "selected_strategy_family": selected_family,
        "selected_expected_value_score": selected_score,
        "selected_expected_value_state": selected_ev_state,
        "best_strategy_family": best_family,
        "best_expected_value_score": best_score,
        "best_expected_value_state": _clean_text(ev_item.get("best_expected_value_state")),
        "candidate_strategy_family_scores": candidates,
        "candidate_count": len(candidates),
        "macro_regime": ev_item.get("macro_regime"),
        "weekly_planning_label": ev_item.get("weekly_planning_label"),
        "asset_behavior_state": ev_item.get("asset_behavior_state"),
        "options_behavior_state": ev_item.get("options_behavior_state"),
        "premium_bias": ev_item.get("premium_bias"),
        "strategy_environment_bias": ev_item.get("strategy_environment_bias"),
        "favored_strategy_families": _as_string_list(ev_item.get("favored_strategy_families")),
        "allowed_strategy_families": _as_string_list(ev_item.get("allowed_strategy_families")),
        "discouraged_strategy_families": _as_string_list(ev_item.get("discouraged_strategy_families")),
        "blocked_strategy_families": _as_string_list(ev_item.get("blocked_strategy_families")),
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": review_reasons,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _candidate_scores(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    scores = [dict(item) for item in value if isinstance(item, Mapping)]
    return sorted(
        scores,
        key=lambda item: (
            _safe_float(item.get("risk_adjusted_expected_value_score")) if _safe_float(item.get("risk_adjusted_expected_value_score")) is not None else -1.0,
            -_family_order_index(str(item.get("strategy_family") or "")),
        ),
        reverse=True,
    )


def _rank_candidate_items(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    reviewable = [
        item
        for item in items
        if item.get("final_review_handoff_status") in {"ready_for_final_review", "constrained_for_final_review"}
    ]
    return sorted(
        reviewable,
        key=lambda item: (
            _safe_float(item.get("selected_expected_value_score")) if _safe_float(item.get("selected_expected_value_score")) is not None else -1.0,
            1 if item.get("final_review_handoff_status") == "ready_for_final_review" else 0,
            -_family_order_index(str(item.get("selected_strategy_family") or "")),
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )


def _rank_for_symbol(ranked_candidates: Sequence[Mapping[str, Any]], symbol: str) -> int | None:
    for index, item in enumerate(ranked_candidates, start=1):
        if str(item.get("symbol")) == symbol:
            return index
    return None


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in items)
    handoff_counts = Counter(str(item.get("final_review_handoff_status") or "unknown") for item in items)
    family_counts = Counter(str(item.get("selected_strategy_family")) for item in items if item.get("selected_strategy_family"))
    ev_state_counts = Counter(str(item.get("selected_expected_value_state") or "unknown") for item in items)
    risk_flag_counts = Counter(flag for item in items for flag in item.get("risk_flags", []))
    constraint_counts = Counter(flag for item in items for flag in item.get("constraint_flags", []))
    data_reason_counts = Counter(reason for item in items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in items for reason in item.get("hard_block_reasons", []))
    selected_items = [item for item in items if item.get("selected_for_final_review") is True]
    ranked_candidate_count = len(selected_items)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(items),
        "ready_candidate_review_symbol_count": coverage_counts.get("ready_candidate_review", 0),
        "constrained_candidate_review_symbol_count": coverage_counts.get("constrained_candidate_review", 0),
        "candidate_review_symbol_count": coverage_counts.get("ready_candidate_review", 0) + coverage_counts.get("constrained_candidate_review", 0),
        "selected_for_final_review_symbol_count": ranked_candidate_count,
        "data_review_symbol_count": coverage_counts.get("data_review_required", 0),
        "blocked_symbol_count": coverage_counts.get("blocked", 0),
        "not_recommended_symbol_count": coverage_counts.get("not_recommended", 0),
        "needs_review_symbol_count": coverage_counts.get("data_review_required", 0) + coverage_counts.get("blocked", 0),
        "manual_review_symbol_count": sum(1 for item in items if item.get("manual_review_required") is True),
        "ranked_candidate_count": ranked_candidate_count,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "final_review_handoff_counts": dict(sorted(handoff_counts.items())),
        "selected_strategy_family_counts": dict(sorted(family_counts.items())),
        "selected_expected_value_state_counts": dict(sorted(ev_state_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
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


def _family_order_index(family: str) -> int:
    if family in FAMILY_ORDER:
        return FAMILY_ORDER.index(family)
    return 999


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
        "artifact_type": "signalforge_candidate_selection_review",
        "schema_version": CANDIDATE_SELECTION_REVIEW_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "candidate_selection_review",
        "adapter_type": "candidate_selection_review_builder",
        "review_scope": "ranked_candidate_review_not_contract_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "candidate_selection_review_items": [],
        "candidate_review_items": [],
        "candidate_selection_review_summary": {
            "covered_capabilities": list(COVERED_CAPABILITIES),
            "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
            "symbol_count": 0,
            "ready_candidate_review_symbol_count": 0,
            "constrained_candidate_review_symbol_count": 0,
            "candidate_review_symbol_count": 0,
            "selected_for_final_review_symbol_count": 0,
            "data_review_symbol_count": 0,
            "blocked_symbol_count": 0,
            "not_recommended_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "manual_review_symbol_count": 0,
            "ranked_candidate_count": 0,
            "coverage_status_counts": {},
            "final_review_handoff_counts": {},
            "selected_strategy_family_counts": {},
            "selected_expected_value_state_counts": {},
            "risk_flag_counts": {},
            "constraint_flag_counts": {},
            "data_review_reason_counts": {},
            "hard_block_reason_counts": {},
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
