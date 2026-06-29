from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report import (
    EXPLICIT_EXCLUSIONS,
    build_options_portfolio_control_report,
)


OPERATION_SCHEMA_VERSION = "options_portfolio_control_report_operation.v1"
EVENT_SCHEMA_VERSION = "options_portfolio_control_report_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_portfolio_control_report_audit.v1"
HEALTH_SCHEMA_VERSION = "options_portfolio_control_report_health.v1"

OPERATION_TYPE = "options_portfolio_control_report_operation"
VALID_REPORT_STATUSES = {"ready", "needs_review", "blocked"}
VALID_ACTION_PRIORITIES = {"high", "normal"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_portfolio_control_report_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    control_report = build_options_portfolio_control_report(source or {})
    audit_report = build_options_portfolio_control_report_audit_report(control_report)
    health_report = build_options_portfolio_control_report_health_report(control_report)

    operation_status = _classify_operation_status(
        report_status=str(control_report.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            control_report=control_report,
            event_type="options_portfolio_control_report_operation_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            control_report=control_report,
            event_type="options_portfolio_control_report_operation_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        control_report=control_report,
        audit_report=audit_report,
        health_report=health_report,
        operation_status=operation_status,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_status,
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_portfolio_control_report": control_report,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(control_report.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_audit_report(
    control_report: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="control_report_artifact_type_valid",
            passed=control_report.get("artifact_type") == "options_portfolio_control_report",
            severity="blocker",
            message="options portfolio control report artifact type is valid",
            failure_message="options portfolio control report artifact type is invalid",
        ),
        _check(
            name="control_report_status_valid",
            passed=control_report.get("status") in VALID_REPORT_STATUSES,
            severity="blocker",
            message="options portfolio control report status is valid",
            failure_message="options portfolio control report status is invalid",
        ),
        _check(
            name="control_summary_present",
            passed=isinstance(control_report.get("control_summary"), Mapping),
            severity="blocker",
            message="options portfolio control summary is present",
            failure_message="options portfolio control summary is missing",
        ),
        _check(
            name="operator_dashboard_present",
            passed=isinstance(control_report.get("operator_dashboard"), Mapping),
            severity="blocker",
            message="options portfolio operator dashboard is present",
            failure_message="options portfolio operator dashboard is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(control_report),
            severity="blocker",
            message="options portfolio control report exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(control_report, "order_intent"),
            severity="blocker",
            message="options portfolio control report did not create order intents",
            failure_message="options portfolio control report created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(control_report, "broker_order_id"),
            severity="blocker",
            message="options portfolio control report did not create broker order ids",
            failure_message="options portfolio control report created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                control_report,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options portfolio control report did not create automatic actions",
            failure_message="options portfolio control report created one or more automatic actions",
        ),
        _check(
            name="no_automatic_strategy_or_parameter_changes_created",
            passed=not _contains_non_null_key(
                control_report,
                "automatic_strategy_change",
                "automatic_parameter_change",
                "strategy_change",
                "parameter_change",
            ),
            severity="blocker",
            message="options portfolio control report did not create automatic strategy or parameter changes",
            failure_message="options portfolio control report created automatic strategy or parameter changes",
        ),
        _check(
            name="no_automatic_pause_actions_created",
            passed=not _contains_non_null_key(
                control_report,
                "automatic_pause_action",
                "pause_action",
            ),
            severity="blocker",
            message="options portfolio control report did not create automatic pause actions",
            failure_message="options portfolio control report created automatic pause actions",
        ),
        _check(
            name="control_actions_have_valid_priorities",
            passed=_control_actions_have_valid_priorities(control_report),
            severity="warning",
            message="options portfolio control actions have valid priorities",
            failure_message="one or more options portfolio control actions have invalid priorities",
        ),
        _check(
            name="control_actions_require_manual_approval",
            passed=_control_actions_require_manual_approval(control_report),
            severity="warning",
            message="options portfolio control actions require manual approval",
            failure_message="one or more options portfolio control actions do not require manual approval",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(control_report),
            severity="warning",
            message="blocked options portfolio control items include reasons",
            failure_message="one or more blocked options portfolio control items are missing reasons",
        ),
    ]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            report_status=str(control_report.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": _summarize_checks(checks),
        "checks": checks,
        "explicit_exclusions": list(control_report.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_health_report(
    control_report: Mapping[str, Any],
) -> dict[str, Any]:
    report_status = str(control_report.get("status", "needs_review"))
    control_summary = _as_mapping(control_report.get("control_summary"))
    operator_dashboard = _as_mapping(control_report.get("operator_dashboard"))
    blocked_items = _as_list(control_report.get("blocked_items"))
    needs_review_items = _as_list(control_report.get("needs_review_items"))
    missing_sections = _as_list(control_report.get("missing_sections"))
    control_actions = _as_list(control_report.get("control_actions"))

    indicators = {
        "report_status": report_status,
        "report_date": _string_or_none(control_report.get("report_date")),
        "section_count": _safe_int(control_summary.get("section_count")),
        "present_section_count": _safe_int(control_summary.get("present_section_count")),
        "missing_section_count": _safe_int(control_summary.get("missing_section_count")),
        "ready_section_count": _safe_int(control_summary.get("ready_section_count")),
        "needs_review_section_count": _safe_int(control_summary.get("needs_review_section_count")),
        "blocked_section_count": _safe_int(control_summary.get("blocked_section_count")),
        "blocked_item_count": len(blocked_items),
        "needs_review_item_count": len(needs_review_items),
        "missing_record_count": len(missing_sections),
        "total_item_count": _safe_int(control_summary.get("total_item_count")),
        "total_manual_action_count": _safe_int(control_summary.get("total_manual_action_count")),
        "control_action_count": len(control_actions),
        "can_consider_new_trades": operator_dashboard.get("can_consider_new_trades") is True,
        "needs_position_defense_review": operator_dashboard.get("needs_position_defense_review") is True,
        "manual_actions_require_review": operator_dashboard.get("manual_actions_require_review") is True,
        "human_decision_logged": operator_dashboard.get("human_decision_logged") is True,
        "human_decision_count": _safe_int(operator_dashboard.get("human_decision_count")),
        "overall_edge_classification": _string_or_none(
            operator_dashboard.get("overall_edge_classification")
        ),
        "strategy_improvement_decision": _string_or_none(
            operator_dashboard.get("strategy_improvement_decision")
        ),
        "has_blocked_items": bool(blocked_items),
        "has_needs_review_items": bool(needs_review_items),
        "has_missing_sections": bool(missing_sections),
        "has_order_intent": _contains_non_null_key(control_report, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(control_report, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(control_report, "automatic_action"),
        "has_automatic_strategy_change": _contains_non_null_key(
            control_report,
            "automatic_strategy_change",
            "automatic_parameter_change",
            "strategy_change",
            "parameter_change",
        ),
        "has_automatic_pause_action": _contains_non_null_key(
            control_report,
            "automatic_pause_action",
            "pause_action",
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            report_status=report_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(control_report.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    control_report: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    control_summary = _as_mapping(control_report.get("control_summary"))
    operator_dashboard = _as_mapping(control_report.get("operator_dashboard"))

    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "report_date": _string_or_none(control_report.get("report_date")),
        "operation_summary": {
            "section_count": _safe_int(control_summary.get("section_count")),
            "present_section_count": _safe_int(control_summary.get("present_section_count")),
            "missing_section_count": _safe_int(control_summary.get("missing_section_count")),
            "ready_section_count": _safe_int(control_summary.get("ready_section_count")),
            "needs_review_section_count": _safe_int(control_summary.get("needs_review_section_count")),
            "blocked_section_count": _safe_int(control_summary.get("blocked_section_count")),
            "blocked_item_count": _safe_int(control_summary.get("blocked_item_count")),
            "needs_review_item_count": _safe_int(control_summary.get("needs_review_item_count")),
            "total_item_count": _safe_int(control_summary.get("total_item_count")),
            "total_manual_action_count": _safe_int(control_summary.get("total_manual_action_count")),
            "can_consider_new_trades": operator_dashboard.get("can_consider_new_trades"),
            "needs_position_defense_review": operator_dashboard.get("needs_position_defense_review"),
            "manual_actions_require_review": operator_dashboard.get("manual_actions_require_review"),
            "overall_edge_classification": operator_dashboard.get("overall_edge_classification"),
            "strategy_improvement_decision": operator_dashboard.get("strategy_improvement_decision"),
            "human_decision_logged": operator_dashboard.get("human_decision_logged"),
            "human_decision_count": _safe_int(operator_dashboard.get("human_decision_count")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(control_report.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    control_report: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    control_summary = _as_mapping(control_report.get("control_summary"))
    operator_dashboard = _as_mapping(control_report.get("operator_dashboard"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "report_date": _string_or_none(control_report.get("report_date")),
        "present_section_count": _safe_int(control_summary.get("present_section_count")),
        "missing_section_count": _safe_int(control_summary.get("missing_section_count")),
        "blocked_item_count": _safe_int(control_summary.get("blocked_item_count")),
        "needs_review_item_count": _safe_int(control_summary.get("needs_review_item_count")),
        "can_consider_new_trades": operator_dashboard.get("can_consider_new_trades"),
        "human_decision_logged": operator_dashboard.get("human_decision_logged"),
    }


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
        "passed": bool(passed),
        "severity": severity,
        "message": message if passed else failure_message,
    }


def _summarize_checks(checks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    passed = sum(1 for check in checks if check.get("passed") is True)
    failed = len(checks) - passed
    blockers = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") == "blocker"
    )
    warnings = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") != "blocker"
    )
    return {
        "check_count": len(checks),
        "passed_count": passed,
        "failed_count": failed,
        "blocker_count": blockers,
        "warning_count": warnings,
    }


def _classify_operation_status(
    *,
    report_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {report_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {report_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(
    *,
    report_status: str,
    checks: Sequence[Mapping[str, Any]],
) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if report_status == "blocked":
        return "blocked"
    if report_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(
    *,
    report_status: str,
    indicators: Mapping[str, Any],
) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
        or indicators.get("has_automatic_strategy_change")
        or indicators.get("has_automatic_pause_action")
    ):
        return "blocked"

    if report_status == "blocked" or indicators.get("has_blocked_items"):
        return "blocked"

    if (
        report_status == "needs_review"
        or indicators.get("has_needs_review_items")
        or indicators.get("has_missing_sections")
        or indicators.get("needs_position_defense_review")
        or indicators.get("manual_actions_require_review")
    ):
        return "needs_review"

    return "ready"


def _has_required_exclusions(control_report: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(control_report.get("explicit_exclusions")))
    return all(item in exclusions for item in REQUIRED_EXCLUSIONS)


def _control_actions_have_valid_priorities(control_report: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("priority") in VALID_ACTION_PRIORITIES
        for item in _as_list(control_report.get("control_actions"))
    )


def _control_actions_require_manual_approval(control_report: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("requires_manual_approval") is True
        for item in _as_list(control_report.get("control_actions"))
    )


def _blocked_items_have_reasons(control_report: Mapping[str, Any]) -> bool:
    return all(
        bool(_as_mapping(item).get("reason"))
        for item in _as_list(control_report.get("blocked_items"))
    )


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value.get(key) is not None:
                return True
        return any(_contains_non_null_key(item, *keys) for item in value.values())

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_null_key(item, *keys) for item in value)

    return False


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    normalized = Path(path)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    return normalized


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

