from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CONTRACT_CANDIDATE_REVIEW_EXPORT_SCHEMA_VERSION = "signalforge_contract_candidate_review_export.v1"

COVERED_CAPABILITIES = [
    "contract_candidate_review_export",
    "ranked_contract_candidate_review_queue",
    "human_contract_review_handoff",
    "contract_candidate_review_not_contract_selection_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "contract_candidate_scoring",
]

RANKED_CONTRACT_CANDIDATE_KEYS = (
    "ranked_contract_candidate_items",
    "contract_candidate_score_queue",
    "ranked_contract_candidates",
    "contract_candidate_review_queue",
    "items",
    "data",
    "rows",
)

CONTRACT_CANDIDATE_SCORING_ITEM_KEYS = (
    "contract_candidate_scoring_items",
    "contract_candidate_items",
    "items",
    "data",
    "rows",
)

READY_FOR_CONTRACT_CANDIDATE_REVIEW = "ready_for_contract_candidate_review"
CONSTRAINED_FOR_CONTRACT_CANDIDATE_REVIEW = "constrained_for_contract_candidate_review"
DATA_REVIEW_REQUIRED = "data_review_required"
BLOCKED_FROM_CONTRACT_CANDIDATE_REVIEW = "blocked_from_contract_candidate_review"


READY_SOURCE_STATUSES = {
    "ready_for_contract_candidate_review",
    "ready_for_contract_selection_evaluation",
    "ready_contract_candidate_review",
}

CONSTRAINED_SOURCE_STATUSES = {
    "constrained_for_contract_candidate_review",
    "constrained_for_contract_selection_evaluation",
    "constrained_contract_candidate_review",
}


def build_signalforge_contract_candidate_review_export(
    contract_candidate_scoring_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    max_contract_review_items: int = 25,
) -> dict[str, Any]:
    """Export ranked contract candidates into a human contract-review queue.

    This artifact consumes Contract Candidate Scoring output and prepares a
    ranked contract-review queue. It does not select a contract for trading,
    call broker APIs, route orders, submit orders, model fills/slippage, or
    authorize automatic strategy/parameter changes.
    """

    source_artifacts = {
        "contract_candidate_scoring_source": _source_artifact_type(contract_candidate_scoring_source),
    }
    source_summary = _source_summary(contract_candidate_scoring_source)
    ranked_candidates = _extract_items(contract_candidate_scoring_source, RANKED_CONTRACT_CANDIDATE_KEYS)
    scoring_items = _extract_items(contract_candidate_scoring_source, CONTRACT_CANDIDATE_SCORING_ITEM_KEYS)

    if not ranked_candidates and not scoring_items:
        return _blocked_result(["missing_contract_candidate_scoring_items"], source_artifacts=source_artifacts)

    review_items = [
        _build_review_item(candidate)
        for candidate in ranked_candidates
        if isinstance(candidate, Mapping)
    ]
    review_queue = _rank_review_items(review_items)[: max(0, int(max_contract_review_items))]
    selected_ids = {_item_identity(item) for item in review_queue}

    for item in review_items:
        if _item_identity(item) in selected_ids:
            item["included_in_contract_candidate_review_export"] = True
            item["contract_candidate_review_rank"] = _rank_for_identity(review_queue, _item_identity(item))
        else:
            item["included_in_contract_candidate_review_export"] = False
            item["contract_candidate_review_rank"] = None

    review_queue = [
        dict(item)
        for item in sorted(
            (item for item in review_items if item.get("included_in_contract_candidate_review_export") is True),
            key=lambda item: item.get("contract_candidate_review_rank") or 999999,
        )
    ]

    summary = _summary(
        review_items=review_items,
        review_queue=review_queue,
        scoring_items=scoring_items,
        source_summary=source_summary,
    )
    status = (
        "ready"
        if summary["contract_candidate_review_queue_count"] > 0
        and summary["blocked_symbol_count"] == 0
        and summary["data_review_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_contract_candidate_review_export",
        "schema_version": CONTRACT_CANDIDATE_REVIEW_EXPORT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "contract_candidate_review_export",
        "adapter_type": "contract_candidate_review_export_builder",
        "review_scope": "contract_candidate_human_review_queue_not_contract_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "contract_final_review_export",
                "priority": "medium",
                "recommendation": "Use human-reviewed contract candidates only after explicit review approval; do not route or submit orders from this artifact.",
            }
        ],
        "contract_candidate_review_items": review_items,
        "contract_candidate_review_queue": review_queue,
        "ranked_contract_candidate_review_items": review_queue,
        "contract_candidate_review_export_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "blocked_reasons": [],
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_review_item(candidate: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(candidate, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    contract_symbol = _clean_text(_first_value(candidate, ("contract_symbol", "option_symbol", "symbol")))
    source_status = _clean_text(
        _first_value(candidate, ("source_contract_candidate_scoring_status", "contract_candidate_scoring_status", "coverage_status"))
    ) or READY_FOR_CONTRACT_CANDIDATE_REVIEW

    risk_flags = _as_string_list(candidate.get("risk_flags"))
    constraint_flags = _as_string_list(candidate.get("constraint_flags"))
    data_review_reasons = _as_string_list(candidate.get("data_review_reasons"))
    hard_block_reasons = _as_string_list(candidate.get("hard_block_reasons"))
    review_reasons = _as_string_list(candidate.get("review_reasons"))

    if hard_block_reasons or source_status == BLOCKED_FROM_CONTRACT_CANDIDATE_REVIEW:
        export_status = "blocked"
        eligible = False
    elif data_review_reasons or (review_reasons and candidate.get("is_reviewable_contract_candidate") is False):
        export_status = DATA_REVIEW_REQUIRED
        eligible = False
    elif source_status in CONSTRAINED_SOURCE_STATUSES or risk_flags or constraint_flags:
        export_status = CONSTRAINED_FOR_CONTRACT_CANDIDATE_REVIEW
        eligible = True
    elif source_status in READY_SOURCE_STATUSES or candidate.get("is_reviewable_contract_candidate") is not False:
        export_status = READY_FOR_CONTRACT_CANDIDATE_REVIEW
        eligible = True
    else:
        export_status = DATA_REVIEW_REQUIRED
        eligible = False

    combined_review_reasons = sorted(
        set(data_review_reasons + hard_block_reasons + review_reasons + risk_flags + constraint_flags)
    )

    return {
        "artifact_type": "contract_candidate_review_export_item",
        "symbol": symbol,
        "contract_symbol": contract_symbol,
        "coverage_status": export_status,
        "contract_candidate_review_export_status": export_status,
        "source_contract_candidate_scoring_status": source_status,
        "eligible_for_contract_candidate_review_export": eligible,
        "included_in_contract_candidate_review_export": False,
        "source_contract_candidate_rank": _safe_int(candidate.get("contract_candidate_rank")),
        "symbol_contract_candidate_rank": _safe_int(candidate.get("symbol_contract_candidate_rank")),
        "contract_candidate_review_rank": None,
        "manual_review_required": True,
        "selected_strategy_family": _clean_text(candidate.get("selected_strategy_family")),
        "contract_score": _safe_float(candidate.get("contract_score")),
        "spread_score": _safe_float(candidate.get("spread_score")),
        "liquidity_score": _safe_float(candidate.get("liquidity_score")),
        "delta_score": _safe_float(candidate.get("delta_score")),
        "dte_score": _safe_float(candidate.get("dte_score")),
        "moneyness_score": _safe_float(candidate.get("moneyness_score")),
        "greek_score": _safe_float(candidate.get("greek_score")),
        "quote_date": _clean_text(candidate.get("quote_date")),
        "expiration": _clean_text(candidate.get("expiration")),
        "dte": _safe_int(candidate.get("dte")),
        "strike": _safe_float(candidate.get("strike")),
        "option_right": _clean_text(candidate.get("option_right")),
        "bid": _safe_float(candidate.get("bid")),
        "ask": _safe_float(candidate.get("ask")),
        "mid": _safe_float(candidate.get("mid")),
        "spread_pct": _safe_float(candidate.get("spread_pct")),
        "open_interest": _safe_int(candidate.get("open_interest")),
        "volume": _safe_int(candidate.get("volume")),
        "implied_volatility": _safe_float(candidate.get("implied_volatility")),
        "delta": _safe_float(candidate.get("delta")),
        "gamma": _safe_float(candidate.get("gamma")),
        "theta": _safe_float(candidate.get("theta")),
        "vega": _safe_float(candidate.get("vega")),
        "moneyness": _safe_float(candidate.get("moneyness")),
        "is_reviewable_contract_candidate": candidate.get("is_reviewable_contract_candidate") is not False,
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "review_reasons": sorted(set(review_reasons)),
        "needs_review_reasons": combined_review_reasons,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _rank_review_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    eligible = [dict(item) for item in items if item.get("eligible_for_contract_candidate_review_export") is True]
    return sorted(
        eligible,
        key=lambda item: (
            _safe_int(item.get("source_contract_candidate_rank")) is None,
            _safe_int(item.get("source_contract_candidate_rank")) or 999999,
            -(_safe_float(item.get("contract_score")) or -999.0),
            str(item.get("symbol") or ""),
            str(item.get("contract_symbol") or ""),
        ),
    )


def _rank_for_identity(ranked_items: Sequence[Mapping[str, Any]], identity: tuple[str, str | None]) -> int | None:
    for index, item in enumerate(ranked_items, start=1):
        if _item_identity(item) == identity:
            return index
    return None


def _item_identity(item: Mapping[str, Any]) -> tuple[str, str | None]:
    return (str(item.get("symbol") or "UNKNOWN"), _clean_text(item.get("contract_symbol")))


def _summary(
    *,
    review_items: Sequence[Mapping[str, Any]],
    review_queue: Sequence[Mapping[str, Any]],
    scoring_items: Sequence[Any],
    source_summary: Mapping[str, Any],
) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in review_items)
    source_status_counts = Counter(str(item.get("source_contract_candidate_scoring_status") or "unknown") for item in review_items)
    strategy_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in review_queue
        if item.get("selected_strategy_family")
    )
    all_strategy_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in review_items
        if item.get("selected_strategy_family")
    )
    risk_flag_counts = Counter(flag for item in review_items for flag in item.get("risk_flags", []))
    constraint_counts = Counter(flag for item in review_items for flag in item.get("constraint_flags", []))
    data_reason_counts = Counter(reason for item in review_items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in review_items for reason in item.get("hard_block_reasons", []))
    review_reason_counts = Counter(reason for item in review_items for reason in item.get("review_reasons", []))

    queue_symbols = {str(item.get("symbol")) for item in review_queue if item.get("symbol")}
    ready_symbols = {
        str(item.get("symbol"))
        for item in review_items
        if item.get("coverage_status") == READY_FOR_CONTRACT_CANDIDATE_REVIEW and item.get("symbol")
    }
    constrained_symbols = {
        str(item.get("symbol"))
        for item in review_items
        if item.get("coverage_status") == CONSTRAINED_FOR_CONTRACT_CANDIDATE_REVIEW and item.get("symbol")
    }

    source_data_review = _safe_int(source_summary.get("data_review_symbol_count")) or 0
    source_blocked = _safe_int(source_summary.get("blocked_symbol_count")) or 0
    source_needs_review = _safe_int(source_summary.get("needs_review_symbol_count")) or source_data_review + source_blocked
    source_scoreable = _safe_int(source_summary.get("scoreable_symbol_count"))
    source_option_rows = _safe_int(source_summary.get("option_row_count")) or 0

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len({str(item.get("symbol")) for item in review_items if item.get("symbol")}) or (_safe_int(source_summary.get("symbol_count")) or 0),
        "source_scoreable_symbol_count": source_scoreable if source_scoreable is not None else 0,
        "contract_candidate_count": len(review_items),
        "contract_candidate_review_symbol_count": len(queue_symbols),
        "ready_contract_candidate_review_symbol_count": len(ready_symbols - constrained_symbols),
        "constrained_contract_candidate_review_symbol_count": len(constrained_symbols),
        "contract_candidate_review_queue_count": len(review_queue),
        "ranked_contract_candidate_review_count": len(review_queue),
        "ready_contract_candidate_review_item_count": coverage_counts.get(READY_FOR_CONTRACT_CANDIDATE_REVIEW, 0),
        "constrained_contract_candidate_review_item_count": coverage_counts.get(CONSTRAINED_FOR_CONTRACT_CANDIDATE_REVIEW, 0),
        "data_review_symbol_count": source_data_review,
        "blocked_symbol_count": source_blocked,
        "needs_review_symbol_count": source_needs_review,
        "manual_review_symbol_count": len(queue_symbols),
        "source_contract_candidate_scoring_item_count": len(scoring_items),
        "source_ranked_contract_candidate_count": _safe_int(source_summary.get("ranked_contract_candidate_count")) or len(review_items),
        "option_row_count": source_option_rows,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "source_contract_candidate_scoring_status_counts": dict(sorted(source_status_counts.items())),
        "contract_candidate_review_strategy_family_counts": dict(sorted(strategy_counts.items())),
        "all_contract_candidate_strategy_family_counts": dict(sorted(all_strategy_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
        "contract_review_reason_counts": dict(sorted(review_reason_counts.items())),
    }


def _source_summary(source: Any) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        summary = source.get("contract_candidate_scoring_summary")
        if isinstance(summary, Mapping):
            return summary
    return {}


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
    summary = {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": 0,
        "source_scoreable_symbol_count": 0,
        "contract_candidate_count": 0,
        "contract_candidate_review_symbol_count": 0,
        "ready_contract_candidate_review_symbol_count": 0,
        "constrained_contract_candidate_review_symbol_count": 0,
        "contract_candidate_review_queue_count": 0,
        "ranked_contract_candidate_review_count": 0,
        "ready_contract_candidate_review_item_count": 0,
        "constrained_contract_candidate_review_item_count": 0,
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "source_contract_candidate_scoring_item_count": 0,
        "source_ranked_contract_candidate_count": 0,
        "option_row_count": 0,
        "coverage_status_counts": {},
        "source_contract_candidate_scoring_status_counts": {},
        "contract_candidate_review_strategy_family_counts": {},
        "all_contract_candidate_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
        "contract_review_reason_counts": {},
    }
    return {
        "artifact_type": "signalforge_contract_candidate_review_export",
        "schema_version": CONTRACT_CANDIDATE_REVIEW_EXPORT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "contract_candidate_review_export",
        "adapter_type": "contract_candidate_review_export_builder",
        "review_scope": "contract_candidate_human_review_queue_not_contract_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "contract_candidate_review_items": [],
        "contract_candidate_review_queue": [],
        "ranked_contract_candidate_review_items": [],
        "contract_candidate_review_export_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
