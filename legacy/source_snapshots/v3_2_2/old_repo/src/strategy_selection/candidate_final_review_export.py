from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CANDIDATE_FINAL_REVIEW_EXPORT_SCHEMA_VERSION = "signalforge_candidate_final_review_export.v1"

COVERED_CAPABILITIES = [
    "candidate_final_review_export",
    "ranked_final_review_queue",
    "human_review_handoff",
    "final_review_export_not_contract_selection_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "candidate_selection_review",
]

CANDIDATE_REVIEW_ITEM_KEYS = (
    "candidate_selection_review_items",
    "candidate_review_items",
    "candidate_final_review_items",
    "items",
    "data",
    "rows",
)

READY_FOR_FINAL_REVIEW = "ready_for_final_review"
CONSTRAINED_FOR_FINAL_REVIEW = "constrained_for_final_review"
DATA_REVIEW_REQUIRED = "data_review_required"
BLOCKED_FROM_FINAL_REVIEW = "blocked_from_final_review"
NOT_RECOMMENDED_FOR_CANDIDATE_REVIEW = "not_recommended_for_candidate_review"


RANKABLE_FINAL_REVIEW_HANDOFFS = {
    READY_FOR_FINAL_REVIEW,
    CONSTRAINED_FOR_FINAL_REVIEW,
}


def build_signalforge_candidate_final_review_export(
    candidate_review_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    max_final_review_items: int = 25,
) -> dict[str, Any]:
    """Export ranked EV-positive candidates into a final human-review queue.

    This artifact consumes Candidate Selection Review and produces a final
    review export. It does not choose contracts, call broker APIs, route orders,
    submit orders, model fills, model slippage, or authorize any automatic
    strategy change.
    """

    source_items = _extract_items(candidate_review_source, CANDIDATE_REVIEW_ITEM_KEYS)
    source_artifacts = {"candidate_review_source": _source_artifact_type(candidate_review_source)}

    blocked_reasons: list[str] = []
    if not source_items:
        blocked_reasons.append("missing_candidate_review_items")

    if blocked_reasons:
        return _blocked_result(blocked_reasons, source_artifacts=source_artifacts)

    audit_items = [_build_export_audit_item(item) for item in source_items if isinstance(item, Mapping)]
    final_review_queue = _rank_final_review_items(audit_items)[: max(0, int(max_final_review_items))]
    selected_ids = {_item_identity(item) for item in final_review_queue}

    for item in audit_items:
        if _item_identity(item) in selected_ids:
            item["included_in_final_review_export"] = True
            item["final_review_rank"] = _rank_for_identity(final_review_queue, _item_identity(item))
        else:
            item["included_in_final_review_export"] = False
            item["final_review_rank"] = None

    final_review_queue = [dict(item) for item in sorted(
        (item for item in audit_items if item.get("included_in_final_review_export") is True),
        key=lambda item: item.get("final_review_rank") or 999999,
    )]

    summary = _summary(audit_items, final_review_queue)
    status = "ready" if summary["final_review_queue_count"] > 0 and summary["blocked_symbol_count"] == 0 and summary["data_review_symbol_count"] == 0 else "needs_review"

    return {
        "artifact_type": "signalforge_candidate_final_review_export",
        "schema_version": CANDIDATE_FINAL_REVIEW_EXPORT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "candidate_final_review_export",
        "adapter_type": "candidate_final_review_export_builder",
        "review_scope": "final_human_review_queue_not_contract_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "contract_selection_readiness",
                "priority": "high",
                "recommendation": "Use final-review-approved candidates to evaluate option-contract readiness before any contract selection or execution workflow.",
            }
        ],
        "candidate_final_review_items": audit_items,
        "final_review_queue": final_review_queue,
        "ranked_final_review_items": final_review_queue,
        "candidate_final_review_export_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_export_audit_item(candidate_item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(candidate_item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    final_handoff = _clean_text(
        _first_value(
            candidate_item,
            (
                "final_review_handoff_status",
                "candidate_review_handoff_status",
                "handoff_status",
                "coverage_status",
            ),
        )
    ) or DATA_REVIEW_REQUIRED

    selected_for_final_review = candidate_item.get("selected_for_final_review") is True
    candidate_review_rank = _safe_int(candidate_item.get("candidate_review_rank"))
    selected_family = _clean_text(candidate_item.get("selected_strategy_family"))
    selected_score = _safe_float(candidate_item.get("selected_expected_value_score"))
    selected_ev_state = _clean_text(candidate_item.get("selected_expected_value_state")) or "unknown"

    risk_flags = _as_string_list(candidate_item.get("risk_flags"))
    constraint_flags = _as_string_list(candidate_item.get("constraint_flags"))
    data_review_reasons = _as_string_list(candidate_item.get("data_review_reasons"))
    hard_block_reasons = _as_string_list(candidate_item.get("hard_block_reasons"))
    needs_review_reasons = _as_string_list(candidate_item.get("needs_review_reasons"))

    if final_handoff == DATA_REVIEW_REQUIRED or candidate_item.get("data_review_required") is True:
        export_status = DATA_REVIEW_REQUIRED
        eligible_for_final_review_export = False
    elif final_handoff == BLOCKED_FROM_FINAL_REVIEW or candidate_item.get("hard_blocked") is True:
        export_status = "blocked"
        eligible_for_final_review_export = False
    elif final_handoff in RANKABLE_FINAL_REVIEW_HANDOFFS and selected_for_final_review and selected_family:
        export_status = "constrained_final_review" if final_handoff == CONSTRAINED_FOR_FINAL_REVIEW or risk_flags or constraint_flags else "ready_final_review"
        eligible_for_final_review_export = True
    else:
        export_status = "not_recommended"
        eligible_for_final_review_export = False

    combined_review_reasons = sorted(
        set(
            data_review_reasons
            + hard_block_reasons
            + needs_review_reasons
            + risk_flags
            + constraint_flags
        )
    )

    return {
        "artifact_type": "candidate_final_review_export_item",
        "symbol": symbol,
        "coverage_status": export_status,
        "final_review_export_status": export_status,
        "final_review_handoff_status": final_handoff,
        "eligible_for_final_review_export": eligible_for_final_review_export,
        "included_in_final_review_export": False,
        "candidate_review_rank": candidate_review_rank,
        "final_review_rank": None,
        "manual_review_required": True,
        "selected_strategy_family": selected_family,
        "selected_expected_value_score": selected_score,
        "selected_expected_value_state": selected_ev_state,
        "expected_value_state": _clean_text(candidate_item.get("expected_value_state")),
        "expected_value_handoff_status": _clean_text(candidate_item.get("expected_value_handoff_status")),
        "best_strategy_family": _clean_text(candidate_item.get("best_strategy_family")),
        "best_expected_value_score": _safe_float(candidate_item.get("best_expected_value_score")),
        "candidate_strategy_family_scores": _candidate_scores(candidate_item.get("candidate_strategy_family_scores")),
        "candidate_count": _safe_int(candidate_item.get("candidate_count")) or len(_candidate_scores(candidate_item.get("candidate_strategy_family_scores"))),
        "macro_regime": candidate_item.get("macro_regime"),
        "weekly_planning_label": candidate_item.get("weekly_planning_label"),
        "asset_behavior_state": candidate_item.get("asset_behavior_state"),
        "options_behavior_state": candidate_item.get("options_behavior_state"),
        "premium_bias": candidate_item.get("premium_bias"),
        "strategy_environment_bias": candidate_item.get("strategy_environment_bias"),
        "favored_strategy_families": _as_string_list(candidate_item.get("favored_strategy_families")),
        "allowed_strategy_families": _as_string_list(candidate_item.get("allowed_strategy_families")),
        "discouraged_strategy_families": _as_string_list(candidate_item.get("discouraged_strategy_families")),
        "blocked_strategy_families": _as_string_list(candidate_item.get("blocked_strategy_families")),
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": combined_review_reasons,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _rank_final_review_items(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    eligible = [item for item in items if item.get("eligible_for_final_review_export") is True]
    return sorted(
        eligible,
        key=lambda item: (
            -(_safe_int(item.get("candidate_review_rank")) or 999999),
            _safe_float(item.get("selected_expected_value_score")) if _safe_float(item.get("selected_expected_value_score")) is not None else -1.0,
            1 if item.get("final_review_export_status") == "ready_final_review" else 0,
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )


def _rank_for_identity(ranked_items: Sequence[Mapping[str, Any]], identity: tuple[str, str | None]) -> int | None:
    for index, item in enumerate(ranked_items, start=1):
        if _item_identity(item) == identity:
            return index
    return None


def _item_identity(item: Mapping[str, Any]) -> tuple[str, str | None]:
    return (str(item.get("symbol") or "UNKNOWN"), _clean_text(item.get("selected_strategy_family")))


def _summary(audit_items: Sequence[Mapping[str, Any]], final_review_queue: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in audit_items)
    handoff_counts = Counter(str(item.get("final_review_handoff_status") or "unknown") for item in audit_items)
    selected_family_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in final_review_queue
        if item.get("selected_strategy_family")
    )
    all_selected_family_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in audit_items
        if item.get("selected_strategy_family")
    )
    ev_state_counts = Counter(str(item.get("selected_expected_value_state") or "unknown") for item in audit_items)
    risk_flag_counts = Counter(flag for item in audit_items for flag in item.get("risk_flags", []))
    constraint_counts = Counter(flag for item in audit_items for flag in item.get("constraint_flags", []))
    data_reason_counts = Counter(reason for item in audit_items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in audit_items for reason in item.get("hard_block_reasons", []))
    final_queue_count = len(final_review_queue)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(audit_items),
        "ready_final_review_symbol_count": coverage_counts.get("ready_final_review", 0),
        "constrained_final_review_symbol_count": coverage_counts.get("constrained_final_review", 0),
        "candidate_final_review_symbol_count": coverage_counts.get("ready_final_review", 0) + coverage_counts.get("constrained_final_review", 0),
        "selected_for_final_review_symbol_count": final_queue_count,
        "final_review_queue_count": final_queue_count,
        "ranked_final_review_count": final_queue_count,
        "data_review_symbol_count": coverage_counts.get("data_review_required", 0),
        "blocked_symbol_count": coverage_counts.get("blocked", 0),
        "not_recommended_symbol_count": coverage_counts.get("not_recommended", 0),
        "needs_review_symbol_count": coverage_counts.get("data_review_required", 0) + coverage_counts.get("blocked", 0),
        "manual_review_symbol_count": sum(1 for item in audit_items if item.get("manual_review_required") is True),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "final_review_handoff_counts": dict(sorted(handoff_counts.items())),
        "final_review_strategy_family_counts": dict(sorted(selected_family_counts.items())),
        "selected_strategy_family_counts": dict(sorted(all_selected_family_counts.items())),
        "selected_expected_value_state_counts": dict(sorted(ev_state_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
    }


def _candidate_scores(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


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


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
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
        "artifact_type": "signalforge_candidate_final_review_export",
        "schema_version": CANDIDATE_FINAL_REVIEW_EXPORT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "candidate_final_review_export",
        "adapter_type": "candidate_final_review_export_builder",
        "review_scope": "final_human_review_queue_not_contract_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "candidate_final_review_items": [],
        "final_review_queue": [],
        "ranked_final_review_items": [],
        "candidate_final_review_export_summary": {
            "covered_capabilities": list(COVERED_CAPABILITIES),
            "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
            "symbol_count": 0,
            "ready_final_review_symbol_count": 0,
            "constrained_final_review_symbol_count": 0,
            "candidate_final_review_symbol_count": 0,
            "selected_for_final_review_symbol_count": 0,
            "final_review_queue_count": 0,
            "ranked_final_review_count": 0,
            "data_review_symbol_count": 0,
            "blocked_symbol_count": 0,
            "not_recommended_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "manual_review_symbol_count": 0,
            "coverage_status_counts": {},
            "final_review_handoff_counts": {},
            "final_review_strategy_family_counts": {},
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
