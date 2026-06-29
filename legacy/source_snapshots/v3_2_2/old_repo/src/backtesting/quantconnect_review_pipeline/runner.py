from __future__ import annotations

from typing import Any, Mapping

from src.backtesting.quantconnect_review_handoff.operation import (
    run_quantconnect_review_handoff_operation,
)
from src.backtesting.quantconnect_review_summary.operation import (
    run_quantconnect_review_summary_operation,
)


PIPELINE_SCHEMA_VERSION = "quantconnect_review_pipeline.v1"
PIPELINE_TYPE = "manual_quantconnect_review_pipeline"

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


def run_quantconnect_review_pipeline(
    export_operation_result: Any,
    result_import_operation_result: Any,
) -> dict[str, Any]:
    """Run the deterministic manual QuantConnect review pipeline.

    This runner does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only combines existing local export and
    result-import operation artifacts into review summary and handoff results.
    """

    review_summary_operation = run_quantconnect_review_summary_operation(
        export_operation_result,
        result_import_operation_result,
    )
    review_handoff_operation = run_quantconnect_review_handoff_operation(
        review_summary_operation,
    )

    review_summary = _as_mapping(review_summary_operation.get("review_summary"))
    handoff_bundle = _as_mapping(review_handoff_operation.get("handoff_bundle"))

    warnings = _collect_warnings(review_summary, handoff_bundle)
    blocked_reasons = _collect_blocked_reasons(review_summary, handoff_bundle)

    status = _classify_pipeline_status(
        review_summary_status=str(review_summary_operation.get("status", "needs_review")),
        review_handoff_status=str(review_handoff_operation.get("status", "needs_review")),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("QuantConnect review pipeline blocked")

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    summary = _build_pipeline_summary(
        status=status,
        review_summary_operation=review_summary_operation,
        review_handoff_operation=review_handoff_operation,
        review_summary=review_summary,
        handoff_bundle=handoff_bundle,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
    )

    return {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "pipeline_type": PIPELINE_TYPE,
        "status": status,
        "summary": summary,
        "review_summary_operation": review_summary_operation,
        "review_handoff_operation": review_handoff_operation,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_pipeline_summary(
    *,
    status: str,
    review_summary_operation: Mapping[str, Any],
    review_handoff_operation: Mapping[str, Any],
    review_summary: Mapping[str, Any],
    handoff_bundle: Mapping[str, Any],
    warnings: list[str],
    blocked_reasons: list[str],
) -> dict[str, Any]:
    review_summary_record = _as_mapping(review_summary_operation.get("operation_record"))
    review_summary_record_summary = _as_mapping(review_summary_record.get("summary"))

    handoff_record = _as_mapping(review_handoff_operation.get("operation_record"))
    handoff_record_summary = _as_mapping(handoff_record.get("summary"))

    review_summary_summary = _as_mapping(review_summary.get("summary"))
    handoff_summary = _as_mapping(handoff_bundle.get("summary"))

    return {
        "pipeline_status": status,
        "backtest_id": (
            handoff_summary.get("backtest_id")
            or review_summary_summary.get("backtest_id")
            or review_summary_record_summary.get("backtest_id")
        ),
        "review_summary_status": review_summary_operation.get("status", "needs_review"),
        "review_handoff_status": review_handoff_operation.get("status", "needs_review"),
        "review_summary_audit_status": review_summary_record_summary.get(
            "audit_status"
        ),
        "review_summary_health_status": review_summary_record_summary.get(
            "health_status"
        ),
        "review_handoff_audit_status": handoff_record_summary.get("audit_status"),
        "review_handoff_health_status": handoff_record_summary.get("health_status"),
        "ready_payload_count": _safe_int(handoff_summary.get("ready_payload_count")),
        "needs_review_payload_count": _safe_int(
            handoff_summary.get("needs_review_payload_count")
        ),
        "blocked_payload_count": _safe_int(handoff_summary.get("blocked_payload_count")),
        "expected_strategy_count": _safe_int(
            handoff_summary.get("expected_strategy_count")
        ),
        "observed_strategy_count": _safe_int(
            handoff_summary.get("observed_strategy_count")
        ),
        "expected_symbol_count": _safe_int(
            handoff_summary.get("expected_symbol_count")
        ),
        "observed_symbol_count": _safe_int(
            handoff_summary.get("observed_symbol_count")
        ),
        "decision_event_count": _safe_int(handoff_summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            handoff_summary.get("performance_metric_count")
        ),
        "warning_count": len(warnings),
        "blocked_reason_count": len(blocked_reasons),
    }


def _classify_pipeline_status(
    *,
    review_summary_status: str,
    review_handoff_status: str,
    blocked_reasons: list[str],
) -> str:
    if (
        review_summary_status == "blocked"
        or review_handoff_status == "blocked"
        or blocked_reasons
    ):
        return "blocked"

    if review_summary_status == "ready" and review_handoff_status == "ready":
        return "ready"

    return "needs_review"


def _collect_warnings(
    review_summary: Mapping[str, Any],
    handoff_bundle: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(_as_text_list(review_summary.get("warnings")))
    warnings.extend(_as_text_list(handoff_bundle.get("warnings")))
    return warnings


def _collect_blocked_reasons(
    review_summary: Mapping[str, Any],
    handoff_bundle: Mapping[str, Any],
) -> list[str]:
    blocked_reasons: list[str] = []
    blocked_reasons.extend(_as_text_list(review_summary.get("blocked_reasons")))
    blocked_reasons.extend(_as_text_list(handoff_bundle.get("blocked_reasons")))
    return blocked_reasons


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
