from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


CONTRACT_SELECTION_READINESS_SCHEMA_VERSION = "signalforge_contract_selection_readiness.v1"

COVERED_CAPABILITIES = [
    "contract_selection_readiness",
    "final_review_candidate_contract_data_readiness",
    "contract_data_quality_gate",
    "contract_readiness_not_contract_selection_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "candidate_final_review_export",
]

FINAL_REVIEW_ITEM_KEYS = (
    "final_review_queue",
    "ranked_final_review_items",
    "candidate_final_review_items",
    "items",
    "data",
    "rows",
)

AUDIT_ITEM_KEYS = (
    "candidate_final_review_items",
    "final_review_queue",
    "ranked_final_review_items",
    "items",
    "data",
    "rows",
)

OPTION_ROW_KEYS = (
    "option_rows",
    "contract_rows",
    "contracts",
    "items",
    "data",
    "rows",
)

RANKABLE_FINAL_REVIEW_STATUSES = {
    "ready_final_review",
    "constrained_final_review",
}

READINESS_READY = "ready_for_contract_selection_evaluation"
READINESS_CONSTRAINED = "constrained_for_contract_selection_evaluation"
READINESS_DATA_REVIEW = "data_review_required"
READINESS_BLOCKED = "blocked_from_contract_selection_evaluation"
READINESS_NOT_RECOMMENDED = "not_recommended"


def build_signalforge_contract_selection_readiness(
    candidate_final_review_source: Mapping[str, Any] | Sequence[Any] | None,
    option_source: Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    min_candidate_contract_count: int = 1,
    max_spread_pct: float = 0.15,
    min_open_interest: int = 100,
    min_volume: int = 1,
) -> dict[str, Any]:
    """Evaluate whether final-review-approved candidates have usable contract data.

    This artifact checks readiness for later contract selection. It does not
    choose contracts, call broker APIs, route orders, submit orders, model fills,
    model slippage, or authorize any automatic strategy change.
    """

    source_artifacts = {
        "candidate_final_review_source": _source_artifact_type(candidate_final_review_source),
        "option_source": _source_artifact_type(option_source),
    }
    all_review_items = _extract_items(candidate_final_review_source, AUDIT_ITEM_KEYS)
    final_review_items = _extract_final_review_queue(candidate_final_review_source)
    option_rows = _extract_items(option_source, OPTION_ROW_KEYS)

    blocked_reasons: list[str] = []
    if not all_review_items and not final_review_items:
        blocked_reasons.append("missing_candidate_final_review_items")

    if blocked_reasons:
        return _blocked_result(blocked_reasons, source_artifacts=source_artifacts)

    indexed_option_rows = _index_option_rows(option_rows)
    audit_items = [_build_source_audit_item(item) for item in all_review_items if isinstance(item, Mapping)]
    final_candidates = [_build_source_audit_item(item) for item in final_review_items if isinstance(item, Mapping)]

    readiness_items = [
        _build_readiness_item(
            candidate,
            indexed_option_rows.get(str(candidate.get("symbol") or ""), []),
            min_candidate_contract_count=max(1, int(min_candidate_contract_count)),
            max_spread_pct=float(max_spread_pct),
            min_open_interest=int(min_open_interest),
            min_volume=int(min_volume),
        )
        for candidate in final_candidates
        if candidate.get("eligible_for_contract_readiness") is True
    ]

    readiness_queue = _rank_readiness_items(readiness_items)
    for index, item in enumerate(readiness_queue, start=1):
        item["contract_readiness_rank"] = index

    summary = _summary(
        audit_items=audit_items,
        readiness_items=readiness_items,
        readiness_queue=readiness_queue,
        option_rows=option_rows,
    )

    status = (
        "ready"
        if summary["contract_readiness_queue_count"] > 0
        and summary["data_review_symbol_count"] == 0
        and summary["blocked_symbol_count"] == 0
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_contract_selection_readiness",
        "schema_version": CONTRACT_SELECTION_READINESS_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "contract_selection_readiness",
        "adapter_type": "contract_selection_readiness_builder",
        "review_scope": "contract_data_readiness_not_contract_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "contract_candidate_scoring",
                "priority": "high",
                "recommendation": "Score contract candidates only after final-review-approved candidates have contract-selection readiness.",
            }
        ],
        "candidate_final_review_items": audit_items,
        "contract_selection_readiness_items": readiness_items,
        "contract_readiness_queue": readiness_queue,
        "ranked_contract_readiness_items": readiness_queue,
        "contract_selection_readiness_summary": summary,
        "thresholds": {
            "min_candidate_contract_count": max(1, int(min_candidate_contract_count)),
            "max_spread_pct": float(max_spread_pct),
            "min_open_interest": int(min_open_interest),
            "min_volume": int(min_volume),
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "blocked_reasons": [],
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_source_audit_item(item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    final_status = _clean_text(
        _first_value(item, ("final_review_export_status", "coverage_status", "final_review_handoff_status"))
    ) or READINESS_DATA_REVIEW
    included = item.get("included_in_final_review_export") is True or item.get("eligible_for_final_review_export") is True
    selected_family = _clean_text(item.get("selected_strategy_family"))

    eligible = bool(included and final_status in RANKABLE_FINAL_REVIEW_STATUSES and selected_family)

    return {
        "symbol": symbol,
        "source_coverage_status": final_status,
        "eligible_for_contract_readiness": eligible,
        "included_in_final_review_export": item.get("included_in_final_review_export") is True,
        "final_review_rank": _safe_int(item.get("final_review_rank")),
        "selected_strategy_family": selected_family,
        "selected_expected_value_score": _safe_float(item.get("selected_expected_value_score")),
        "selected_expected_value_state": _clean_text(item.get("selected_expected_value_state")) or "unknown",
        "risk_flags": sorted(set(_as_string_list(item.get("risk_flags")))),
        "constraint_flags": sorted(set(_as_string_list(item.get("constraint_flags")))),
        "data_review_reasons": sorted(set(_as_string_list(item.get("data_review_reasons")))),
        "hard_block_reasons": sorted(set(_as_string_list(item.get("hard_block_reasons")))),
        "needs_review_reasons": sorted(set(_as_string_list(item.get("needs_review_reasons")))),
        "macro_regime": item.get("macro_regime"),
        "weekly_planning_label": item.get("weekly_planning_label"),
        "asset_behavior_state": item.get("asset_behavior_state"),
        "options_behavior_state": item.get("options_behavior_state"),
        "premium_bias": item.get("premium_bias"),
        "strategy_environment_bias": item.get("strategy_environment_bias"),
    }


def _build_readiness_item(
    candidate: Mapping[str, Any],
    symbol_option_rows: Sequence[Mapping[str, Any]],
    *,
    min_candidate_contract_count: int,
    max_spread_pct: float,
    min_open_interest: int,
    min_volume: int,
) -> dict[str, Any]:
    symbol = str(candidate.get("symbol") or "UNKNOWN")
    contract_rows = [_normalize_option_row(row) for row in symbol_option_rows]
    valid_rows = [row for row in contract_rows if row["is_valid_contract_row"]]
    liquid_rows = [
        row
        for row in valid_rows
        if row["spread_pct"] is not None
        and row["spread_pct"] <= max_spread_pct
        and (row["open_interest"] is None or row["open_interest"] >= min_open_interest)
        and (row["volume"] is None or row["volume"] >= min_volume)
    ]
    delta_rows = [row for row in valid_rows if row["delta"] is not None]

    data_review_reasons = list(candidate.get("data_review_reasons") or [])
    hard_block_reasons = list(candidate.get("hard_block_reasons") or [])
    risk_flags = list(candidate.get("risk_flags") or [])
    constraint_flags = list(candidate.get("constraint_flags") or [])
    readiness_notes: list[str] = []

    if not contract_rows:
        data_review_reasons.append("missing_contract_rows")
    if contract_rows and not valid_rows:
        data_review_reasons.append("no_valid_contract_rows")
    if valid_rows and not liquid_rows:
        data_review_reasons.append("no_contract_rows_pass_liquidity_thresholds")
    if valid_rows and len(liquid_rows) < min_candidate_contract_count:
        data_review_reasons.append("insufficient_liquid_contract_candidates")
    if valid_rows and not delta_rows:
        data_review_reasons.append("missing_delta_for_contract_candidates")

    wide_spread_rows = [row for row in valid_rows if row["spread_pct"] is not None and row["spread_pct"] > max_spread_pct]
    low_oi_rows = [row for row in valid_rows if row["open_interest"] is not None and row["open_interest"] < min_open_interest]
    low_volume_rows = [row for row in valid_rows if row["volume"] is not None and row["volume"] < min_volume]

    if wide_spread_rows:
        risk_flags.append("contract_spread_risk")
    if low_oi_rows:
        risk_flags.append("contract_open_interest_risk")
    if low_volume_rows:
        risk_flags.append("contract_volume_risk")

    if hard_block_reasons:
        readiness_status = READINESS_BLOCKED
    elif data_review_reasons:
        readiness_status = READINESS_DATA_REVIEW
    elif risk_flags or constraint_flags:
        readiness_status = READINESS_CONSTRAINED
    else:
        readiness_status = READINESS_READY

    eligible_for_contract_selection_evaluation = readiness_status in {READINESS_READY, READINESS_CONSTRAINED}
    if eligible_for_contract_selection_evaluation:
        readiness_notes.append("contract_data_ready_for_later_contract_scoring")
    else:
        readiness_notes.append("contract_data_not_ready_for_later_contract_scoring")

    return {
        "artifact_type": "contract_selection_readiness_item",
        "symbol": symbol,
        "coverage_status": readiness_status,
        "contract_selection_readiness_status": readiness_status,
        "eligible_for_contract_selection_evaluation": eligible_for_contract_selection_evaluation,
        "contract_readiness_rank": None,
        "manual_review_required": True,
        "selected_strategy_family": candidate.get("selected_strategy_family"),
        "selected_expected_value_score": candidate.get("selected_expected_value_score"),
        "selected_expected_value_state": candidate.get("selected_expected_value_state"),
        "source_final_review_rank": candidate.get("final_review_rank"),
        "source_coverage_status": candidate.get("source_coverage_status"),
        "contract_row_count": len(contract_rows),
        "valid_contract_row_count": len(valid_rows),
        "liquid_contract_row_count": len(liquid_rows),
        "delta_available_contract_row_count": len(delta_rows),
        "min_spread_pct": _min_value(row["spread_pct"] for row in valid_rows),
        "max_spread_pct": _max_value(row["spread_pct"] for row in valid_rows),
        "max_open_interest": _max_value(row["open_interest"] for row in valid_rows),
        "max_volume": _max_value(row["volume"] for row in valid_rows),
        "candidate_contract_rows": _contract_row_preview(liquid_rows or valid_rows),
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": sorted(set(data_review_reasons + hard_block_reasons + risk_flags + constraint_flags)),
        "readiness_notes": readiness_notes,
        "macro_regime": candidate.get("macro_regime"),
        "weekly_planning_label": candidate.get("weekly_planning_label"),
        "asset_behavior_state": candidate.get("asset_behavior_state"),
        "options_behavior_state": candidate.get("options_behavior_state"),
        "premium_bias": candidate.get("premium_bias"),
        "strategy_environment_bias": candidate.get("strategy_environment_bias"),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _normalize_option_row(row: Mapping[str, Any]) -> dict[str, Any]:
    bid = _safe_float(_first_value(row, ("bid", "bid_price")))
    ask = _safe_float(_first_value(row, ("ask", "ask_price")))
    mid = _safe_float(_first_value(row, ("mid", "mid_price", "mark")))
    if mid is None and bid is not None and ask is not None and ask >= bid:
        mid = (bid + ask) / 2.0
    spread = None if bid is None or ask is None or ask < bid else ask - bid
    spread_pct = None if spread is None or not mid or mid <= 0 else spread / mid

    strike = _safe_float(row.get("strike"))
    expiration = _clean_text(_first_value(row, ("expiration", "expiry", "expiration_date")))
    option_type = _clean_text(_first_value(row, ("right", "option_type", "type")))

    is_valid_contract_row = bool(strike is not None and expiration and (bid is not None or ask is not None or mid is not None))

    return {
        "symbol": _clean_symbol(_first_value(row, ("underlying_symbol", "symbol", "ticker"))),
        "contract_symbol": _clean_text(_first_value(row, ("contract_symbol", "option_symbol", "symbol"))),
        "expiration": expiration,
        "strike": strike,
        "option_type": option_type,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_pct": spread_pct,
        "open_interest": _safe_int(_first_value(row, ("open_interest", "oi"))),
        "volume": _safe_int(row.get("volume")),
        "delta": _safe_float(row.get("delta")),
        "gamma": _safe_float(row.get("gamma")),
        "theta": _safe_float(row.get("theta")),
        "vega": _safe_float(row.get("vega")),
        "implied_volatility": _safe_float(_first_value(row, ("implied_volatility", "iv"))),
        "is_valid_contract_row": is_valid_contract_row,
    }


def _contract_row_preview(rows: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for row in rows[:limit]:
        preview.append(
            {
                "contract_symbol": row.get("contract_symbol"),
                "expiration": row.get("expiration"),
                "strike": row.get("strike"),
                "option_type": row.get("option_type"),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "mid": row.get("mid"),
                "spread_pct": row.get("spread_pct"),
                "open_interest": row.get("open_interest"),
                "volume": row.get("volume"),
                "delta": row.get("delta"),
            }
        )
    return preview


def _rank_readiness_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    eligible = [dict(item) for item in items if item.get("eligible_for_contract_selection_evaluation") is True]
    return sorted(
        eligible,
        key=lambda item: (
            1 if item.get("contract_selection_readiness_status") == READINESS_READY else 0,
            _safe_float(item.get("selected_expected_value_score")) or -999.0,
            _safe_int(item.get("liquid_contract_row_count")) or 0,
            -(_safe_int(item.get("source_final_review_rank")) or 999999),
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )


def _summary(
    *,
    audit_items: Sequence[Mapping[str, Any]],
    readiness_items: Sequence[Mapping[str, Any]],
    readiness_queue: Sequence[Mapping[str, Any]],
    option_rows: Sequence[Any],
) -> dict[str, Any]:
    source_status_counts = Counter(str(item.get("source_coverage_status") or "unknown") for item in audit_items)
    readiness_counts = Counter(str(item.get("coverage_status") or "unknown") for item in readiness_items)
    strategy_family_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in readiness_queue
        if item.get("selected_strategy_family")
    )
    all_strategy_family_counts = Counter(
        str(item.get("selected_strategy_family"))
        for item in readiness_items
        if item.get("selected_strategy_family")
    )
    risk_flag_counts = Counter(flag for item in readiness_items for flag in item.get("risk_flags", []))
    constraint_counts = Counter(flag for item in readiness_items for flag in item.get("constraint_flags", []))
    data_reason_counts = Counter(reason for item in readiness_items for reason in item.get("data_review_reasons", []))
    hard_block_counts = Counter(reason for item in readiness_items for reason in item.get("hard_block_reasons", []))
    source_data_reason_counts = Counter(reason for item in audit_items for reason in item.get("data_review_reasons", []))

    candidate_final_review_count = sum(1 for item in audit_items if item.get("eligible_for_contract_readiness") is True)
    source_data_review_count = source_status_counts.get("data_review_required", 0)
    source_not_recommended_count = source_status_counts.get("not_recommended", 0)
    source_blocked_count = source_status_counts.get("blocked", 0)
    ready_count = readiness_counts.get(READINESS_READY, 0)
    constrained_count = readiness_counts.get(READINESS_CONSTRAINED, 0)
    readiness_data_review_count = readiness_counts.get(READINESS_DATA_REVIEW, 0)
    readiness_blocked_count = readiness_counts.get(READINESS_BLOCKED, 0)
    queue_count = len(readiness_queue)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(audit_items),
        "candidate_final_review_symbol_count": candidate_final_review_count,
        "contract_readiness_symbol_count": len(readiness_items),
        "ready_contract_readiness_symbol_count": ready_count,
        "constrained_contract_readiness_symbol_count": constrained_count,
        "contract_selection_evaluable_symbol_count": ready_count + constrained_count,
        "contract_readiness_queue_count": queue_count,
        "ranked_contract_readiness_count": queue_count,
        "data_review_symbol_count": source_data_review_count + readiness_data_review_count,
        "contract_data_review_symbol_count": readiness_data_review_count,
        "blocked_symbol_count": source_blocked_count + readiness_blocked_count,
        "not_recommended_symbol_count": source_not_recommended_count,
        "no_final_review_candidate_symbol_count": max(0, len(audit_items) - candidate_final_review_count - source_data_review_count - source_not_recommended_count - source_blocked_count),
        "needs_review_symbol_count": source_data_review_count + readiness_data_review_count + source_blocked_count + readiness_blocked_count,
        "manual_review_symbol_count": len(audit_items),
        "option_row_count": len(option_rows),
        "coverage_status_counts": dict(sorted(readiness_counts.items())),
        "source_final_review_status_counts": dict(sorted(source_status_counts.items())),
        "contract_readiness_strategy_family_counts": dict(sorted(strategy_family_counts.items())),
        "all_candidate_strategy_family_counts": dict(sorted(all_strategy_family_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "data_review_reason_counts": dict(sorted((data_reason_counts + source_data_reason_counts).items())),
        "hard_block_reason_counts": dict(sorted(hard_block_counts.items())),
    }


def _extract_final_review_queue(source: Mapping[str, Any] | Sequence[Any] | None) -> list[Any]:
    if isinstance(source, Mapping):
        for key in ("final_review_queue", "ranked_final_review_items"):
            value = source.get(key)
            if _looks_like_items(value):
                return list(value)
        # Fallback: use included items only if no explicit queue exists.
        items = _extract_items(source, ("candidate_final_review_items",))
        included = [item for item in items if isinstance(item, Mapping) and item.get("included_in_final_review_export") is True]
        return included
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)
    return []


def _index_option_rows(option_rows: Sequence[Any]) -> dict[str, list[Mapping[str, Any]]]:
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    for row in option_rows:
        if not isinstance(row, Mapping):
            continue
        symbol = _clean_symbol(_first_value(row, ("underlying_symbol", "root_symbol", "ticker", "underlying", "symbol")))
        if not symbol:
            continue
        indexed.setdefault(symbol, []).append(row)
    return indexed


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


def _looks_like_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return _clean_text(source.get("artifact_type")) or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    if source is None:
        return "missing"
    return type(source).__name__


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


def _min_value(values: Any) -> float | int | None:
    clean = [value for value in values if value is not None]
    return min(clean) if clean else None


def _max_value(values: Any) -> float | int | None:
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


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
        "candidate_final_review_symbol_count": 0,
        "contract_readiness_symbol_count": 0,
        "ready_contract_readiness_symbol_count": 0,
        "constrained_contract_readiness_symbol_count": 0,
        "contract_selection_evaluable_symbol_count": 0,
        "contract_readiness_queue_count": 0,
        "ranked_contract_readiness_count": 0,
        "data_review_symbol_count": 0,
        "contract_data_review_symbol_count": 0,
        "blocked_symbol_count": 0,
        "not_recommended_symbol_count": 0,
        "no_final_review_candidate_symbol_count": 0,
        "needs_review_symbol_count": 0,
        "manual_review_symbol_count": 0,
        "option_row_count": 0,
        "coverage_status_counts": {},
        "source_final_review_status_counts": {},
        "contract_readiness_strategy_family_counts": {},
        "all_candidate_strategy_family_counts": {},
        "risk_flag_counts": {},
        "constraint_flag_counts": {},
        "data_review_reason_counts": {},
        "hard_block_reason_counts": {},
    }
    return {
        "artifact_type": "signalforge_contract_selection_readiness",
        "schema_version": CONTRACT_SELECTION_READINESS_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "contract_selection_readiness",
        "adapter_type": "contract_selection_readiness_builder",
        "review_scope": "contract_data_readiness_not_contract_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "candidate_final_review_items": [],
        "contract_selection_readiness_items": [],
        "contract_readiness_queue": [],
        "ranked_contract_readiness_items": [],
        "contract_selection_readiness_summary": summary,
        "thresholds": {},
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
