from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "historical_research_evidence_review_final_summary.v1"
SUMMARY_TYPE = "historical_research_evidence_review_final_summary"

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


def build_historical_research_evidence_review_final_summary(
    source: Any,
) -> dict[str, Any]:
    """Build a compact final summary from a historical research evidence review.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only summarizes an existing local evidence
    review artifact.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    review_bundle = _extract_review_bundle(source_copy)

    if not review_bundle:
        return _blocked_invalid_shape(
            "source is missing historical research evidence review bundle"
        )

    review_status = str(review_bundle.get("status", "needs_review"))
    review_summary = _as_mapping(review_bundle.get("summary"))

    final_items = []
    final_items.extend(
        _build_final_items(
            _as_list(review_bundle.get("ready_review_items")),
            status="ready",
        )
    )
    final_items.extend(
        _build_final_items(
            _as_list(review_bundle.get("needs_review_items")),
            status="needs_review",
        )
    )
    final_items.extend(
        _build_final_items(
            _as_list(review_bundle.get("blocked_review_items")),
            status="blocked",
        )
    )

    final_items = sorted(
        final_items,
        key=lambda item: (
            item.get("status") or "",
            item.get("evidence_source") or "",
            item.get("backtest_id") or "",
            item.get("evidence_id") or "",
        ),
    )

    warnings = []
    warnings.extend(_as_text_list(review_bundle.get("warnings")))
    warnings.extend(_item_warnings(final_items))

    blocked_reasons = []
    blocked_reasons.extend(_as_text_list(review_bundle.get("blocked_reasons")))
    blocked_reasons.extend(_item_blocked_reasons(final_items))

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    ready_count = sum(1 for item in final_items if item["status"] == "ready")
    needs_review_count = sum(
        1 for item in final_items if item["status"] == "needs_review"
    )
    blocked_count = sum(1 for item in final_items if item["status"] == "blocked")

    status = _classify_final_status(
        review_status=review_status,
        ready_count=ready_count,
        needs_review_count=needs_review_count,
        blocked_count=blocked_count,
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("historical research evidence review final summary is blocked")

    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": SUMMARY_TYPE,
        "status": status,
        "summary": {
            "source_review_status": review_status,
            "source_review_type": review_bundle.get("review_type"),
            "source_schema_version": review_bundle.get("schema_version"),
            "source_intake_status": review_summary.get("source_intake_status"),
            "source_intake_type": review_summary.get("source_intake_type"),
            "source_adapter_type": review_summary.get("source_adapter_type"),
            "backtest_id": review_summary.get("backtest_id"),
            "ready_final_item_count": ready_count,
            "needs_review_final_item_count": needs_review_count,
            "blocked_final_item_count": blocked_count,
            "source_ready_review_item_count": _safe_int(
                review_summary.get("ready_review_item_count")
            ),
            "source_needs_review_item_count": _safe_int(
                review_summary.get("needs_review_item_count")
            ),
            "source_blocked_review_item_count": _safe_int(
                review_summary.get("blocked_review_item_count")
            ),
            "decision_event_count": _safe_int(
                review_summary.get("decision_event_count")
            ),
            "performance_metric_count": _safe_int(
                review_summary.get("performance_metric_count")
            ),
            "expected_strategy_count": _safe_int(
                review_summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                review_summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(
                review_summary.get("expected_symbol_count")
            ),
            "observed_symbol_count": _safe_int(
                review_summary.get("observed_symbol_count")
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "final_review_items": final_items,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_review_summary": {
            "schema_version": review_bundle.get("schema_version"),
            "review_type": review_bundle.get("review_type"),
            "status": review_bundle.get("status"),
            "summary": _json_safe_mapping(review_summary),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_type": SUMMARY_TYPE,
        "status": "blocked",
        "summary": {
            "source_review_status": "invalid_shape",
            "source_review_type": None,
            "source_schema_version": None,
            "source_intake_status": None,
            "source_intake_type": None,
            "source_adapter_type": None,
            "backtest_id": None,
            "ready_final_item_count": 0,
            "needs_review_final_item_count": 0,
            "blocked_final_item_count": 0,
            "source_ready_review_item_count": 0,
            "source_needs_review_item_count": 0,
            "source_blocked_review_item_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "final_review_items": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_review_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_review_bundle(source: Mapping[str, Any]) -> dict[str, Any]:
    review_bundle = source.get("review_bundle")
    if isinstance(review_bundle, Mapping):
        return dict(review_bundle)

    if source.get("schema_version") == "historical_research_evidence_review_bundle.v1":
        return dict(source)

    operation_result = source.get("operation_result")
    if isinstance(operation_result, Mapping):
        review_bundle = operation_result.get("review_bundle")
        if isinstance(review_bundle, Mapping):
            return dict(review_bundle)

    return {}


def _build_final_items(
    review_items: list[Any],
    *,
    status: str,
) -> list[dict[str, Any]]:
    items = []

    for review_item in review_items:
        if not isinstance(review_item, Mapping):
            continue

        items.append(_build_final_item(review_item, status=status))

    return items


def _build_final_item(
    review_item: Mapping[str, Any],
    *,
    status: str,
) -> dict[str, Any]:
    review_checks = _as_list(review_item.get("review_checks"))
    readiness_summary = _as_mapping(review_item.get("readiness_summary"))
    alignment_status = _as_mapping(review_item.get("alignment_status"))
    performance_snapshot = _as_mapping(review_item.get("performance_snapshot"))
    decision_snapshot = _as_mapping(review_item.get("decision_snapshot"))

    return {
        "final_item_type": "historical_research_evidence_review_final_item",
        "status": status,
        "evidence_id": review_item.get("evidence_id"),
        "evidence_source": review_item.get("evidence_source"),
        "evidence_method": review_item.get("evidence_method"),
        "evidence_category": review_item.get("evidence_category"),
        "backtest_id": review_item.get("backtest_id"),
        "review_status": review_item.get("review_status"),
        "export_status": review_item.get("export_status"),
        "import_status": review_item.get("import_status"),
        "strategy_ids": _as_text_list(review_item.get("strategy_ids")),
        "symbols": _as_text_list(review_item.get("symbols")),
        "expected_strategy_count": _safe_int(
            review_item.get("expected_strategy_count")
        ),
        "observed_strategy_count": _safe_int(
            review_item.get("observed_strategy_count")
        ),
        "expected_symbol_count": _safe_int(review_item.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(review_item.get("observed_symbol_count")),
        "decision_event_count": _safe_int(review_item.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            review_item.get("performance_metric_count")
        ),
        "readiness_summary": _json_safe_mapping(readiness_summary),
        "alignment_status": _json_safe_mapping(alignment_status),
        "performance_snapshot": _build_performance_snapshot(performance_snapshot),
        "decision_snapshot": _json_safe_mapping(decision_snapshot),
        "review_check_summary": _build_review_check_summary(review_checks),
        "review_actions": _as_text_list(review_item.get("review_actions")),
        "warnings": _sorted_unique_text(_as_text_list(review_item.get("warnings"))),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(review_item.get("blocked_reasons"))
        ),
    }


def _build_performance_snapshot(
    performance_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "total_trades": performance_snapshot.get("total_trades"),
        "win_rate": performance_snapshot.get("win_rate"),
        "drawdown": performance_snapshot.get("drawdown"),
        "sharpe_ratio": performance_snapshot.get("sharpe_ratio"),
        "probabilistic_sharpe_ratio": performance_snapshot.get(
            "probabilistic_sharpe_ratio"
        ),
        "net_profit": performance_snapshot.get("net_profit"),
    }


def _build_review_check_summary(
    review_checks: list[Any],
) -> dict[str, int]:
    checks = [check for check in review_checks if isinstance(check, Mapping)]

    return {
        "check_count": len(checks),
        "passed_count": sum(1 for check in checks if check.get("status") == "passed"),
        "needs_review_count": sum(
            1 for check in checks if check.get("status") == "needs_review"
        ),
    }


def _classify_final_status(
    *,
    review_status: str,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if review_status == "blocked" or blocked_count > 0 or blocked_reasons:
        return "blocked"

    if review_status == "ready" and ready_count > 0 and needs_review_count == 0:
        return "ready"

    if review_status == "needs_review" or needs_review_count > 0:
        return "needs_review"

    return "needs_review"


def _item_warnings(items: list[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []

    for item in items:
        warnings.extend(_as_text_list(item.get("warnings")))

    return warnings


def _item_blocked_reasons(items: list[Mapping[str, Any]]) -> list[str]:
    blocked_reasons: list[str] = []

    for item in items:
        blocked_reasons.extend(_as_text_list(item.get("blocked_reasons")))

    return blocked_reasons


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
