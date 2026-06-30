from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CONTRACT_FINAL_DECISION_RECORD_SCHEMA_VERSION = "signalforge_contract_final_decision_record.v1"

COVERED_CAPABILITIES = [
    "contract_final_decision_record",
    "explicit_human_contract_decision_capture",
    "approve_reject_defer_contract_review_record",
    "contract_decision_record_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "contract_final_review_export",
]

CONTRACT_FINAL_REVIEW_QUEUE_KEYS = (
    "ranked_contract_final_review_items",
    "contract_final_review_queue",
    "contract_final_review_items",
    "items",
    "data",
    "rows",
)

CONTRACT_FINAL_DECISION_KEYS = (
    "contract_final_decisions",
    "contract_decisions",
    "decisions",
    "review_decisions",
    "items",
    "data",
    "rows",
)

APPROVED_CONTRACT_FINAL_DECISION = "approved_contract_final_decision"
REJECTED_CONTRACT_FINAL_DECISION = "rejected_contract_final_decision"
DEFERRED_CONTRACT_FINAL_DECISION = "deferred_contract_final_decision"
PENDING_CONTRACT_FINAL_DECISION = "pending_contract_final_decision"
INVALID_CONTRACT_FINAL_DECISION = "invalid_contract_final_decision"
DATA_REVIEW_REQUIRED = "data_review_required"
BLOCKED_FROM_CONTRACT_FINAL_DECISION = "blocked_from_contract_final_decision"

APPROVE_VALUES = {"approve", "approved", "accept", "accepted", "yes"}
REJECT_VALUES = {"reject", "rejected", "decline", "declined", "no"}
DEFER_VALUES = {"defer", "deferred", "hold", "pending", "review_later", "needs_review"}


def build_signalforge_contract_final_decision_record(
    contract_final_review_source: Mapping[str, Any] | Sequence[Any] | None,
    decision_source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    """Record explicit human approve/reject/defer decisions for final contract review items.

    This artifact only records decisions. It does not create order intent, call broker APIs,
    route or submit orders, model fills/slippage, or authorize automatic strategy/parameter changes.
    """

    source_artifacts = {
        "contract_final_review_source": _source_artifact_type(contract_final_review_source),
        "decision_source": _source_artifact_type(decision_source),
    }
    source_summary = _source_summary(contract_final_review_source)
    review_items = _extract_items(contract_final_review_source, CONTRACT_FINAL_REVIEW_QUEUE_KEYS)

    if not review_items:
        return _blocked_result(["missing_contract_final_review_items"], source_artifacts=source_artifacts)

    decisions = _decision_index(_extract_items(decision_source, CONTRACT_FINAL_DECISION_KEYS))
    decision_items = [
        _build_decision_item(item, decisions)
        for item in review_items
        if isinstance(item, Mapping)
    ]

    decision_records = sorted(
        decision_items,
        key=lambda item: (
            _safe_int(item.get("source_contract_final_review_rank")) is None,
            _safe_int(item.get("source_contract_final_review_rank")) or 999999,
            str(item.get("symbol") or ""),
            str(item.get("contract_symbol") or ""),
        ),
    )

    summary = _summary(decision_records=decision_records, source_summary=source_summary)
    status = (
        "ready"
        if summary["contract_final_decision_count"] > 0
        and summary["pending_contract_final_decision_count"] == 0
        and summary["invalid_contract_final_decision_count"] == 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_contract_final_decision_record",
        "schema_version": CONTRACT_FINAL_DECISION_RECORD_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "contract_final_decision_record",
        "adapter_type": "contract_final_decision_record_builder",
        "review_scope": "explicit_contract_final_decision_record_not_order_intent_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "contract_decision_review_audit",
                "priority": "medium",
                "recommendation": "Audit explicit approve/reject/defer decisions before any downstream planning; do not route or submit orders from this artifact.",
            }
        ],
        "contract_final_decision_records": decision_records,
        "contract_final_decision_record_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_decision_item(review_item: Mapping[str, Any], decisions: Mapping[tuple[str, str | None], Mapping[str, Any]]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(review_item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    contract_symbol = _clean_text(_first_value(review_item, ("contract_symbol", "option_symbol")))
    key = (symbol, contract_symbol)
    decision = decisions.get(key) or decisions.get((symbol, None))

    source_status = _clean_text(
        _first_value(
            review_item,
            (
                "contract_final_review_export_status",
                "contract_final_review_status",
                "coverage_status",
            ),
        )
    ) or "ready_for_contract_final_review"

    risk_flags = _as_string_list(review_item.get("risk_flags"))
    constraint_flags = _as_string_list(review_item.get("constraint_flags"))
    data_review_reasons = _as_string_list(review_item.get("data_review_reasons"))
    hard_block_reasons = _as_string_list(review_item.get("hard_block_reasons"))
    review_reasons = _as_string_list(review_item.get("review_reasons"))
    needs_review_reasons = _as_string_list(review_item.get("needs_review_reasons"))

    if hard_block_reasons or source_status.startswith("blocked"):
        normalized_decision = "blocked"
        final_status = BLOCKED_FROM_CONTRACT_FINAL_DECISION
        explicit_decision = False
    elif data_review_reasons or source_status == DATA_REVIEW_REQUIRED:
        normalized_decision = "data_review_required"
        final_status = DATA_REVIEW_REQUIRED
        explicit_decision = False
    else:
        normalized_decision = _normalize_decision(decision)
        explicit_decision = normalized_decision in {"approved", "rejected", "deferred"}
        if normalized_decision == "approved":
            final_status = APPROVED_CONTRACT_FINAL_DECISION
        elif normalized_decision == "rejected":
            final_status = REJECTED_CONTRACT_FINAL_DECISION
        elif normalized_decision == "deferred":
            final_status = DEFERRED_CONTRACT_FINAL_DECISION
        elif normalized_decision == "invalid":
            final_status = INVALID_CONTRACT_FINAL_DECISION
        else:
            final_status = PENDING_CONTRACT_FINAL_DECISION

    decision_reason = _clean_text(_first_value(decision, ("decision_reason", "reason", "notes", "review_notes"))) if isinstance(decision, Mapping) else None
    reviewer = _clean_text(_first_value(decision, ("reviewer", "reviewed_by", "approved_by"))) if isinstance(decision, Mapping) else None
    reviewed_at = _clean_text(_first_value(decision, ("reviewed_at", "decision_timestamp", "timestamp", "as_of"))) if isinstance(decision, Mapping) else None

    combined_reasons = sorted(
        set(data_review_reasons + hard_block_reasons + review_reasons + needs_review_reasons + risk_flags + constraint_flags)
    )
    if final_status == INVALID_CONTRACT_FINAL_DECISION:
        combined_reasons = sorted(set(combined_reasons + ["invalid_contract_final_decision_value"]))
    if final_status == PENDING_CONTRACT_FINAL_DECISION:
        combined_reasons = sorted(set(combined_reasons + ["missing_contract_final_decision"]))

    return {
        "artifact_type": "contract_final_decision_record_item",
        "symbol": symbol,
        "contract_symbol": contract_symbol,
        "coverage_status": final_status,
        "contract_final_decision_status": final_status,
        "normalized_human_decision": normalized_decision,
        "explicit_human_decision_recorded": explicit_decision,
        "source_contract_final_review_status": source_status,
        "source_contract_final_review_rank": _safe_int(review_item.get("contract_final_review_rank")),
        "selected_strategy_family": _clean_text(review_item.get("selected_strategy_family")),
        "contract_score": _safe_float(review_item.get("contract_score")),
        "quote_date": _clean_text(review_item.get("quote_date")),
        "expiration": _clean_text(review_item.get("expiration")),
        "dte": _safe_int(review_item.get("dte")),
        "strike": _safe_float(review_item.get("strike")),
        "option_right": _clean_text(review_item.get("option_right")),
        "bid": _safe_float(review_item.get("bid")),
        "ask": _safe_float(review_item.get("ask")),
        "mid": _safe_float(review_item.get("mid")),
        "spread_pct": _safe_float(review_item.get("spread_pct")),
        "open_interest": _safe_int(review_item.get("open_interest")),
        "volume": _safe_int(review_item.get("volume")),
        "implied_volatility": _safe_float(review_item.get("implied_volatility")),
        "delta": _safe_float(review_item.get("delta")),
        "gamma": _safe_float(review_item.get("gamma")),
        "theta": _safe_float(review_item.get("theta")),
        "vega": _safe_float(review_item.get("vega")),
        "moneyness": _safe_float(review_item.get("moneyness")),
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "review_reasons": sorted(set(review_reasons)),
        "needs_review_reasons": combined_reasons,
        "decision_reason": decision_reason,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "manual_review_required": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _normalize_decision(decision: Mapping[str, Any] | None) -> str:
    if not isinstance(decision, Mapping):
        return "pending"
    raw = _clean_text(
        _first_value(
            decision,
            (
                "contract_final_decision",
                "human_contract_final_decision",
                "human_decision",
                "decision",
                "status",
            ),
        )
    )
    if raw is None:
        return "pending"
    clean = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if clean in APPROVE_VALUES:
        return "approved"
    if clean in REJECT_VALUES:
        return "rejected"
    if clean in DEFER_VALUES:
        return "deferred"
    return "invalid"


def _decision_index(decision_items: Sequence[Any]) -> dict[tuple[str, str | None], Mapping[str, Any]]:
    index: dict[tuple[str, str | None], Mapping[str, Any]] = {}
    for item in decision_items:
        if not isinstance(item, Mapping):
            continue
        symbol = _clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker")))
        if not symbol:
            continue
        contract_symbol = _clean_text(_first_value(item, ("contract_symbol", "option_symbol")))
        index[(symbol, contract_symbol)] = item
    return index


def _summary(*, decision_records: Sequence[Mapping[str, Any]], source_summary: Mapping[str, Any]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in decision_records)
    decision_counts = Counter(str(item.get("normalized_human_decision") or "unknown") for item in decision_records)
    strategy_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in decision_records
        if item.get("selected_strategy_family")
    )
    risk_flag_counts = Counter(flag for item in decision_records for flag in item.get("risk_flags", []))
    constraint_counts = Counter(flag for item in decision_records for flag in item.get("constraint_flags", []))
    data_reason_counts = Counter(reason for item in decision_records for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in decision_records for reason in item.get("hard_block_reasons", []))
    needs_review_counts = Counter(reason for item in decision_records for reason in item.get("needs_review_reasons", []))

    symbols = {str(item.get("symbol")) for item in decision_records if item.get("symbol")}
    approved_symbols = {str(item.get("symbol")) for item in decision_records if item.get("coverage_status") == APPROVED_CONTRACT_FINAL_DECISION}
    rejected_symbols = {str(item.get("symbol")) for item in decision_records if item.get("coverage_status") == REJECTED_CONTRACT_FINAL_DECISION}
    deferred_symbols = {str(item.get("symbol")) for item in decision_records if item.get("coverage_status") == DEFERRED_CONTRACT_FINAL_DECISION}
    pending_symbols = {str(item.get("symbol")) for item in decision_records if item.get("coverage_status") == PENDING_CONTRACT_FINAL_DECISION}
    invalid_symbols = {str(item.get("symbol")) for item in decision_records if item.get("coverage_status") == INVALID_CONTRACT_FINAL_DECISION}

    source_review_symbols = _safe_int(source_summary.get("contract_final_review_symbol_count")) or len(symbols)
    source_review_queue = _safe_int(source_summary.get("contract_final_review_queue_count")) or len(decision_records)
    source_ranked = _safe_int(source_summary.get("ranked_contract_final_review_count")) or len(decision_records)
    source_option_rows = _safe_int(source_summary.get("option_row_count")) or 0
    source_data_review = _safe_int(source_summary.get("data_review_symbol_count")) or 0
    source_blocked = _safe_int(source_summary.get("blocked_symbol_count")) or 0

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(symbols) or (_safe_int(source_summary.get("symbol_count")) or 0),
        "source_contract_final_review_symbol_count": source_review_symbols,
        "source_contract_final_review_queue_count": source_review_queue,
        "source_ranked_contract_final_review_count": source_ranked,
        "contract_final_decision_count": len(decision_records),
        "contract_final_decision_symbol_count": len(symbols),
        "explicit_contract_final_decision_count": sum(1 for item in decision_records if item.get("explicit_human_decision_recorded") is True),
        "approved_contract_final_decision_count": coverage_counts.get(APPROVED_CONTRACT_FINAL_DECISION, 0),
        "rejected_contract_final_decision_count": coverage_counts.get(REJECTED_CONTRACT_FINAL_DECISION, 0),
        "deferred_contract_final_decision_count": coverage_counts.get(DEFERRED_CONTRACT_FINAL_DECISION, 0),
        "pending_contract_final_decision_count": coverage_counts.get(PENDING_CONTRACT_FINAL_DECISION, 0),
        "invalid_contract_final_decision_count": coverage_counts.get(INVALID_CONTRACT_FINAL_DECISION, 0),
        "approved_contract_final_decision_symbol_count": len(approved_symbols),
        "rejected_contract_final_decision_symbol_count": len(rejected_symbols),
        "deferred_contract_final_decision_symbol_count": len(deferred_symbols),
        "pending_contract_final_decision_symbol_count": len(pending_symbols),
        "invalid_contract_final_decision_symbol_count": len(invalid_symbols),
        "data_review_symbol_count": source_data_review,
        "blocked_symbol_count": source_blocked,
        "needs_review_symbol_count": len(pending_symbols | invalid_symbols) + source_data_review + source_blocked,
        "manual_review_symbol_count": len(symbols),
        "option_row_count": source_option_rows,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "human_decision_counts": dict(sorted(decision_counts.items())),
        "contract_final_decision_strategy_family_counts": dict(sorted(strategy_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
        "needs_review_reason_counts": dict(sorted(needs_review_counts.items())),
    }


def _source_summary(source: Any) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        summary = source.get("contract_final_review_export_summary")
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
        "source_contract_final_review_symbol_count": 0,
        "source_contract_final_review_queue_count": 0,
        "source_ranked_contract_final_review_count": 0,
        "contract_final_decision_count": 0,
        "contract_final_decision_symbol_count": 0,
        "explicit_contract_final_decision_count": 0,
        "approved_contract_final_decision_count": 0,
        "rejected_contract_final_decision_count": 0,
        "deferred_contract_final_decision_count": 0,
        "pending_contract_final_decision_count": 0,
        "invalid_contract_final_decision_count": 0,
        "approved_contract_final_decision_symbol_count": 0,
        "rejected_contract_final_decision_symbol_count": 0,
        "deferred_contract_final_decision_symbol_count": 0,
        "pending_contract_final_decision_symbol_count": 0,
        "invalid_contract_final_decision_symbol_count": 0,
        "data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "option_row_count": 0,
        "coverage_status_counts": {},
        "human_decision_counts": {},
        "contract_final_decision_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
        "needs_review_reason_counts": {},
    }
    return {
        "artifact_type": "signalforge_contract_final_decision_record",
        "schema_version": CONTRACT_FINAL_DECISION_RECORD_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "contract_final_decision_record",
        "adapter_type": "contract_final_decision_record_builder",
        "review_scope": "explicit_contract_final_decision_record_not_order_intent_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "contract_final_decision_records": [],
        "contract_final_decision_record_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
