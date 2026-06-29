from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_review_handoff.builder import (
    build_quantconnect_review_handoff_bundle,
)


OPERATION_SCHEMA_VERSION = "quantconnect_review_handoff_operation.v1"
EVENT_SCHEMA_VERSION = "quantconnect_review_handoff_operation_event.v1"
AUDIT_SCHEMA_VERSION = "quantconnect_review_handoff_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_review_handoff_health.v1"

OPERATION_TYPE = "quantconnect_review_handoff_operation"


def run_quantconnect_review_handoff_operation(
    review_summary_operation_result: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic QuantConnect review handoff operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps an existing local review summary
    operation result with operation, audit, and health artifacts.
    """

    handoff_bundle = build_quantconnect_review_handoff_bundle(
        review_summary_operation_result
    )
    audit_report = build_quantconnect_review_handoff_audit_report(handoff_bundle)
    health_report = build_quantconnect_review_handoff_health_report(handoff_bundle)

    events = [
        _build_event(
            handoff_bundle=handoff_bundle,
            event_type="quantconnect_review_handoff_operation_started",
            sequence=1,
        ),
        _build_event(
            handoff_bundle=handoff_bundle,
            event_type="quantconnect_review_handoff_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        handoff_bundle=handoff_bundle,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": handoff_bundle["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "handoff_bundle": handoff_bundle,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(handoff_bundle.get("explicit_exclusions", [])),
    }


def build_quantconnect_review_handoff_audit_report(
    handoff_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _as_mapping(handoff_bundle.get("summary"))

    checks = [
        _check(
            name="handoff_schema_version_present",
            passed=bool(handoff_bundle.get("schema_version")),
            severity="blocker",
            message="handoff schema version is present",
            failure_message="handoff schema version is missing",
        ),
        _check(
            name="handoff_type_is_manual_quantconnect_backtest_review_handoff",
            passed=handoff_bundle.get("handoff_type")
            == "manual_quantconnect_backtest_review_handoff",
            severity="blocker",
            message="handoff type is manual QuantConnect backtest review handoff",
            failure_message="unexpected handoff type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(handoff_bundle),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required manual-only exclusions are missing",
        ),
        _check(
            name="payload_count_matches_status",
            passed=_payload_count_matches_status(handoff_bundle),
            severity="blocker",
            message="payload count matches handoff status",
            failure_message="payload count does not match handoff status",
        ),
        _check(
            name="ready_handoff_has_payload",
            passed=_safe_int(summary.get("ready_payload_count")) > 0
            if handoff_bundle.get("status") == "ready"
            else True,
            severity="blocker",
            message="ready handoff has a ready payload",
            failure_message="ready handoff is missing ready payload",
        ),
        _check(
            name="evidence_has_backtest_id",
            passed=bool(summary.get("backtest_id"))
            if handoff_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="handoff evidence has backtest id",
            failure_message="handoff evidence is missing backtest id",
        ),
        _check(
            name="evidence_has_decision_events",
            passed=_safe_int(summary.get("decision_event_count")) > 0
            if handoff_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="handoff evidence has decision events",
            failure_message="handoff evidence is missing decision events",
        ),
        _check(
            name="evidence_has_performance_metrics",
            passed=_safe_int(summary.get("performance_metric_count")) > 0
            if handoff_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="handoff evidence has performance metrics",
            failure_message="handoff evidence is missing performance metrics",
        ),
        _check(
            name="blocked_handoff_has_reason",
            passed=_blocked_handoff_has_reason(handoff_bundle),
            severity="warning",
            message="blocked handoff reason handling is valid",
            failure_message="blocked handoff is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            handoff_status=str(handoff_bundle.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(handoff_bundle.get("explicit_exclusions", [])),
    }


def build_quantconnect_review_handoff_health_report(
    handoff_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    handoff_status = str(handoff_bundle.get("status", "needs_review"))
    summary = _as_mapping(handoff_bundle.get("summary"))

    indicators = {
        "handoff_status": handoff_status,
        "source_review_status": summary.get("source_review_status"),
        "backtest_id": summary.get("backtest_id"),
        "ready_payload_count": _safe_int(summary.get("ready_payload_count")),
        "needs_review_payload_count": _safe_int(
            summary.get("needs_review_payload_count")
        ),
        "blocked_payload_count": _safe_int(summary.get("blocked_payload_count")),
        "expected_strategy_count": _safe_int(summary.get("expected_strategy_count")),
        "observed_strategy_count": _safe_int(summary.get("observed_strategy_count")),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "warning_count": _safe_int(summary.get("warning_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
    }

    recommendations = _build_health_recommendations(indicators)

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(handoff_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(handoff_bundle.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    handoff_bundle: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(handoff_bundle.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": handoff_bundle.get("status", "needs_review"),
        "summary": {
            "source_review_status": summary.get("source_review_status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "handoff_status": handoff_bundle.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "ready_payload_count": _safe_int(summary.get("ready_payload_count")),
            "needs_review_payload_count": _safe_int(
                summary.get("needs_review_payload_count")
            ),
            "blocked_payload_count": _safe_int(summary.get("blocked_payload_count")),
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
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(handoff_bundle.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    handoff_bundle: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(handoff_bundle.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": handoff_bundle.get("status", "needs_review"),
        "summary": {
            "source_review_status": summary.get("source_review_status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "handoff_status": handoff_bundle.get("status", "needs_review"),
            "ready_payload_count": _safe_int(summary.get("ready_payload_count")),
            "needs_review_payload_count": _safe_int(
                summary.get("needs_review_payload_count")
            ),
            "blocked_payload_count": _safe_int(summary.get("blocked_payload_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(handoff_bundle.get("explicit_exclusions", [])),
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
    handoff_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if handoff_status == "blocked":
        return "blocked"

    if handoff_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(handoff_status: str) -> str:
    if handoff_status == "ready":
        return "healthy"
    if handoff_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("ready_payload_count")) == 0 and indicators.get(
        "handoff_status"
    ) == "ready":
        recommendations.append("add a ready QuantConnect review handoff payload")

    if _safe_int(indicators.get("needs_review_payload_count")) > 0:
        recommendations.append("review QuantConnect handoff warnings before promotion")

    if _safe_int(indicators.get("blocked_payload_count")) > 0:
        recommendations.append("resolve blocked QuantConnect handoff payloads")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include SignalForge decision evidence")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include QuantConnect performance statistics")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before downstream review")

    if indicators.get("handoff_status") == "ready":
        recommendations.append("QuantConnect review handoff is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(handoff_bundle: Mapping[str, Any]) -> bool:
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

    exclusions = handoff_bundle.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _payload_count_matches_status(handoff_bundle: Mapping[str, Any]) -> bool:
    summary = _as_mapping(handoff_bundle.get("summary"))
    status = handoff_bundle.get("status")

    ready_count = _safe_int(summary.get("ready_payload_count"))
    needs_review_count = _safe_int(summary.get("needs_review_payload_count"))
    blocked_count = _safe_int(summary.get("blocked_payload_count"))

    if status == "ready":
        return ready_count > 0 and needs_review_count == 0 and blocked_count == 0

    if status == "needs_review":
        return needs_review_count > 0 and blocked_count == 0

    if status == "blocked":
        return blocked_count > 0 or _safe_int(summary.get("blocked_reason_count")) > 0

    return False


def _blocked_handoff_has_reason(handoff_bundle: Mapping[str, Any]) -> bool:
    if handoff_bundle.get("status") != "blocked":
        return True

    blocked_reasons = handoff_bundle.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "manual_quantconnect_review_handoff"
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
