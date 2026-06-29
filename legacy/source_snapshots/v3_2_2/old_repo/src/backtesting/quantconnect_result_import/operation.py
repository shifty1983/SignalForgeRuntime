from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_result_import.builder import (
    build_quantconnect_result_import,
)


OPERATION_SCHEMA_VERSION = "quantconnect_result_import_operation.v1"
EVENT_SCHEMA_VERSION = "quantconnect_result_import_operation_event.v1"
AUDIT_SCHEMA_VERSION = "quantconnect_result_import_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_result_import_health.v1"

OPERATION_TYPE = "quantconnect_result_import_operation"


def run_quantconnect_result_import_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic QuantConnect result import operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps manually supplied QuantConnect
    backtest results/logs with operation, audit, and health artifacts.
    """

    imported_result = build_quantconnect_result_import(source)
    audit_report = build_quantconnect_result_import_audit_report(imported_result)
    health_report = build_quantconnect_result_import_health_report(imported_result)

    events = [
        _build_event(
            imported_result=imported_result,
            event_type="quantconnect_result_import_operation_started",
            sequence=1,
        ),
        _build_event(
            imported_result=imported_result,
            event_type="quantconnect_result_import_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        imported_result=imported_result,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": imported_result["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "import_result": imported_result,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(imported_result.get("explicit_exclusions", [])),
    }


def build_quantconnect_result_import_audit_report(
    imported_result: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _as_mapping(imported_result.get("summary"))
    performance_summary = _as_mapping(imported_result.get("performance_summary"))
    signalforge_events = _as_mapping(imported_result.get("signalforge_events"))

    export_loaded_events = _as_list(signalforge_events.get("export_loaded"))
    decision_events = _as_list(signalforge_events.get("decisions"))

    checks = [
        _check(
            name="import_schema_version_present",
            passed=bool(imported_result.get("schema_version")),
            severity="blocker",
            message="import schema version is present",
            failure_message="import schema version is missing",
        ),
        _check(
            name="source_platform_is_quantconnect",
            passed=imported_result.get("source_platform") == "quantconnect",
            severity="blocker",
            message="source platform is quantconnect",
            failure_message="source platform is not quantconnect",
        ),
        _check(
            name="manual_import_type_preserved",
            passed=imported_result.get("import_type") == "manual_backtest_result_import",
            severity="blocker",
            message="manual backtest result import type is preserved",
            failure_message="unexpected result import type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(imported_result),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required manual-only exclusions are missing",
        ),
        _check(
            name="export_loaded_marker_present",
            passed=len(export_loaded_events) > 0,
            severity="warning",
            message="SIGNALFORGE_EXPORT_LOADED marker is present",
            failure_message="SIGNALFORGE_EXPORT_LOADED marker is missing",
        ),
        _check(
            name="decision_markers_present",
            passed=len(decision_events) > 0,
            severity="warning",
            message="SIGNALFORGE_DECISION markers are present",
            failure_message="SIGNALFORGE_DECISION markers are missing",
        ),
        _check(
            name="performance_statistics_present",
            passed=_has_performance_statistics(performance_summary),
            severity="warning",
            message="performance statistics are present",
            failure_message="performance statistics are missing",
        ),
        _check(
            name="decision_count_matches_summary",
            passed=_safe_int(summary.get("decision_event_count")) == len(decision_events),
            severity="blocker",
            message="decision event count matches summary",
            failure_message="decision event count does not match summary",
        ),
        _check(
            name="blocked_import_has_reason_or_error",
            passed=_blocked_import_has_reason_or_error(imported_result),
            severity="warning",
            message="blocked import reason/error handling is valid",
            failure_message="blocked import is missing blocked reasons and errors",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            import_status=str(imported_result.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(imported_result.get("explicit_exclusions", [])),
    }


def build_quantconnect_result_import_health_report(
    imported_result: Mapping[str, Any],
) -> dict[str, Any]:
    import_status = str(imported_result.get("status", "needs_review"))
    summary = _as_mapping(imported_result.get("summary"))

    indicators = {
        "import_status": import_status,
        "backtest_id": summary.get("backtest_id"),
        "log_line_count": _safe_int(summary.get("log_line_count")),
        "export_loaded_event_count": _safe_int(
            summary.get("export_loaded_event_count")
        ),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "reported_strategy_count": _safe_int(summary.get("reported_strategy_count")),
        "unique_strategy_count": _safe_int(summary.get("unique_strategy_count")),
        "unique_symbol_count": _safe_int(summary.get("unique_symbol_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "warning_count": _safe_int(summary.get("warning_count")),
        "error_count": _safe_int(summary.get("error_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        "manual_import_only": imported_result.get("import_type")
        == "manual_backtest_result_import",
    }

    recommendations = _build_health_recommendations(indicators)

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(import_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(imported_result.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    imported_result: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(imported_result.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": imported_result.get("status", "needs_review"),
        "summary": {
            "backtest_id": summary.get("backtest_id"),
            "source_status": summary.get("source_status", "needs_review"),
            "import_status": imported_result.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "log_line_count": _safe_int(summary.get("log_line_count")),
            "export_loaded_event_count": _safe_int(
                summary.get("export_loaded_event_count")
            ),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "reported_strategy_count": _safe_int(
                summary.get("reported_strategy_count")
            ),
            "unique_strategy_count": _safe_int(summary.get("unique_strategy_count")),
            "unique_symbol_count": _safe_int(summary.get("unique_symbol_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "error_count": _safe_int(summary.get("error_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(imported_result.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    imported_result: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(imported_result.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": imported_result.get("status", "needs_review"),
        "summary": {
            "backtest_id": summary.get("backtest_id"),
            "source_status": summary.get("source_status", "needs_review"),
            "import_status": imported_result.get("status", "needs_review"),
            "export_loaded_event_count": _safe_int(
                summary.get("export_loaded_event_count")
            ),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "error_count": _safe_int(summary.get("error_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(imported_result.get("explicit_exclusions", [])),
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
    import_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if import_status == "blocked":
        return "blocked"

    if import_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(import_status: str) -> str:
    if import_status == "ready":
        return "healthy"
    if import_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("export_loaded_event_count")) == 0:
        recommendations.append("include SIGNALFORGE_EXPORT_LOADED logs from QuantConnect")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include SIGNALFORGE_DECISION logs from QuantConnect")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include QuantConnect backtest statistics")

    if _safe_int(indicators.get("error_count")) > 0:
        recommendations.append("resolve QuantConnect runtime errors before review")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before promotion")

    if indicators.get("import_status") == "ready":
        recommendations.append("manual QuantConnect result import is ready for review")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(imported_result: Mapping[str, Any]) -> bool:
    required = {
        "quantconnect_api_calls",
        "broker_api_calls",
        "order_routing",
        "order_submission",
        "live_execution",
        "local_fill_simulation",
        "local_slippage_modeling",
        "external_data_warehouse_access",
    }

    exclusions = imported_result.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _has_performance_statistics(performance_summary: Mapping[str, Any]) -> bool:
    raw = performance_summary.get("raw_statistics")
    if isinstance(raw, Mapping) and raw:
        return True

    for key, value in performance_summary.items():
        if key == "raw_statistics":
            continue
        if value is not None:
            return True

    return False


def _blocked_import_has_reason_or_error(imported_result: Mapping[str, Any]) -> bool:
    if imported_result.get("status") != "blocked":
        return True

    errors = imported_result.get("errors")
    blocked_reasons = imported_result.get("blocked_reasons")

    has_errors = isinstance(errors, list) and len(errors) > 0
    has_blocked_reasons = isinstance(blocked_reasons, list) and len(blocked_reasons) > 0

    return has_errors or has_blocked_reasons


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "manual_backtest_result"
    return f"{OPERATION_TYPE}::{backtest_id}"


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
