from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "historical_research_downstream_intake.v1"
INTAKE_TYPE = "historical_research_downstream_intake"

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


def build_historical_research_downstream_intake(
    source: Any,
) -> dict[str, Any]:
    """Build a QuantConnect-independent downstream research intake artifact.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.

    It normalizes promoted historical research evidence into a stable input for
    expected-value, strategy-selection, and downstream research layers.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    promotion_handoff = _extract_promotion_handoff(source_copy)

    if not promotion_handoff:
        return _blocked_invalid_shape(
            "source is missing historical research evidence promotion handoff"
        )

    handoff_status = str(promotion_handoff.get("status", "needs_review"))
    handoff_summary = _as_mapping(promotion_handoff.get("summary"))

    intake_items = _build_intake_items(
        _as_list(promotion_handoff.get("promoted_items"))
    )

    warnings = _sorted_unique_text(
        _as_text_list(promotion_handoff.get("warnings"))
        + _collect_item_text(intake_items, "warnings")
    )

    blocked_reasons = _sorted_unique_text(
        _as_text_list(promotion_handoff.get("blocked_reasons"))
        + _collect_item_text(intake_items, "blocked_reasons")
    )

    strategy_ids = _sorted_unique_text(
        [
            strategy_id
            for item in intake_items
            for strategy_id in _as_text_list(item.get("strategy_ids"))
        ]
    )

    symbols = _sorted_unique_text(
        [
            symbol
            for item in intake_items
            for symbol in _as_text_list(item.get("symbols"))
        ]
    )

    backtest_ids = _sorted_unique_text(
        [
            str(item.get("backtest_id"))
            for item in intake_items
            if item.get("backtest_id")
        ]
    )

    evidence_ids = _sorted_unique_text(
        [
            str(item.get("evidence_id"))
            for item in intake_items
            if item.get("evidence_id")
        ]
    )

    status = _classify_downstream_intake_status(
        handoff_status=handoff_status,
        intake_items=intake_items,
        blocked_reasons=blocked_reasons,
        can_enter_downstream=bool(
            handoff_summary.get(
                "can_enter_downstream_historical_research"
            )
        ),
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons = [
            "historical research downstream intake is blocked"
        ]

    return {
        "schema_version": SCHEMA_VERSION,
        "intake_type": INTAKE_TYPE,
        "status": status,
        "summary": {
            "source_handoff_status": handoff_status,
            "source_handoff_type": promotion_handoff.get("handoff_type"),
            "source_schema_version": promotion_handoff.get("schema_version"),
            "backtest_id": handoff_summary.get("backtest_id"),
            "intake_item_count": len(intake_items),
            "source_promoted_item_count": _safe_int(
                handoff_summary.get("promoted_item_count")
            ),
            "strategy_count": len(strategy_ids),
            "symbol_count": len(symbols),
            "backtest_count": len(backtest_ids),
            "evidence_count": len(evidence_ids),
            "decision_event_count": sum(
                _safe_int(item.get("decision_event_count"))
                for item in intake_items
            ),
            "performance_metric_count": sum(
                _safe_int(item.get("performance_metric_count"))
                for item in intake_items
            ),
            "ready_intake_item_count": sum(
                1
                for item in intake_items
                if item.get("status") == "ready"
            ),
            "needs_review_intake_item_count": sum(
                1
                for item in intake_items
                if item.get("status") == "needs_review"
            ),
            "blocked_intake_item_count": sum(
                1
                for item in intake_items
                if item.get("status") == "blocked"
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
            "can_enter_expected_value_research": (
                status == "ready" and len(intake_items) > 0
            ),
            "can_enter_strategy_selection": (
                status == "ready"
                and len(strategy_ids) > 0
                and len(symbols) > 0
            ),
        },
        "intake_items": intake_items,
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "backtest_ids": backtest_ids,
        "evidence_ids": evidence_ids,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_promotion_handoff_summary": {
            "schema_version": promotion_handoff.get("schema_version"),
            "handoff_type": promotion_handoff.get("handoff_type"),
            "status": promotion_handoff.get("status"),
            "summary": _json_safe_mapping(handoff_summary),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_intake_items(
    promoted_items: list[Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for index, item in enumerate(promoted_items, start=1):
        if not isinstance(item, Mapping):
            continue

        items.append(
            _build_intake_item(
                item,
                sequence=index,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            item.get("backtest_id") or "",
            item.get("evidence_id") or "",
            item.get("sequence") or 0,
        ),
    )


def _build_intake_item(
    promoted_item: Mapping[str, Any],
    *,
    sequence: int,
) -> dict[str, Any]:
    strategy_ids = _sorted_unique_text(
        _as_text_list(promoted_item.get("strategy_ids"))
    )
    symbols = _sorted_unique_text(
        _as_text_list(promoted_item.get("symbols"))
    )

    decision_event_count = _safe_int(
        promoted_item.get("decision_event_count")
    )
    performance_metric_count = _safe_int(
        promoted_item.get("performance_metric_count")
    )

    readiness = {
        "can_enter_expected_value_research": (
            promoted_item.get("status") == "ready"
            and bool(promoted_item.get("evidence_id"))
            and bool(promoted_item.get("backtest_id"))
            and len(strategy_ids) > 0
            and len(symbols) > 0
            and decision_event_count > 0
            and performance_metric_count > 0
        ),
        "has_evidence_id": bool(promoted_item.get("evidence_id")),
        "has_backtest_id": bool(promoted_item.get("backtest_id")),
        "has_strategy_context": len(strategy_ids) > 0,
        "has_symbol_context": len(symbols) > 0,
        "has_decision_evidence": decision_event_count > 0,
        "has_performance_evidence": performance_metric_count > 0,
    }

    status = "ready" if readiness["can_enter_expected_value_research"] else "needs_review"

    return {
        "intake_item_type": "historical_research_downstream_intake_item",
        "status": status,
        "sequence": sequence,
        "source_handoff_item_type": promoted_item.get("handoff_item_type"),
        "source_status": promoted_item.get("status"),
        "evidence_id": promoted_item.get("evidence_id"),
        "evidence_source": promoted_item.get("evidence_source"),
        "evidence_method": promoted_item.get("evidence_method"),
        "evidence_category": promoted_item.get("evidence_category"),
        "backtest_id": promoted_item.get("backtest_id"),
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "decision_event_count": decision_event_count,
        "performance_metric_count": performance_metric_count,
        "readiness": readiness,
        "performance_snapshot": _json_safe_mapping(
            _as_mapping(promoted_item.get("performance_snapshot"))
        ),
        "alignment_status": _json_safe_mapping(
            _as_mapping(promoted_item.get("alignment_status"))
        ),
        "research_actions": _build_research_actions(
            readiness=readiness,
        ),
        "warnings": _sorted_unique_text(
            _as_text_list(promoted_item.get("warnings"))
        ),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(promoted_item.get("blocked_reasons"))
        ),
    }


def _build_research_actions(
    *,
    readiness: Mapping[str, Any],
) -> list[str]:
    actions: list[str] = []

    if readiness.get("can_enter_expected_value_research"):
        actions.append("include item in expected-value research")
        actions.append("include item in strategy-selection research")

    if not readiness.get("has_strategy_context"):
        actions.append("add strategy context before expected-value research")

    if not readiness.get("has_symbol_context"):
        actions.append("add symbol context before expected-value research")

    if not readiness.get("has_decision_evidence"):
        actions.append("add decision evidence before expected-value research")

    if not readiness.get("has_performance_evidence"):
        actions.append(
            "add performance evidence before expected-value research"
        )

    return _sorted_unique_text(actions)


def _extract_promotion_handoff(source: Mapping[str, Any]) -> dict[str, Any]:
    promotion_handoff = source.get("promotion_handoff")

    if isinstance(promotion_handoff, Mapping):
        return deepcopy(dict(promotion_handoff))

    if (
        source.get("schema_version")
        == "historical_research_evidence_promotion_handoff.v1"
    ):
        return deepcopy(dict(source))

    operation_result = source.get("operation_result")

    if isinstance(operation_result, Mapping):
        promotion_handoff = operation_result.get("promotion_handoff")

        if isinstance(promotion_handoff, Mapping):
            return deepcopy(dict(promotion_handoff))

    pipeline_result = source.get("pipeline_result")

    if isinstance(pipeline_result, Mapping):
        promotion_handoff = pipeline_result.get("promotion_handoff")

        if isinstance(promotion_handoff, Mapping):
            return deepcopy(dict(promotion_handoff))

    return {}


def _classify_downstream_intake_status(
    *,
    handoff_status: str,
    intake_items: list[Mapping[str, Any]],
    blocked_reasons: list[str],
    can_enter_downstream: bool,
) -> str:
    if handoff_status == "blocked" or blocked_reasons:
        return "blocked"

    if handoff_status == "needs_review":
        return "needs_review"

    if not can_enter_downstream:
        return "needs_review"

    if not intake_items:
        return "needs_review"

    if any(item.get("status") == "blocked" for item in intake_items):
        return "blocked"

    if any(item.get("status") == "needs_review" for item in intake_items):
        return "needs_review"

    return "ready"


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "intake_type": INTAKE_TYPE,
        "status": "blocked",
        "summary": {
            "source_handoff_status": "invalid_shape",
            "source_handoff_type": None,
            "source_schema_version": None,
            "backtest_id": None,
            "intake_item_count": 0,
            "source_promoted_item_count": 0,
            "strategy_count": 0,
            "symbol_count": 0,
            "backtest_count": 0,
            "evidence_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "ready_intake_item_count": 0,
            "needs_review_intake_item_count": 0,
            "blocked_intake_item_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
            "can_enter_expected_value_research": False,
            "can_enter_strategy_selection": False,
        },
        "intake_items": [],
        "strategy_ids": [],
        "symbols": [],
        "backtest_ids": [],
        "evidence_ids": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_promotion_handoff_summary": {},
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
