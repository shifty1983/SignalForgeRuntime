from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CONTRACT_DECISION_REVIEW_AUDIT_SCHEMA_VERSION = "signalforge_contract_decision_review_audit.v1"

COVERED_CAPABILITIES = [
    "contract_decision_review_audit",
    "explicit_contract_decision_audit",
    "pending_invalid_contract_decision_gate",
    "contract_decision_audit_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "contract_final_decision_record",
]

CONTRACT_FINAL_DECISION_RECORD_KEYS = (
    "contract_final_decision_records",
    "contract_final_decisions",
    "decision_records",
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

READY_AUDIT_STATUS = "audited_contract_decision"
REVIEW_AUDIT_STATUS = "contract_decision_audit_needs_review"
BLOCKED_AUDIT_STATUS = "blocked_from_contract_decision_audit"


def build_signalforge_contract_decision_review_audit(
    contract_final_decision_record_source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    """Audit explicit human approve/reject/defer contract decision records.

    This artifact audits the decision record only. It does not create order intent, call broker APIs,
    route or submit orders, model fills/slippage, or authorize automatic strategy/parameter changes.
    """

    source_artifacts = {
        "contract_final_decision_record_source": _source_artifact_type(contract_final_decision_record_source),
    }
    source_summary = _source_summary(contract_final_decision_record_source)
    source_records = _extract_items(contract_final_decision_record_source, CONTRACT_FINAL_DECISION_RECORD_KEYS)

    if not source_records:
        return _blocked_result(["missing_contract_final_decision_records"], source_artifacts=source_artifacts)

    audit_records = [_build_audit_item(item) for item in source_records if isinstance(item, Mapping)]
    audit_records = sorted(
        audit_records,
        key=lambda item: (
            _safe_int(item.get("source_contract_final_review_rank")) is None,
            _safe_int(item.get("source_contract_final_review_rank")) or 999999,
            str(item.get("symbol") or ""),
            str(item.get("contract_symbol") or ""),
        ),
    )

    summary = _summary(audit_records=audit_records, source_summary=source_summary)
    status = (
        "ready"
        if summary["contract_decision_audit_count"] > 0
        and summary["pending_contract_final_decision_count"] == 0
        and summary["invalid_contract_final_decision_count"] == 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_contract_decision_review_audit",
        "schema_version": CONTRACT_DECISION_REVIEW_AUDIT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "contract_decision_review_audit",
        "adapter_type": "contract_decision_review_audit_builder",
        "review_scope": "contract_decision_audit_not_order_intent_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "contract_decision_governance_snapshot",
                "priority": "medium",
                "recommendation": "Summarize approved/rejected/deferred contract decisions for governance review only; do not route or submit orders from this artifact.",
            }
        ],
        "contract_decision_review_audit_records": audit_records,
        "contract_decision_review_audit_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_audit_item(source_item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(source_item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    contract_symbol = _clean_text(_first_value(source_item, ("contract_symbol", "option_symbol")))
    source_status = _clean_text(
        _first_value(
            source_item,
            (
                "contract_final_decision_status",
                "contract_decision_status",
                "coverage_status",
            ),
        )
    ) or PENDING_CONTRACT_FINAL_DECISION
    normalized_decision = _clean_text(source_item.get("normalized_human_decision"))
    explicit_decision = bool(source_item.get("explicit_human_decision_recorded"))

    risk_flags = _as_string_list(source_item.get("risk_flags"))
    constraint_flags = _as_string_list(source_item.get("constraint_flags"))
    data_review_reasons = _as_string_list(source_item.get("data_review_reasons"))
    hard_block_reasons = _as_string_list(source_item.get("hard_block_reasons"))
    needs_review_reasons = _as_string_list(source_item.get("needs_review_reasons"))
    decision_reason = _clean_text(source_item.get("decision_reason"))

    audit_status = READY_AUDIT_STATUS
    audit_reasons: list[str] = []

    if source_status == PENDING_CONTRACT_FINAL_DECISION:
        audit_status = REVIEW_AUDIT_STATUS
        audit_reasons.append("pending_contract_final_decision")
    elif source_status == INVALID_CONTRACT_FINAL_DECISION:
        audit_status = REVIEW_AUDIT_STATUS
        audit_reasons.append("invalid_contract_final_decision")
    elif source_status == DATA_REVIEW_REQUIRED:
        audit_status = REVIEW_AUDIT_STATUS
        audit_reasons.append("data_review_required")
    elif source_status == BLOCKED_FROM_CONTRACT_FINAL_DECISION or source_status.startswith("blocked"):
        audit_status = BLOCKED_AUDIT_STATUS
        audit_reasons.append("blocked_contract_final_decision")

    if not explicit_decision and source_status in {
        APPROVED_CONTRACT_FINAL_DECISION,
        REJECTED_CONTRACT_FINAL_DECISION,
        DEFERRED_CONTRACT_FINAL_DECISION,
    }:
        audit_status = REVIEW_AUDIT_STATUS
        audit_reasons.append("missing_explicit_human_decision_marker")

    if source_status == REJECTED_CONTRACT_FINAL_DECISION and not decision_reason:
        audit_status = REVIEW_AUDIT_STATUS
        audit_reasons.append("missing_rejection_reason")
    if source_status == DEFERRED_CONTRACT_FINAL_DECISION and not decision_reason:
        audit_status = REVIEW_AUDIT_STATUS
        audit_reasons.append("missing_defer_reason")

    inherited_review_reasons = sorted(set(risk_flags + constraint_flags + needs_review_reasons))
    audit_reasons = sorted(set(audit_reasons + data_review_reasons + hard_block_reasons))

    return {
        "artifact_type": "contract_decision_review_audit_item",
        "symbol": symbol,
        "contract_symbol": contract_symbol,
        "coverage_status": audit_status,
        "contract_decision_review_audit_status": audit_status,
        "source_contract_final_decision_status": source_status,
        "normalized_human_decision": normalized_decision,
        "explicit_human_decision_recorded": explicit_decision,
        "source_contract_final_review_rank": _safe_int(source_item.get("source_contract_final_review_rank")),
        "selected_strategy_family": _clean_text(source_item.get("selected_strategy_family")),
        "contract_score": _safe_float(source_item.get("contract_score")),
        "quote_date": _clean_text(source_item.get("quote_date")),
        "expiration": _clean_text(source_item.get("expiration")),
        "dte": _safe_int(source_item.get("dte")),
        "strike": _safe_float(source_item.get("strike")),
        "option_right": _clean_text(source_item.get("option_right")),
        "bid": _safe_float(source_item.get("bid")),
        "ask": _safe_float(source_item.get("ask")),
        "mid": _safe_float(source_item.get("mid")),
        "spread_pct": _safe_float(source_item.get("spread_pct")),
        "open_interest": _safe_int(source_item.get("open_interest")),
        "volume": _safe_int(source_item.get("volume")),
        "implied_volatility": _safe_float(source_item.get("implied_volatility")),
        "delta": _safe_float(source_item.get("delta")),
        "gamma": _safe_float(source_item.get("gamma")),
        "theta": _safe_float(source_item.get("theta")),
        "vega": _safe_float(source_item.get("vega")),
        "moneyness": _safe_float(source_item.get("moneyness")),
        "reviewer": _clean_text(source_item.get("reviewer")),
        "reviewed_at": _clean_text(source_item.get("reviewed_at")),
        "decision_reason": decision_reason,
        "risk_flags": risk_flags,
        "constraint_flags": constraint_flags,
        "data_review_reasons": data_review_reasons,
        "hard_block_reasons": hard_block_reasons,
        "needs_review_reasons": inherited_review_reasons,
        "contract_decision_audit_reasons": audit_reasons,
        "order_intent": None,
        "broker_order_id": None,
    }


def _summary(*, audit_records: Sequence[Mapping[str, Any]], source_summary: Mapping[str, Any]) -> dict[str, Any]:
    symbols = {_clean_symbol(item.get("symbol")) for item in audit_records if _clean_symbol(item.get("symbol"))}
    statuses = Counter(_clean_text(item.get("coverage_status")) for item in audit_records)
    source_statuses = Counter(_clean_text(item.get("source_contract_final_decision_status")) for item in audit_records)
    decisions = Counter(_clean_text(item.get("normalized_human_decision")) for item in audit_records if _clean_text(item.get("normalized_human_decision")))
    strategy_families = Counter(_clean_text(item.get("selected_strategy_family")) for item in audit_records if _clean_text(item.get("selected_strategy_family")))
    risk_flags = Counter(flag for item in audit_records for flag in _as_string_list(item.get("risk_flags")))
    constraint_flags = Counter(flag for item in audit_records for flag in _as_string_list(item.get("constraint_flags")))
    data_review_reasons = Counter(reason for item in audit_records for reason in _as_string_list(item.get("data_review_reasons")))
    hard_block_reasons = Counter(reason for item in audit_records for reason in _as_string_list(item.get("hard_block_reasons")))
    needs_review_reasons = Counter(reason for item in audit_records for reason in _as_string_list(item.get("needs_review_reasons")))
    audit_reasons = Counter(reason for item in audit_records for reason in _as_string_list(item.get("contract_decision_audit_reasons")))

    approved_records = [item for item in audit_records if item.get("source_contract_final_decision_status") == APPROVED_CONTRACT_FINAL_DECISION]
    rejected_records = [item for item in audit_records if item.get("source_contract_final_decision_status") == REJECTED_CONTRACT_FINAL_DECISION]
    deferred_records = [item for item in audit_records if item.get("source_contract_final_decision_status") == DEFERRED_CONTRACT_FINAL_DECISION]
    pending_records = [item for item in audit_records if item.get("source_contract_final_decision_status") == PENDING_CONTRACT_FINAL_DECISION]
    invalid_records = [item for item in audit_records if item.get("source_contract_final_decision_status") == INVALID_CONTRACT_FINAL_DECISION]
    data_review_records = [item for item in audit_records if item.get("source_contract_final_decision_status") == DATA_REVIEW_REQUIRED]
    blocked_records = [item for item in audit_records if item.get("source_contract_final_decision_status") == BLOCKED_FROM_CONTRACT_FINAL_DECISION or str(item.get("source_contract_final_decision_status") or "").startswith("blocked")]

    approved_symbols = {_clean_symbol(item.get("symbol")) for item in approved_records if _clean_symbol(item.get("symbol"))}
    rejected_symbols = {_clean_symbol(item.get("symbol")) for item in rejected_records if _clean_symbol(item.get("symbol"))}
    deferred_symbols = {_clean_symbol(item.get("symbol")) for item in deferred_records if _clean_symbol(item.get("symbol"))}
    pending_symbols = {_clean_symbol(item.get("symbol")) for item in pending_records if _clean_symbol(item.get("symbol"))}
    invalid_symbols = {_clean_symbol(item.get("symbol")) for item in invalid_records if _clean_symbol(item.get("symbol"))}
    data_review_symbols = {_clean_symbol(item.get("symbol")) for item in data_review_records if _clean_symbol(item.get("symbol"))}
    blocked_symbols = {_clean_symbol(item.get("symbol")) for item in blocked_records if _clean_symbol(item.get("symbol"))}
    needs_review_symbols = {
        _clean_symbol(item.get("symbol"))
        for item in audit_records
        if item.get("coverage_status") == REVIEW_AUDIT_STATUS and _clean_symbol(item.get("symbol"))
    }

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(symbols),
        "source_contract_final_decision_count": _safe_int(source_summary.get("contract_final_decision_count")) or len(audit_records),
        "source_contract_final_decision_symbol_count": _safe_int(source_summary.get("contract_final_decision_symbol_count")) or len(symbols),
        "source_contract_final_review_queue_count": _safe_int(source_summary.get("source_contract_final_review_queue_count")) or 0,
        "source_ranked_contract_final_review_count": _safe_int(source_summary.get("source_ranked_contract_final_review_count")) or 0,
        "contract_decision_audit_count": len(audit_records),
        "contract_decision_audit_symbol_count": len(symbols),
        "audited_contract_decision_count": statuses.get(READY_AUDIT_STATUS, 0),
        "contract_decision_audit_needs_review_count": statuses.get(REVIEW_AUDIT_STATUS, 0),
        "blocked_contract_decision_audit_count": statuses.get(BLOCKED_AUDIT_STATUS, 0),
        "approved_contract_final_decision_count": len(approved_records),
        "rejected_contract_final_decision_count": len(rejected_records),
        "deferred_contract_final_decision_count": len(deferred_records),
        "pending_contract_final_decision_count": len(pending_records),
        "invalid_contract_final_decision_count": len(invalid_records),
        "approved_contract_final_decision_symbol_count": len(approved_symbols),
        "rejected_contract_final_decision_symbol_count": len(rejected_symbols),
        "deferred_contract_final_decision_symbol_count": len(deferred_symbols),
        "pending_contract_final_decision_symbol_count": len(pending_symbols),
        "invalid_contract_final_decision_symbol_count": len(invalid_symbols),
        "data_review_symbol_count": len(data_review_symbols),
        "blocked_symbol_count": len(blocked_symbols),
        "needs_review_symbol_count": len(needs_review_symbols),
        "manual_review_symbol_count": len(symbols),
        "option_row_count": _safe_int(source_summary.get("option_row_count")) or 0,
        "coverage_status_counts": _dict(statuses),
        "source_contract_final_decision_status_counts": _dict(source_statuses),
        "human_decision_counts": _dict(decisions),
        "contract_decision_audit_strategy_family_counts": _dict(strategy_families),
        "risk_flag_counts": _dict(risk_flags),
        "constraint_flag_counts": _dict(constraint_flags),
        "data_review_reason_counts": _dict(data_review_reasons),
        "hard_block_reason_counts": _dict(hard_block_reasons),
        "needs_review_reason_counts": _dict(needs_review_reasons),
        "contract_decision_audit_reason_counts": _dict(audit_reasons),
    }


def _blocked_result(blocked_reasons: Sequence[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": 0,
        "source_contract_final_decision_count": 0,
        "source_contract_final_decision_symbol_count": 0,
        "source_contract_final_review_queue_count": 0,
        "source_ranked_contract_final_review_count": 0,
        "contract_decision_audit_count": 0,
        "contract_decision_audit_symbol_count": 0,
        "audited_contract_decision_count": 0,
        "contract_decision_audit_needs_review_count": 0,
        "blocked_contract_decision_audit_count": 0,
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
        "source_contract_final_decision_status_counts": {},
        "human_decision_counts": {},
        "contract_decision_audit_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
        "needs_review_reason_counts": {},
        "contract_decision_audit_reason_counts": {},
    }
    return {
        "artifact_type": "signalforge_contract_decision_review_audit",
        "schema_version": CONTRACT_DECISION_REVIEW_AUDIT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "contract_decision_review_audit",
        "adapter_type": "contract_decision_review_audit_builder",
        "review_scope": "contract_decision_audit_not_order_intent_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "contract_decision_review_audit_records": [],
        "contract_decision_review_audit_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _source_summary(source: Mapping[str, Any] | Sequence[Any] | None) -> Mapping[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    summary = source.get("contract_final_decision_record_summary")
    return summary if isinstance(summary, Mapping) else {}


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or "mapping")
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    return "missing"


def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]) -> list[Any]:
    if isinstance(source, Mapping):
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
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)
    return []


def _first_value(source: Mapping[str, Any] | None, keys: Sequence[str]) -> Any:
    if not isinstance(source, Mapping):
        return None
    for key in keys:
        if key in source and source.get(key) not in (None, ""):
            return source.get(key)
    return None


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = _clean_text(value)
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = []
        for item in value:
            cleaned = _clean_text(item)
            if cleaned:
                result.append(cleaned)
        return result
    cleaned = _clean_text(value)
    return [cleaned] if cleaned else []


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _dict(counter: Counter) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(counter.items()) if key}
