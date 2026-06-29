from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_review_summary.builder import (
    build_quantconnect_review_summary,
)


OPERATION_SCHEMA_VERSION = "quantconnect_review_summary_operation.v1"
EVENT_SCHEMA_VERSION = "quantconnect_review_summary_operation_event.v1"
AUDIT_SCHEMA_VERSION = "quantconnect_review_summary_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_review_summary_health.v1"

OPERATION_TYPE = "quantconnect_review_summary_operation"


def run_quantconnect_review_summary_operation(
    export_operation_result: Any,
    result_import_operation_result: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic QuantConnect review summary operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps local QuantConnect export and
    result-import artifacts with operation, audit, and health outputs.
    """

    review_summary = build_quantconnect_review_summary(
        export_operation_result,
        result_import_operation_result,
    )
    audit_report = build_quantconnect_review_summary_audit_report(review_summary)
    health_report = build_quantconnect_review_summary_health_report(review_summary)

    events = [
        _build_event(
            review_summary=review_summary,
            event_type="quantconnect_review_summary_operation_started",
            sequence=1,
        ),
        _build_event(
            review_summary=review_summary,
            event_type="quantconnect_review_summary_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        review_summary=review_summary,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": review_summary["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "review_summary": review_summary,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(review_summary.get("explicit_exclusions", [])),
    }


def build_quantconnect_review_summary_audit_report(
    review_summary: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _as_mapping(review_summary.get("summary"))
    alignment = _as_mapping(review_summary.get("alignment"))
    decision_summary = _as_mapping(review_summary.get("decision_summary"))

    checks = [
        _check(
            name="review_schema_version_present",
            passed=bool(review_summary.get("schema_version")),
            severity="blocker",
            message="review summary schema version is present",
            failure_message="review summary schema version is missing",
        ),
        _check(
            name="review_type_is_manual_quantconnect_backtest_review",
            passed=review_summary.get("review_type")
            == "manual_quantconnect_backtest_review",
            severity="blocker",
            message="review type is manual QuantConnect backtest review",
            failure_message="unexpected review type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(review_summary),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required manual-only exclusions are missing",
        ),
        _check(
            name="export_and_import_status_present",
            passed=bool(summary.get("export_status")) and bool(summary.get("import_status")),
            severity="blocker",
            message="export and import statuses are present",
            failure_message="export or import status is missing",
        ),
        _check(
            name="export_loaded_marker_present",
            passed=bool(alignment.get("has_export_loaded_marker")),
            severity="warning",
            message="SIGNALFORGE_EXPORT_LOADED marker is present",
            failure_message="SIGNALFORGE_EXPORT_LOADED marker is missing",
        ),
        _check(
            name="decision_events_present",
            passed=bool(alignment.get("has_decision_events")),
            severity="warning",
            message="SIGNALFORGE_DECISION events are present",
            failure_message="SIGNALFORGE_DECISION events are missing",
        ),
        _check(
            name="strategies_match",
            passed=bool(alignment.get("strategies_match")),
            severity="warning",
            message="exported strategies match observed decision strategies",
            failure_message="exported strategies do not match observed decisions",
        ),
        _check(
            name="symbols_match",
            passed=bool(alignment.get("symbols_match")),
            severity="warning",
            message="exported symbols match observed decision symbols",
            failure_message="exported symbols do not match observed decisions",
        ),
        _check(
            name="reported_count_matches_export",
            passed=bool(alignment.get("reported_count_matches_export")),
            severity="warning",
            message="reported strategy count matches export",
            failure_message="reported strategy count does not match export",
        ),
        _check(
            name="performance_metrics_present",
            passed=_safe_int(summary.get("performance_metric_count")) > 0,
            severity="warning",
            message="performance metrics are present",
            failure_message="performance metrics are missing",
        ),
        _check(
            name="decision_count_matches_summary",
            passed=_safe_int(summary.get("decision_event_count"))
            == _safe_int(decision_summary.get("decision_event_count")),
            severity="blocker",
            message="decision event count matches decision summary",
            failure_message="decision event count does not match decision summary",
        ),
        _check(
            name="blocked_review_has_reason",
            passed=_blocked_review_has_reason(review_summary),
            severity="warning",
            message="blocked review reason handling is valid",
            failure_message="blocked review is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            review_status=str(review_summary.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(review_summary.get("explicit_exclusions", [])),
    }


def build_quantconnect_review_summary_health_report(
    review_summary: Mapping[str, Any],
) -> dict[str, Any]:
    review_status = str(review_summary.get("status", "needs_review"))
    summary = _as_mapping(review_summary.get("summary"))
    alignment = _as_mapping(review_summary.get("alignment"))

    indicators = {
        "review_status": review_status,
        "export_status": summary.get("export_status"),
        "import_status": summary.get("import_status"),
        "backtest_id": summary.get("backtest_id"),
        "expected_strategy_count": _safe_int(summary.get("expected_strategy_count")),
        "observed_strategy_count": _safe_int(summary.get("observed_strategy_count")),
        "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "warning_count": _safe_int(summary.get("warning_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        "has_export_loaded_marker": bool(alignment.get("has_export_loaded_marker")),
        "has_decision_events": bool(alignment.get("has_decision_events")),
        "strategies_match": bool(alignment.get("strategies_match")),
        "symbols_match": bool(alignment.get("symbols_match")),
        "reported_count_matches_export": bool(
            alignment.get("reported_count_matches_export")
        ),
    }

    recommendations = _build_health_recommendations(indicators)

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(review_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(review_summary.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    review_summary: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(review_summary.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": review_summary.get("status", "needs_review"),
        "summary": {
            "backtest_id": summary.get("backtest_id"),
            "export_status": summary.get("export_status", "needs_review"),
            "import_status": summary.get("import_status", "needs_review"),
            "review_status": review_summary.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "expected_strategy_count": _safe_int(
                summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
            "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(review_summary.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    review_summary: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(review_summary.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": review_summary.get("status", "needs_review"),
        "summary": {
            "backtest_id": summary.get("backtest_id"),
            "export_status": summary.get("export_status", "needs_review"),
            "import_status": summary.get("import_status", "needs_review"),
            "review_status": review_summary.get("status", "needs_review"),
            "expected_strategy_count": _safe_int(
                summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                summary.get("observed_strategy_count")
            ),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(review_summary.get("explicit_exclusions", [])),
    }


def _write_jsonl_event_log(path: Path, events: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, sort_keys=True))
            file.write("\n")


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    return Path(path)


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
    if passed:
        return {
            "name": name,
            "status": "passed",
            "severity": severity,
            "message": message,
        }

    failed_status = "failed" if severity == "blocker" else "warning"
    return {
        "name": name,
        "status": failed_status,
        "severity": severity,
        "message": failure_message,
    }


def _summarize_checks(checks: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "passed_count": sum(1 for check in checks if check.get("status") == "passed"),
        "warning_count": sum(1 for check in checks if check.get("status") == "warning"),
        "failed_count": sum(1 for check in checks if check.get("status") == "failed"),
        "check_count": len(checks),
    }


def _classify_audit_status(
    *,
    review_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if review_status == "blocked":
        return "blocked"

    if review_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(review_status: str) -> str:
    if review_status == "ready":
        return "healthy"
    if review_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if not indicators.get("has_export_loaded_marker"):
        recommendations.append("include SIGNALFORGE_EXPORT_LOADED logs from QuantConnect")

    if not indicators.get("has_decision_events"):
        recommendations.append("include SIGNALFORGE_DECISION logs from QuantConnect")

    if not indicators.get("strategies_match"):
        recommendations.append("review exported strategy IDs against observed decisions")

    if not indicators.get("symbols_match"):
        recommendations.append("review exported symbols against observed decisions")

    if not indicators.get("reported_count_matches_export"):
        recommendations.append("confirm exported strategy count matches QuantConnect logs")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include QuantConnect backtest statistics")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before historical review")

    if indicators.get("review_status") == "ready":
        recommendations.append("manual QuantConnect review summary is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(review_summary: Mapping[str, Any]) -> bool:
    required = {
        "quantconnect_api_calls",
        "broker_api_calls",
        "order_routing",
        "order_submission",
        "fills",
        "live_execution",
        "local_fill_simulation",
        "local_slippage_modeling",
        "external_data_warehouse_access",
    }

    exclusions = review_summary.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _blocked_review_has_reason(review_summary: Mapping[str, Any]) -> bool:
    if review_summary.get("status") != "blocked":
        return True

    blocked_reasons = review_summary.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "manual_quantconnect_backtest_review"
    return f"{OPERATION_TYPE}::{backtest_id}"


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
