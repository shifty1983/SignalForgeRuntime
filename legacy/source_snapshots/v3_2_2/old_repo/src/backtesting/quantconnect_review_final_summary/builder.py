from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_review_final_summary.v1"
SUMMARY_TYPE = "manual_quantconnect_review_final_summary"

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


def build_quantconnect_review_final_summary(
    review_pipeline_result: Any,
) -> dict[str, Any]:
    """Build a compact final summary from a QuantConnect review pipeline result.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only condenses an existing local review
    pipeline result into a final review artifact.
    """

    if not isinstance(review_pipeline_result, Mapping):
        return _blocked_invalid_shape("review_pipeline_result must be a mapping/dict")

    source = deepcopy(dict(review_pipeline_result))

    pipeline_result = _extract_pipeline_result(source)
    if not pipeline_result:
        return _blocked_invalid_shape(
            "review pipeline result is missing pipeline payload"
        )

    pipeline_status = str(pipeline_result.get("status", "needs_review"))
    pipeline_summary = _as_mapping(pipeline_result.get("summary"))
    review_summary_operation = _as_mapping(
        pipeline_result.get("review_summary_operation")
    )
    review_handoff_operation = _as_mapping(
        pipeline_result.get("review_handoff_operation")
    )

    review_summary = _as_mapping(review_summary_operation.get("review_summary"))
    handoff_bundle = _as_mapping(review_handoff_operation.get("handoff_bundle"))

    warnings = []
    warnings.extend(_as_text_list(pipeline_result.get("warnings")))
    warnings.extend(_as_text_list(review_summary.get("warnings")))
    warnings.extend(_as_text_list(handoff_bundle.get("warnings")))

    blocked_reasons = []
    blocked_reasons.extend(_as_text_list(pipeline_result.get("blocked_reasons")))
    blocked_reasons.extend(_as_text_list(review_summary.get("blocked_reasons")))
    blocked_reasons.extend(_as_text_list(handoff_bundle.get("blocked_reasons")))

    final_evidence_items = _build_final_evidence_items(
        pipeline_summary=pipeline_summary,
        review_summary=review_summary,
        handoff_bundle=handoff_bundle,
    )

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    status = _classify_final_status(
        pipeline_status=pipeline_status,
        ready_count=_safe_int(pipeline_summary.get("ready_payload_count")),
        needs_review_count=_safe_int(
            pipeline_summary.get("needs_review_payload_count")
        ),
        blocked_count=_safe_int(pipeline_summary.get("blocked_payload_count")),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("QuantConnect final review summary blocked")

    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": SUMMARY_TYPE,
        "status": status,
        "summary": {
            "source_pipeline_status": pipeline_status,
            "backtest_id": pipeline_summary.get("backtest_id"),
            "review_summary_status": pipeline_summary.get("review_summary_status"),
            "review_handoff_status": pipeline_summary.get("review_handoff_status"),
            "ready_evidence_count": sum(
                1 for item in final_evidence_items if item["status"] == "ready"
            ),
            "needs_review_evidence_count": sum(
                1
                for item in final_evidence_items
                if item["status"] == "needs_review"
            ),
            "blocked_evidence_count": sum(
                1 for item in final_evidence_items if item["status"] == "blocked"
            ),
            "expected_strategy_count": _safe_int(
                pipeline_summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                pipeline_summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(
                pipeline_summary.get("expected_symbol_count")
            ),
            "observed_symbol_count": _safe_int(
                pipeline_summary.get("observed_symbol_count")
            ),
            "decision_event_count": _safe_int(
                pipeline_summary.get("decision_event_count")
            ),
            "performance_metric_count": _safe_int(
                pipeline_summary.get("performance_metric_count")
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "final_evidence_items": final_evidence_items,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_pipeline_summary": _json_safe_mapping(pipeline_summary),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": SUMMARY_TYPE,
        "status": "blocked",
        "summary": {
            "source_pipeline_status": "invalid_shape",
            "backtest_id": None,
            "review_summary_status": "invalid_shape",
            "review_handoff_status": "invalid_shape",
            "ready_evidence_count": 0,
            "needs_review_evidence_count": 0,
            "blocked_evidence_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "final_evidence_items": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_pipeline_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_pipeline_result(source: Mapping[str, Any]) -> dict[str, Any]:
    if source.get("schema_version") == "quantconnect_review_pipeline.v1":
        return dict(source)

    pipeline_result = source.get("pipeline_result")
    if isinstance(pipeline_result, Mapping):
        return dict(pipeline_result)

    operation_result = source.get("operation_result")
    if isinstance(operation_result, Mapping):
        pipeline_result = operation_result.get("pipeline_result")
        if isinstance(pipeline_result, Mapping):
            return dict(pipeline_result)

    return {}


def _build_final_evidence_items(
    *,
    pipeline_summary: Mapping[str, Any],
    review_summary: Mapping[str, Any],
    handoff_bundle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ready_payloads = _as_list(handoff_bundle.get("ready_payloads"))
    needs_review_payloads = _as_list(handoff_bundle.get("needs_review_payloads"))
    blocked_payloads = _as_list(handoff_bundle.get("blocked_payloads"))

    items: list[dict[str, Any]] = []

    for payload in ready_payloads:
        if isinstance(payload, Mapping):
            items.append(
                _build_evidence_item(
                    status="ready",
                    payload=payload,
                    pipeline_summary=pipeline_summary,
                    review_summary=review_summary,
                )
            )

    for payload in needs_review_payloads:
        if isinstance(payload, Mapping):
            items.append(
                _build_evidence_item(
                    status="needs_review",
                    payload=payload,
                    pipeline_summary=pipeline_summary,
                    review_summary=review_summary,
                )
            )

    for payload in blocked_payloads:
        if isinstance(payload, Mapping):
            items.append(
                _build_evidence_item(
                    status="blocked",
                    payload=payload,
                    pipeline_summary=pipeline_summary,
                    review_summary=review_summary,
                )
            )

    return sorted(
        items,
        key=lambda item: (
            item["status"],
            item.get("backtest_id") or "",
            ",".join(item.get("symbols", [])),
        ),
    )


def _build_evidence_item(
    *,
    status: str,
    payload: Mapping[str, Any],
    pipeline_summary: Mapping[str, Any],
    review_summary: Mapping[str, Any],
) -> dict[str, Any]:
    alignment = _as_mapping(payload.get("alignment"))
    performance_summary = _as_mapping(payload.get("performance_summary"))
    decision_summary = _as_mapping(payload.get("decision_summary"))

    return {
        "status": status,
        "evidence_type": "quantconnect_manual_backtest",
        "backtest_id": payload.get("backtest_id") or pipeline_summary.get("backtest_id"),
        "review_status": payload.get("review_status") or review_summary.get("status"),
        "export_status": payload.get("export_status")
        or pipeline_summary.get("review_summary_status"),
        "import_status": payload.get("import_status"),
        "expected_strategy_count": _safe_int(
            payload.get("expected_strategy_count")
        ),
        "observed_strategy_count": _safe_int(
            payload.get("observed_strategy_count")
        ),
        "expected_symbol_count": _safe_int(payload.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(payload.get("observed_symbol_count")),
        "decision_event_count": _safe_int(payload.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            payload.get("performance_metric_count")
        ),
        "strategy_ids": _as_text_list(payload.get("observed_strategy_ids")),
        "symbols": _as_text_list(payload.get("observed_symbols")),
        "alignment_status": {
            "strategies_match": bool(alignment.get("strategies_match")),
            "symbols_match": bool(alignment.get("symbols_match")),
            "reported_count_matches_export": bool(
                alignment.get("reported_count_matches_export")
            ),
            "missing_decision_strategy_ids": _as_text_list(
                alignment.get("missing_decision_strategy_ids")
            ),
            "missing_symbols": _as_text_list(alignment.get("missing_symbols")),
        },
        "performance_snapshot": {
            "total_trades": performance_summary.get("total_trades"),
            "win_rate": performance_summary.get("win_rate"),
            "drawdown": performance_summary.get("drawdown"),
            "sharpe_ratio": performance_summary.get("sharpe_ratio"),
            "probabilistic_sharpe_ratio": performance_summary.get(
                "probabilistic_sharpe_ratio"
            ),
            "net_profit": performance_summary.get("net_profit"),
        },
        "decision_snapshot": {
            "decisions_by_strategy_id": _as_mapping(
                decision_summary.get("decisions_by_strategy_id")
            ),
            "decisions_by_symbol": _as_mapping(
                decision_summary.get("decisions_by_symbol")
            ),
            "decisions_by_signal": _as_mapping(
                decision_summary.get("decisions_by_signal")
            ),
        },
        "warnings": _sorted_unique_text(_as_text_list(payload.get("warnings"))),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(payload.get("blocked_reasons"))
        ),
    }


def _classify_final_status(
    *,
    pipeline_status: str,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if pipeline_status == "blocked" or blocked_count > 0 or blocked_reasons:
        return "blocked"

    if pipeline_status == "ready" and ready_count > 0:
        return "ready"

    if needs_review_count > 0 or pipeline_status == "needs_review":
        return "needs_review"

    return "needs_review"


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
