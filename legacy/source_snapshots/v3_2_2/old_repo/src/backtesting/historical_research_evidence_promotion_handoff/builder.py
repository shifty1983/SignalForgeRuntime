from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "historical_research_evidence_promotion_handoff.v1"
HANDOFF_TYPE = "historical_research_evidence_promotion_handoff"

EXPLICIT_EXCLUSIONS = [
    "quantconnect_api_calls",
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "local_fill_simulation",
    "local_slippage_modeling",
    "external_data_warehouse_access",
]


def build_historical_research_evidence_promotion_handoff(
    source: Any,
) -> dict[str, Any]:
    """Build a downstream historical-research promotion handoff bundle.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.

    It converts existing promotable historical-research evidence into a stable
    downstream handoff artifact.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    promotion_gate = _extract_promotion_gate(source_copy)

    if not promotion_gate:
        return _blocked_invalid_shape(
            "source is missing historical research evidence promotion gate"
        )

    gate_status = str(promotion_gate.get("status", "needs_review"))
    gate_summary = _as_mapping(promotion_gate.get("summary"))

    promoted_items = _build_promoted_items(
        _as_list(promotion_gate.get("promotable_evidence"))
    )

    source_needs_review_evidence = _as_list(
        promotion_gate.get("needs_review_evidence")
    )
    source_blocked_evidence = _as_list(
        promotion_gate.get("blocked_evidence")
    )

    warnings = _sorted_unique_text(
        _as_text_list(promotion_gate.get("warnings"))
        + _collect_item_text(promoted_items, "warnings")
    )

    blocked_reasons = _sorted_unique_text(
        _as_text_list(promotion_gate.get("blocked_reasons"))
        + _collect_item_text(promoted_items, "blocked_reasons")
    )

    status = _classify_handoff_status(
        gate_status=gate_status,
        promoted_item_count=len(promoted_items),
        source_needs_review_count=len(source_needs_review_evidence),
        source_blocked_count=len(source_blocked_evidence),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons = [
            "historical research evidence promotion handoff is blocked"
        ]

    strategy_ids = _sorted_unique_text(
        [
            strategy_id
            for item in promoted_items
            for strategy_id in _as_text_list(item.get("strategy_ids"))
        ]
    )

    symbols = _sorted_unique_text(
        [
            symbol
            for item in promoted_items
            for symbol in _as_text_list(item.get("symbols"))
        ]
    )

    backtest_ids = _sorted_unique_text(
        [
            str(item.get("backtest_id"))
            for item in promoted_items
            if item.get("backtest_id")
        ]
    )

    evidence_ids = _sorted_unique_text(
        [
            str(item.get("evidence_id"))
            for item in promoted_items
            if item.get("evidence_id")
        ]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_type": HANDOFF_TYPE,
        "status": status,
        "summary": {
            "source_gate_status": gate_status,
            "source_gate_type": promotion_gate.get("gate_type"),
            "source_schema_version": promotion_gate.get("schema_version"),
            "backtest_id": gate_summary.get("backtest_id"),
            "promoted_item_count": len(promoted_items),
            "source_promotable_evidence_count": _safe_int(
                gate_summary.get("promotable_evidence_count")
            ),
            "source_needs_review_evidence_count": _safe_int(
                gate_summary.get("needs_review_evidence_count")
            ),
            "source_blocked_evidence_count": _safe_int(
                gate_summary.get("blocked_evidence_count")
            ),
            "strategy_count": len(strategy_ids),
            "symbol_count": len(symbols),
            "backtest_count": len(backtest_ids),
            "evidence_count": len(evidence_ids),
            "decision_event_count": sum(
                _safe_int(item.get("decision_event_count"))
                for item in promoted_items
            ),
            "performance_metric_count": sum(
                _safe_int(item.get("performance_metric_count"))
                for item in promoted_items
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
            "can_enter_downstream_historical_research": (
                status == "ready" and len(promoted_items) > 0
            ),
        },
        "promoted_items": promoted_items,
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "backtest_ids": backtest_ids,
        "evidence_ids": evidence_ids,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_promotion_gate_summary": {
            "schema_version": promotion_gate.get("schema_version"),
            "gate_type": promotion_gate.get("gate_type"),
            "status": promotion_gate.get("status"),
            "summary": _json_safe_mapping(gate_summary),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_promoted_items(
    promotable_evidence: list[Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for index, evidence in enumerate(promotable_evidence, start=1):
        if not isinstance(evidence, Mapping):
            continue

        items.append(
            _build_promoted_item(
                evidence,
                sequence=index,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            item.get("evidence_source") or "",
            item.get("backtest_id") or "",
            item.get("evidence_id") or "",
        ),
    )


def _build_promoted_item(
    evidence: Mapping[str, Any],
    *,
    sequence: int,
) -> dict[str, Any]:
    strategy_ids = _sorted_unique_text(
        _as_text_list(evidence.get("strategy_ids"))
    )
    symbols = _sorted_unique_text(
        _as_text_list(evidence.get("symbols"))
    )

    decision_event_count = _safe_int(
        evidence.get("decision_event_count")
    )
    performance_metric_count = _safe_int(
        evidence.get("performance_metric_count")
    )

    readiness = {
        "can_enter_downstream_historical_research": (
            evidence.get("promotion_decision") == "promotable"
            and bool(evidence.get("evidence_id"))
            and bool(evidence.get("backtest_id"))
            and decision_event_count > 0
            and performance_metric_count > 0
        ),
        "has_evidence_id": bool(evidence.get("evidence_id")),
        "has_backtest_id": bool(evidence.get("backtest_id")),
        "has_strategy_context": len(strategy_ids) > 0,
        "has_symbol_context": len(symbols) > 0,
        "has_decision_evidence": decision_event_count > 0,
        "has_performance_evidence": performance_metric_count > 0,
    }

    return {
        "handoff_item_type": (
            "historical_research_evidence_promotion_handoff_item"
        ),
        "status": (
            "ready"
            if readiness["can_enter_downstream_historical_research"]
            else "needs_review"
        ),
        "sequence": sequence,
        "promotion_decision": evidence.get("promotion_decision"),
        "evidence_id": evidence.get("evidence_id"),
        "evidence_source": evidence.get("evidence_source"),
        "evidence_method": evidence.get("evidence_method"),
        "evidence_category": evidence.get("evidence_category"),
        "backtest_id": evidence.get("backtest_id"),
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "expected_strategy_count": _safe_int(
            evidence.get("expected_strategy_count")
        ),
        "observed_strategy_count": _safe_int(
            evidence.get("observed_strategy_count")
        ),
        "expected_symbol_count": _safe_int(
            evidence.get("expected_symbol_count")
        ),
        "observed_symbol_count": _safe_int(
            evidence.get("observed_symbol_count")
        ),
        "decision_event_count": decision_event_count,
        "performance_metric_count": performance_metric_count,
        "readiness": readiness,
        "performance_snapshot": _json_safe_mapping(
            _as_mapping(evidence.get("performance_snapshot"))
        ),
        "alignment_status": _json_safe_mapping(
            _as_mapping(evidence.get("alignment_status"))
        ),
        "gate_checks": _json_safe_list(
            _as_list(evidence.get("gate_checks"))
        ),
        "downstream_actions": _build_downstream_actions(
            evidence=evidence,
            readiness=readiness,
        ),
        "warnings": _sorted_unique_text(
            _as_text_list(evidence.get("warnings"))
        ),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(evidence.get("blocked_reasons"))
        ),
    }


def _build_downstream_actions(
    *,
    evidence: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> list[str]:
    actions = _as_text_list(evidence.get("promotion_actions"))

    if readiness.get("can_enter_downstream_historical_research"):
        actions.append(
            "include promoted evidence in downstream historical research"
        )

    if not readiness.get("has_strategy_context"):
        actions.append("add strategy context before downstream research")

    if not readiness.get("has_symbol_context"):
        actions.append("add symbol context before downstream research")

    if not readiness.get("has_decision_evidence"):
        actions.append("add decision evidence before downstream research")

    if not readiness.get("has_performance_evidence"):
        actions.append(
            "add performance evidence before downstream research"
        )

    return _sorted_unique_text(actions)


def _extract_promotion_gate(source: Mapping[str, Any]) -> dict[str, Any]:
    promotion_gate = source.get("promotion_gate")

    if isinstance(promotion_gate, Mapping):
        return deepcopy(dict(promotion_gate))

    if (
        source.get("schema_version")
        == "historical_research_evidence_promotion_gate.v1"
    ):
        return deepcopy(dict(source))

    operation_result = source.get("operation_result")

    if isinstance(operation_result, Mapping):
        promotion_gate = operation_result.get("promotion_gate")

        if isinstance(promotion_gate, Mapping):
            return deepcopy(dict(promotion_gate))

    pipeline_result = source.get("pipeline_result")

    if isinstance(pipeline_result, Mapping):
        promotion_gate = pipeline_result.get("promotion_gate")

        if isinstance(promotion_gate, Mapping):
            return deepcopy(dict(promotion_gate))

    return {}


def _classify_handoff_status(
    *,
    gate_status: str,
    promoted_item_count: int,
    source_needs_review_count: int,
    source_blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if gate_status == "blocked" or source_blocked_count > 0 or blocked_reasons:
        return "blocked"

    if gate_status == "needs_review" or source_needs_review_count > 0:
        return "needs_review"

    if gate_status == "ready" and promoted_item_count > 0:
        return "ready"

    return "needs_review"


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_type": HANDOFF_TYPE,
        "status": "blocked",
        "summary": {
            "source_gate_status": "invalid_shape",
            "source_gate_type": None,
            "source_schema_version": None,
            "backtest_id": None,
            "promoted_item_count": 0,
            "source_promotable_evidence_count": 0,
            "source_needs_review_evidence_count": 0,
            "source_blocked_evidence_count": 0,
            "strategy_count": 0,
            "symbol_count": 0,
            "backtest_count": 0,
            "evidence_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
            "can_enter_downstream_historical_research": False,
        },
        "promoted_items": [],
        "strategy_ids": [],
        "symbols": [],
        "backtest_ids": [],
        "evidence_ids": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_promotion_gate_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _collect_item_text(
    items: list[Mapping[str, Any]],
    key: str,
) -> list[str]:
    values: list[str] = []

    for item in items:
        values.extend(_as_text_list(item.get(key)))

    return values


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    return []


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    if isinstance(value, tuple):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    return [str(value).strip()] if str(value).strip() else []


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted(
        {
            value.strip()
            for value in values
            if value and value.strip()
        }
    )


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0

    if isinstance(value, int):
        return value

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}

    for key, item in value.items():
        safe[str(key)] = _json_safe_value(item)

    return safe


def _json_safe_list(value: list[Any]) -> list[Any]:
    return [_json_safe_value(item) for item in value]


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)

    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)
