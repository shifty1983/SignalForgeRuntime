from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.position_maintenance.position_risk_monitor import (
    EXPLICIT_EXCLUSIONS,
    VALID_MONITOR_STATUSES,
    build_options_position_risk_monitor,
)


OPERATION_SCHEMA_VERSION = "options_position_risk_monitor_operation.v1"
EVENT_SCHEMA_VERSION = "options_position_risk_monitor_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_position_risk_monitor_audit.v1"
HEALTH_SCHEMA_VERSION = "options_position_risk_monitor_health.v1"

OPERATION_TYPE = "options_position_risk_monitor_operation"
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_position_risk_monitor_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run the scheduled options position risk monitor as an auditable operation.

    This operation is intended for weekday/live-or-near-live monitoring of open
    options positions. It creates manual risk alerts only. It does not call
    broker APIs, route orders, submit orders, model fills, perform live
    execution, model slippage, or create automatic close/roll/defense orders.
    """

    monitor = build_options_position_risk_monitor(source)
    audit_report = build_options_position_risk_monitor_audit_report(monitor)
    health_report = build_options_position_risk_monitor_health_report(monitor)

    events = [
        _build_event(
            monitor=monitor,
            event_type="options_position_risk_monitor_operation_started",
            sequence=1,
        ),
        _build_event(
            monitor=monitor,
            event_type="options_position_risk_monitor_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        monitor=monitor,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": monitor["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_position_risk_monitor": monitor,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(monitor.get("excluded", [])),
    }


def build_options_position_risk_monitor_audit_report(
    monitor: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="monitor_artifact_type_valid",
            passed=monitor.get("artifact_type") == "options_position_risk_monitor",
            severity="blocker",
            message="options position risk monitor artifact type is valid",
            failure_message="options position risk monitor artifact type is invalid",
        ),
        _check(
            name="monitor_status_valid",
            passed=monitor.get("status") in VALID_MONITOR_STATUSES,
            severity="blocker",
            message="options position risk monitor status is valid",
            failure_message="options position risk monitor status is invalid",
        ),
        _check(
            name="evaluation_timestamp_present",
            passed=bool(_string_or_none(monitor.get("evaluation_timestamp"))),
            severity="blocker",
            message="position risk monitor evaluation timestamp is present",
            failure_message="position risk monitor evaluation timestamp is missing",
        ),
        _check(
            name="plan_date_present",
            passed=bool(_string_or_none(monitor.get("plan_date"))),
            severity="blocker",
            message="position risk monitor plan date is present",
            failure_message="position risk monitor plan date is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(monitor),
            severity="blocker",
            message="position risk monitor exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="manual_approval_required",
            passed=monitor.get("requires_manual_approval") is True,
            severity="blocker",
            message="position risk monitor requires manual approval",
            failure_message="position risk monitor does not require manual approval",
        ),
        _check(
            name="risk_alerts_require_manual_approval",
            passed=_risk_alerts_require_manual_approval(monitor),
            severity="blocker",
            message="all position risk alerts require manual approval",
            failure_message="one or more position risk alerts bypass manual approval",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(monitor, "order_intent"),
            severity="blocker",
            message="position risk monitor did not create order intents",
            failure_message="position risk monitor created one or more order intents",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                monitor,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="position risk monitor did not create automatic actions",
            failure_message="position risk monitor created one or more automatic actions",
        ),
        _check(
            name="count_fields_match_monitor_lists",
            passed=_count_fields_match_monitor_lists(monitor),
            severity="blocker",
            message="position risk monitor counts match monitor lists",
            failure_message="position risk monitor counts do not match monitor lists",
        ),
        _check(
            name="blocked_monitor_has_reason",
            passed=_blocked_monitor_has_reason(monitor),
            severity="warning",
            message="blocked position risk monitor reason handling is valid",
            failure_message="blocked position risk monitor is missing blocked reasons/items",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            monitor_status=str(monitor.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(monitor.get("excluded", [])),
    }


def build_options_position_risk_monitor_health_report(
    monitor: Mapping[str, Any],
) -> dict[str, Any]:
    monitor_status = str(monitor.get("status", "needs_review"))
    warnings = list(_strings(monitor.get("warnings")))
    blocked_reasons = list(_strings(monitor.get("blocked_reasons")))
    risk_alerts = _as_list(monitor.get("risk_alerts"))
    triggered_positions = _as_list(monitor.get("triggered_positions"))
    monitor_items = _as_list(monitor.get("monitor_items"))
    blocked_items = _as_list(monitor.get("blocked_items"))
    urgency_summary = _as_mapping(monitor.get("urgency_summary"))
    trigger_summary = _as_mapping(monitor.get("trigger_summary"))

    indicators = {
        "monitor_status": monitor_status,
        "evaluation_timestamp": _string_or_none(monitor.get("evaluation_timestamp")),
        "plan_date": _string_or_none(monitor.get("plan_date")),
        "monitor_mode": _string_or_none(monitor.get("monitor_mode")),
        "market_regime": _string_or_none(monitor.get("market_regime")),
        "position_count": _safe_int(monitor.get("position_count")),
        "triggered_position_count": _safe_int(monitor.get("triggered_position_count")),
        "risk_alert_count": _safe_int(monitor.get("risk_alert_count")),
        "manual_review_count": _safe_int(monitor.get("manual_review_count")),
        "monitor_item_count": _safe_int(monitor.get("monitor_item_count")),
        "blocked_count": _safe_int(monitor.get("blocked_count")),
        "warning_count": len(warnings),
        "blocked_reason_count": len(blocked_reasons),
        "high_urgency_count": _safe_int(urgency_summary.get("high")),
        "medium_urgency_count": _safe_int(urgency_summary.get("medium")),
        "trigger_type_count": len(trigger_summary),
        "has_risk_alerts": bool(risk_alerts),
        "has_triggered_positions": bool(triggered_positions),
        "has_monitor_items": bool(monitor_items),
        "has_blocked_items": bool(blocked_items),
        "requires_manual_approval": monitor.get("requires_manual_approval") is True,
        "order_intents_created": _contains_non_null_key(monitor, "order_intent"),
        "automatic_actions_created": _contains_non_null_key(
            monitor,
            "automatic_action",
            "maintenance_action",
            "defense_action",
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(monitor_status),
        "indicators": indicators,
        "recommendations": _build_health_recommendations(indicators),
        "explicit_exclusions": list(monitor.get("excluded", [])),
    }


def _build_operation_record(
    *,
    monitor: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary = _build_summary(monitor)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": _build_operation_id(monitor),
        "status": monitor.get("status", "needs_review"),
        "evaluation_timestamp": monitor.get("evaluation_timestamp"),
        "plan_date": monitor.get("plan_date"),
        "monitor_mode": monitor.get("monitor_mode"),
        "summary": summary,
        "metadata": dict(metadata or {}),
        "audit_status": audit_report.get("status"),
        "health_status": health_report.get("status"),
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(monitor.get("excluded", [])),
    }


def _build_event(
    *,
    monitor: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "operation_id": _build_operation_id(monitor),
        "status": monitor.get("status", "needs_review"),
        "summary": _build_summary(monitor),
    }


def _build_summary(monitor: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evaluation_timestamp": _string_or_none(monitor.get("evaluation_timestamp")),
        "plan_date": _string_or_none(monitor.get("plan_date")),
        "monitor_mode": _string_or_none(monitor.get("monitor_mode")),
        "monitor_status": _string_or_none(monitor.get("status")),
        "market_regime": _string_or_none(monitor.get("market_regime")),
        "position_count": _safe_int(monitor.get("position_count")),
        "triggered_position_count": _safe_int(monitor.get("triggered_position_count")),
        "risk_alert_count": _safe_int(monitor.get("risk_alert_count")),
        "manual_review_count": _safe_int(monitor.get("manual_review_count")),
        "monitor_item_count": _safe_int(monitor.get("monitor_item_count")),
        "blocked_count": _safe_int(monitor.get("blocked_count")),
        "warning_count": len(_strings(monitor.get("warnings"))),
        "blocked_reason_count": len(_strings(monitor.get("blocked_reasons"))),
    }


def _build_operation_id(monitor: Mapping[str, Any]) -> str:
    evaluation_timestamp = (
        _string_or_none(monitor.get("evaluation_timestamp")) or "unknown_timestamp"
    )
    status = _string_or_none(monitor.get("status")) or "unknown_status"
    position_count = _safe_int(monitor.get("position_count"))
    risk_alert_count = _safe_int(monitor.get("risk_alert_count"))
    blocked_count = _safe_int(monitor.get("blocked_count"))

    return (
        f"options_position_risk_monitor:{evaluation_timestamp}:{status}:"
        f"{position_count}:{risk_alert_count}:{blocked_count}"
    )


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True))
            handle.write("\n")


def _normalize_event_log_path(event_log_path: str | PathLike[str] | None) -> Path | None:
    if event_log_path is None:
        return None
    return Path(event_log_path)


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "passed": bool(passed),
        "severity": severity,
        "message": message if passed else failure_message,
    }


def _summarize_checks(checks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    failed = [check for check in checks if not check.get("passed")]
    blockers = [check for check in failed if check.get("severity") == "blocker"]
    warnings = [check for check in failed if check.get("severity") == "warning"]

    return {
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
    }


def _classify_audit_status(*, monitor_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(
        not check.get("passed") and check.get("severity") == "blocker"
        for check in checks
    ):
        return "blocked"
    if monitor_status == "blocked":
        return "blocked"
    if monitor_status == "needs_review" or any(not check.get("passed") for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(monitor_status: str) -> str:
    if monitor_status == "blocked":
        return "blocked"
    if monitor_status == "needs_review":
        return "degraded"
    return "healthy"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if bool(indicators.get("has_risk_alerts")):
        recommendations.append("review position risk alerts requiring manual approval")

    if _safe_int(indicators.get("high_urgency_count")) > 0:
        recommendations.append("prioritize high-urgency position risk alerts")

    if bool(indicators.get("has_triggered_positions")):
        recommendations.append("review triggered option positions against strategy playbooks")

    if bool(indicators.get("has_blocked_items")):
        recommendations.append("resolve blocked position risk monitor items")

    if _safe_int(indicators.get("warning_count")) > 0:
        recommendations.append("review position risk monitor warnings")

    if bool(indicators.get("order_intents_created")):
        recommendations.append("remove order intents from position risk monitor output")

    if bool(indicators.get("automatic_actions_created")):
        recommendations.append("remove automatic actions from position risk monitor output")

    return _dedupe_strings(recommendations)


def _has_required_exclusions(monitor: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(monitor.get("excluded")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _risk_alerts_require_manual_approval(monitor: Mapping[str, Any]) -> bool:
    alerts = _as_list(monitor.get("risk_alerts"))
    return all(
        isinstance(alert, Mapping) and alert.get("requires_manual_approval") is True
        for alert in alerts
    )


def _count_fields_match_monitor_lists(monitor: Mapping[str, Any]) -> bool:
    return (
        _safe_int(monitor.get("position_count"))
        == len(_as_list(monitor.get("position_snapshots")))
        and _safe_int(monitor.get("triggered_position_count"))
        == len(_as_list(monitor.get("triggered_positions")))
        and _safe_int(monitor.get("risk_alert_count"))
        == len(_as_list(monitor.get("risk_alerts")))
        and _safe_int(monitor.get("manual_review_count"))
        == len(_as_list(monitor.get("risk_alerts")))
        and _safe_int(monitor.get("monitor_item_count"))
        == len(_as_list(monitor.get("monitor_items")))
        and _safe_int(monitor.get("blocked_count"))
        == len(_as_list(monitor.get("blocked_items")))
    )


def _blocked_monitor_has_reason(monitor: Mapping[str, Any]) -> bool:
    if monitor.get("status") != "blocked":
        return True
    return bool(
        _strings(monitor.get("blocked_reasons"))
        or _as_list(monitor.get("blocked_items"))
    )


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    key_set = set(keys)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in key_set and item is not None:
                return True
            if _contains_non_null_key(item, *keys):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_non_null_key(item, *keys) for item in value)
    return False


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)

    return output

