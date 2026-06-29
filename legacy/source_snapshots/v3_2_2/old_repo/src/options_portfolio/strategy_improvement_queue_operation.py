from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.strategy_improvement_queue import (
    EXPLICIT_EXCLUSIONS,
    build_options_strategy_improvement_queue,
)


OPERATION_SCHEMA_VERSION = "options_strategy_improvement_queue_operation.v1"
EVENT_SCHEMA_VERSION = "options_strategy_improvement_queue_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_strategy_improvement_queue_audit.v1"
HEALTH_SCHEMA_VERSION = "options_strategy_improvement_queue_health.v1"

OPERATION_TYPE = "options_strategy_improvement_queue_operation"
VALID_QUEUE_STATUSES = {"ready", "needs_review", "blocked"}
VALID_TASK_PRIORITIES = {"high", "normal"}
VALID_EDGE_CLASSIFICATIONS = {
    "needs_more_data",
    "underperforming",
    "blocked",
}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_strategy_improvement_queue_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run options strategy improvement queue as an auditable operation.

    This operation creates manual research/improvement tasks only. It never calls
    broker APIs, routes orders, submits orders, models fills, performs live
    execution, models slippage, creates automatic close/roll/defense orders, or
    changes strategy logic/parameters automatically.
    """

    improvement_queue = build_options_strategy_improvement_queue(source or {})
    audit_report = build_options_strategy_improvement_queue_audit_report(improvement_queue)
    health_report = build_options_strategy_improvement_queue_health_report(improvement_queue)
    operation_status = _classify_operation_status(
        queue_status=str(improvement_queue.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            improvement_queue=improvement_queue,
            event_type="options_strategy_improvement_queue_operation_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            improvement_queue=improvement_queue,
            event_type="options_strategy_improvement_queue_operation_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        improvement_queue=improvement_queue,
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
        "options_strategy_improvement_queue": improvement_queue,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(improvement_queue.get("explicit_exclusions", [])),
    }


def build_options_strategy_improvement_queue_audit_report(
    improvement_queue: Mapping[str, Any]
) -> dict[str, Any]:
    checks = [
        _check(
            name="improvement_queue_artifact_type_valid",
            passed=improvement_queue.get("artifact_type") == "options_strategy_improvement_queue",
            severity="blocker",
            message="options strategy improvement queue artifact type is valid",
            failure_message="options strategy improvement queue artifact type is invalid",
        ),
        _check(
            name="improvement_queue_status_valid",
            passed=improvement_queue.get("status") in VALID_QUEUE_STATUSES,
            severity="blocker",
            message="options strategy improvement queue status is valid",
            failure_message="options strategy improvement queue status is invalid",
        ),
        _check(
            name="task_summary_present",
            passed=isinstance(improvement_queue.get("task_summary"), Mapping),
            severity="blocker",
            message="options strategy improvement queue task summary is present",
            failure_message="options strategy improvement queue task summary is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(improvement_queue),
            severity="blocker",
            message="options strategy improvement queue exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(improvement_queue, "order_intent"),
            severity="blocker",
            message="options strategy improvement queue did not create order intents",
            failure_message="options strategy improvement queue created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(improvement_queue, "broker_order_id"),
            severity="blocker",
            message="options strategy improvement queue did not create broker order ids",
            failure_message="options strategy improvement queue created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                improvement_queue,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options strategy improvement queue did not create automatic actions",
            failure_message="options strategy improvement queue created one or more automatic actions",
        ),
        _check(
            name="no_automatic_strategy_or_parameter_changes_created",
            passed=not _contains_non_null_key(
                improvement_queue,
                "automatic_strategy_change",
                "automatic_parameter_change",
                "strategy_change",
                "parameter_change",
            ),
            severity="blocker",
            message="options strategy improvement queue did not create automatic strategy or parameter changes",
            failure_message="options strategy improvement queue created automatic strategy or parameter changes",
        ),
        _check(
            name="improvement_tasks_have_valid_priorities",
            passed=_improvement_tasks_have_valid_priorities(improvement_queue),
            severity="warning",
            message="options strategy improvement tasks have valid priorities",
            failure_message="one or more options strategy improvement tasks have invalid priorities",
        ),
        _check(
            name="improvement_tasks_have_valid_edge_classifications",
            passed=_improvement_tasks_have_valid_edge_classifications(improvement_queue),
            severity="warning",
            message="options strategy improvement tasks have valid edge classifications",
            failure_message="one or more options strategy improvement tasks have invalid edge classifications",
        ),
        _check(
            name="improvement_tasks_require_manual_approval",
            passed=_improvement_tasks_require_manual_approval(improvement_queue),
            severity="warning",
            message="options strategy improvement tasks require manual approval",
            failure_message="one or more options strategy improvement tasks do not require manual approval",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(improvement_queue),
            severity="warning",
            message="blocked options strategy improvement items include reasons",
            failure_message="one or more blocked options strategy improvement items are missing reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            queue_status=str(improvement_queue.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(improvement_queue.get("explicit_exclusions", [])),
    }


def build_options_strategy_improvement_queue_health_report(
    improvement_queue: Mapping[str, Any]
) -> dict[str, Any]:
    queue_status = str(improvement_queue.get("status", "needs_review"))
    task_summary = _as_mapping(improvement_queue.get("task_summary"))
    improvement_tasks = _as_list(improvement_queue.get("improvement_tasks"))
    blocked_items = _as_list(improvement_queue.get("blocked_items"))

    indicators = {
        "queue_status": queue_status,
        "queue_date": _string_or_none(improvement_queue.get("queue_date")),
        "source_review_count": _safe_int(improvement_queue.get("source_review_count")),
        "total_task_count": _safe_int(task_summary.get("total_task_count")),
        "high_priority_task_count": _safe_int(task_summary.get("high_priority_task_count")),
        "normal_priority_task_count": _safe_int(task_summary.get("normal_priority_task_count")),
        "needs_more_data_task_count": _safe_int(task_summary.get("needs_more_data_task_count")),
        "underperforming_task_count": _safe_int(task_summary.get("underperforming_task_count")),
        "blocked_task_count": _safe_int(task_summary.get("blocked_task_count")),
        "overall_task_count": _safe_int(task_summary.get("overall_task_count")),
        "strategy_task_count": _safe_int(task_summary.get("strategy_task_count")),
        "symbol_task_count": _safe_int(task_summary.get("symbol_task_count")),
        "setup_family_task_count": _safe_int(task_summary.get("setup_family_task_count")),
        "blocked_item_count": len(blocked_items),
        "improvement_task_count": len(improvement_tasks),
        "has_high_priority_tasks": any(
            _as_mapping(task).get("priority") == "high" for task in improvement_tasks
        ),
        "has_underperforming_tasks": any(
            _as_mapping(task).get("edge_classification") == "underperforming"
            for task in improvement_tasks
        ),
        "has_needs_more_data_tasks": any(
            _as_mapping(task).get("edge_classification") == "needs_more_data"
            for task in improvement_tasks
        ),
        "has_blocked_tasks": any(
            _as_mapping(task).get("edge_classification") == "blocked"
            for task in improvement_tasks
        ),
        "has_blocked_items": bool(blocked_items),
        "has_order_intent": _contains_non_null_key(improvement_queue, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(improvement_queue, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(improvement_queue, "automatic_action"),
        "has_automatic_strategy_change": _contains_non_null_key(
            improvement_queue,
            "automatic_strategy_change",
            "automatic_parameter_change",
            "strategy_change",
            "parameter_change",
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            queue_status=queue_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(improvement_queue.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    improvement_queue: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    task_summary = _as_mapping(improvement_queue.get("task_summary"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "queue_date": _string_or_none(improvement_queue.get("queue_date")),
        "source_review_count": _safe_int(improvement_queue.get("source_review_count")),
        "operation_summary": {
            "total_task_count": _safe_int(task_summary.get("total_task_count")),
            "high_priority_task_count": _safe_int(task_summary.get("high_priority_task_count")),
            "normal_priority_task_count": _safe_int(task_summary.get("normal_priority_task_count")),
            "needs_more_data_task_count": _safe_int(task_summary.get("needs_more_data_task_count")),
            "underperforming_task_count": _safe_int(task_summary.get("underperforming_task_count")),
            "blocked_task_count": _safe_int(task_summary.get("blocked_task_count")),
            "overall_task_count": _safe_int(task_summary.get("overall_task_count")),
            "strategy_task_count": _safe_int(task_summary.get("strategy_task_count")),
            "symbol_task_count": _safe_int(task_summary.get("symbol_task_count")),
            "setup_family_task_count": _safe_int(task_summary.get("setup_family_task_count")),
            "blocked_item_count": _safe_int(task_summary.get("blocked_item_count")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(improvement_queue.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    improvement_queue: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    task_summary = _as_mapping(improvement_queue.get("task_summary"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "queue_date": _string_or_none(improvement_queue.get("queue_date")),
        "source_review_count": _safe_int(improvement_queue.get("source_review_count")),
        "total_task_count": _safe_int(task_summary.get("total_task_count")),
        "high_priority_task_count": _safe_int(task_summary.get("high_priority_task_count")),
        "blocked_item_count": _safe_int(task_summary.get("blocked_item_count")),
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
    queue_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {queue_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {queue_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(*, queue_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if queue_status == "blocked":
        return "blocked"
    if queue_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, queue_status: str, indicators: Mapping[str, Any]) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
        or indicators.get("has_automatic_strategy_change")
    ):
        return "blocked"
    if queue_status == "blocked" or indicators.get("has_blocked_items"):
        return "blocked"
    if (
        queue_status == "needs_review"
        or indicators.get("has_high_priority_tasks")
        or indicators.get("has_underperforming_tasks")
        or indicators.get("has_needs_more_data_tasks")
    ):
        return "needs_review"
    return "ready"


def _has_required_exclusions(improvement_queue: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(improvement_queue.get("explicit_exclusions")))
    return all(item in exclusions for item in REQUIRED_EXCLUSIONS)


def _improvement_tasks_have_valid_priorities(improvement_queue: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("priority") in VALID_TASK_PRIORITIES
        for item in _as_list(improvement_queue.get("improvement_tasks"))
    )


def _improvement_tasks_have_valid_edge_classifications(improvement_queue: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("edge_classification") in VALID_EDGE_CLASSIFICATIONS
        for item in _as_list(improvement_queue.get("improvement_tasks"))
    )


def _improvement_tasks_require_manual_approval(improvement_queue: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("requires_manual_approval") is True
        for item in _as_list(improvement_queue.get("improvement_tasks"))
    )


def _blocked_items_have_reasons(improvement_queue: Mapping[str, Any]) -> bool:
    return all(
        bool(_as_mapping(item).get("reason"))
        for item in _as_list(improvement_queue.get("blocked_items"))
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

