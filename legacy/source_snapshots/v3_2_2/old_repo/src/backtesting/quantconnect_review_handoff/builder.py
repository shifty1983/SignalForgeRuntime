from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_review_handoff_bundle.v1"
HANDOFF_TYPE = "manual_quantconnect_backtest_review_handoff"

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


def build_quantconnect_review_handoff_bundle(
    review_summary_operation_result: Any,
) -> dict[str, Any]:
    """Build a deterministic handoff bundle from a QuantConnect review summary.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only converts an existing local review
    summary operation result into a compact downstream review handoff bundle.
    """

    if not isinstance(review_summary_operation_result, Mapping):
        return _blocked_invalid_shape("review_summary_operation_result must be a mapping/dict")

    source = deepcopy(dict(review_summary_operation_result))
    review_summary = _extract_review_summary(source)

    if not review_summary:
        return _blocked_invalid_shape(
            "review summary operation result is missing review_summary payload"
        )

    review_status = str(review_summary.get("status", "needs_review"))
    summary = _as_mapping(review_summary.get("summary"))
    alignment = _as_mapping(review_summary.get("alignment"))
    decision_summary = _as_mapping(review_summary.get("decision_summary"))
    performance_summary = _as_mapping(review_summary.get("performance_summary"))

    warnings = _sorted_unique_text(_as_text_list(review_summary.get("warnings")))
    blocked_reasons = _sorted_unique_text(
        _as_text_list(review_summary.get("blocked_reasons"))
    )

    payload = _build_handoff_payload(
        review_summary=review_summary,
        summary=summary,
        alignment=alignment,
        decision_summary=decision_summary,
        performance_summary=performance_summary,
    )

    ready_payloads: list[dict[str, Any]] = []
    needs_review_payloads: list[dict[str, Any]] = []
    blocked_payloads: list[dict[str, Any]] = []

    if review_status == "ready":
        ready_payloads.append(payload)
    elif review_status == "blocked":
        blocked_payloads.append(payload)
    else:
        needs_review_payloads.append(payload)

    status = _classify_handoff_status(
        review_status=review_status,
        ready_count=len(ready_payloads),
        needs_review_count=len(needs_review_payloads),
        blocked_count=len(blocked_payloads),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("QuantConnect review handoff is blocked")

    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_type": HANDOFF_TYPE,
        "status": status,
        "summary": {
            "source_review_status": review_status,
            "backtest_id": summary.get("backtest_id"),
            "ready_payload_count": len(ready_payloads),
            "needs_review_payload_count": len(needs_review_payloads),
            "blocked_payload_count": len(blocked_payloads),
            "expected_strategy_count": _safe_int(summary.get("expected_strategy_count")),
            "observed_strategy_count": _safe_int(summary.get("observed_strategy_count")),
            "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
            "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "ready_payloads": ready_payloads,
        "needs_review_payloads": needs_review_payloads,
        "blocked_payloads": blocked_payloads,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_operation_summary": _operation_summary(source),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_type": HANDOFF_TYPE,
        "status": "blocked",
        "summary": {
            "source_review_status": "invalid_shape",
            "backtest_id": None,
            "ready_payload_count": 0,
            "needs_review_payload_count": 0,
            "blocked_payload_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "ready_payloads": [],
        "needs_review_payloads": [],
        "blocked_payloads": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_operation_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_review_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    review_summary = source.get("review_summary")
    if isinstance(review_summary, Mapping):
        return dict(review_summary)

    if source.get("schema_version") == "quantconnect_review_summary.v1":
        return dict(source)

    operation_result = source.get("operation_result")
    if isinstance(operation_result, Mapping):
        review_summary = operation_result.get("review_summary")
        if isinstance(review_summary, Mapping):
            return dict(review_summary)

    return {}


def _build_handoff_payload(
    *,
    review_summary: Mapping[str, Any],
    summary: Mapping[str, Any],
    alignment: Mapping[str, Any],
    decision_summary: Mapping[str, Any],
    performance_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "payload_type": "quantconnect_manual_backtest_evidence",
        "review_status": review_summary.get("status", "needs_review"),
        "backtest_id": summary.get("backtest_id"),
        "export_status": summary.get("export_status"),
        "import_status": summary.get("import_status"),
        "expected_strategy_count": _safe_int(summary.get("expected_strategy_count")),
        "observed_strategy_count": _safe_int(summary.get("observed_strategy_count")),
        "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "expected_strategy_ids": _as_text_list(alignment.get("expected_strategy_ids")),
        "observed_strategy_ids": _as_text_list(alignment.get("observed_strategy_ids")),
        "expected_symbols": _as_text_list(alignment.get("expected_symbols")),
        "observed_symbols": _as_text_list(alignment.get("observed_symbols")),
        "alignment": _json_safe_mapping(alignment),
        "decision_summary": _json_safe_mapping(decision_summary),
        "performance_summary": _json_safe_mapping(performance_summary),
        "warnings": _sorted_unique_text(_as_text_list(review_summary.get("warnings"))),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(review_summary.get("blocked_reasons"))
        ),
    }


def _classify_handoff_status(
    *,
    review_status: str,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if review_status == "blocked" or blocked_count > 0 or blocked_reasons:
        return "blocked"

    if ready_count > 0 and needs_review_count == 0:
        return "ready"

    if needs_review_count > 0:
        return "needs_review"

    return "needs_review"


def _operation_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    operation_record = source.get("operation_record")
    if isinstance(operation_record, Mapping):
        summary = operation_record.get("summary")
        if isinstance(summary, Mapping):
            return _json_safe_mapping(summary)

    summary = source.get("summary")
    if isinstance(summary, Mapping):
        return _json_safe_mapping(summary)

    return {}


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()] if str(value).strip() else []


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


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
        if isinstance(item, Mapping):
            safe[str(key)] = _json_safe_mapping(item)
        elif isinstance(item, list):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, tuple):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
        else:
            safe[str(key)] = str(item)

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
