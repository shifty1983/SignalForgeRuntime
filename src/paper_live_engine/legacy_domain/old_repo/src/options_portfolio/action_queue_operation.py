from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.options_portfolio.action_queue import (
    EXPLICIT_EXCLUSIONS,
    build_options_manual_action_queue,
)


OPERATION_SCHEMA_VERSION = "options_manual_action_queue_operation.v1"
EVENT_SCHEMA_VERSION = "options_manual_action_queue_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_manual_action_queue_audit.v1"
HEALTH_SCHEMA_VERSION = "options_manual_action_queue_health.v1"

OPERATION_TYPE = "options_manual_action_queue_operation"
VALID_QUEUE_STATUSES = {"ready", "needs_review", "blocked"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_manual_action_queue_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run the manual options action queue as an auditable operation.

    This operation merges safe review artifacts from weekly planning,
    strategy-defense review, and scheduled position-risk monitoring into one
    manual action queue. It does not call broker APIs, route orders, submit
    orders, model fills, perform live execution, model slippage, or create
    automatic close/roll/defense orders.
    """

    queue = build_options_manual_action_queue(source)
    audit_report = build_options_manual_action_queue_audit_report(queue)
    health_report = build_options_manual_action_queue_health_report(queue)

    events = [
        _build_event(
            queue=queue,
            event_type="options_manual_action_queue_operation_started",
            sequence=1,
        ),
        _build_event(
            queue=queue,
            event_type="options_manual_action_queue_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        queue=queue,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": queue["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_manual_action_queue": queue,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(queue.get("explicit_exclusions", [])),
    }


def build_options_manual_action_queue_audit_report(queue: Mapping[str, Any]) -> dict[str, Any]:
    checks = [
        _check(
            name="queue_artifact_type_valid",
            passed=queue.get("artifact_type") == "options_manual_action_queue",
            severity="blocker",
            message="options manual action queue artifact type is valid",
            failure_message="options manual action queue artifact type is invalid",
        ),
        _check(
            name="queue_status_valid",
            passed=queue.get("status") in VALID_QUEUE_STATUSES,
            severity="blocker",
            message="options manual action queue status is valid",
            failure_message="options manual action queue status is invalid",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(queue),
            severity="blocker",
            message="options manual action queue exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="manual_approval_required",
            passed=queue.get("requires_manual_approval") is True,
            severity="blocker",
            message="options manual action queue requires manual approval",
            failure_message="options manual action queue does not require manual approval",
        ),
        _check(
            name="priority_actions_require_manual_approval",
            passed=_items_require_manual_approval(queue.get("priority_actions")),
            severity="blocker",
            message="all priority actions require manual approval",
            failure_message="one or more priority actions bypass manual approval",
        ),
        _check(
            name="deferred_actions_require_manual_approval",
            passed=_items_require_manual_approval(queue.get("deferred_actions")),
            severity="blocker",
            message="all deferred actions require manual approval",
            failure_message="one or more deferred actions bypass manual approval",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(queue, "order_intent"),
            severity="blocker",
            message="options manual action queue did not create order intents",
            failure_message="options manual action queue created one or more order intents",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                queue,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options manual action queue did not create automatic actions",
            failure_message="options manual action queue created one or more automatic actions",
        ),
        _check(
            name="count_fields_match_action_lists",
            passed=_count_fields_match_action_lists(queue),
            severity="blocker",
            message="options manual action queue counts match action lists",
            failure_message="options manual action queue counts do not match action lists",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(queue),
            severity="warning",
            message="blocked action queue items include reasons",
            failure_message="one or more blocked action queue items are missing reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            queue_status=str(queue.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(queue.get("explicit_exclusions", [])),
    }


def build_options_manual_action_queue_health_report(queue: Mapping[str, Any]) -> dict[str, Any]:
    queue_status = str(queue.get("status", "needs_review"))
    priority_actions = _as_list(queue.get("priority_actions"))
    monitor_items = _as_list(queue.get("monitor_items"))
    deferred_actions = _as_list(queue.get("deferred_actions"))
    blocked_items = _as_list(queue.get("blocked_items"))
    action_summary = _as_mapping(queue.get("action_summary"))

    indicators = {
        "queue_status": queue_status,
        "queue_date": _string_or_none(queue.get("queue_date")),
        "evaluation_timestamp": _string_or_none(queue.get("evaluation_timestamp")),
        "priority_action_count": _safe_int(action_summary.get("priority_action_count")),
        "risk_monitor_action_count": _safe_int(action_summary.get("risk_monitor_action_count")),
        "defense_review_action_count": _safe_int(action_summary.get("defense_review_action_count")),
        "new_trade_action_count": _safe_int(action_summary.get("new_trade_action_count")),
        "monitor_item_count": _safe_int(action_summary.get("monitor_item_count")),
        "deferred_action_count": _safe_int(action_summary.get("deferred_action_count")),
        "blocked_item_count": _safe_int(action_summary.get("blocked_item_count")),
        "has_priority_actions": bool(priority_actions),
        "has_monitor_items": bool(monitor_items),
        "has_deferred_actions": bool(deferred_actions),
        "has_blocked_items": bool(blocked_items),
        "requires_manual_approval": queue.get("requires_manual_approval") is True,
        "has_order_intent": _contains_non_null_key(queue, "order_intent"),
        "has_automatic_action": _contains_non_null_key(queue, "automatic_action"),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(queue_status=queue_status, indicators=indicators),
        "indicators": indicators,
        "explicit_exclusions": list(queue.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    queue: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    action_summary = _as_mapping(queue.get("action_summary"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": queue.get("status"),
        "queue_date": _string_or_none(queue.get("queue_date")),
        "evaluation_timestamp": _string_or_none(queue.get("evaluation_timestamp")),
        "summary": {
            "priority_action_count": _safe_int(action_summary.get("priority_action_count")),
            "risk_monitor_action_count": _safe_int(action_summary.get("risk_monitor_action_count")),
            "defense_review_action_count": _safe_int(action_summary.get("defense_review_action_count")),
            "new_trade_action_count": _safe_int(action_summary.get("new_trade_action_count")),
            "monitor_item_count": _safe_int(action_summary.get("monitor_item_count")),
            "deferred_action_count": _safe_int(action_summary.get("deferred_action_count")),
            "blocked_item_count": _safe_int(action_summary.get("blocked_item_count")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "requires_manual_approval": True,
        "explicit_exclusions": list(queue.get("explicit_exclusions", [])),
    }


def _build_event(*, queue: Mapping[str, Any], event_type: str, sequence: int) -> dict[str, Any]:
    action_summary = _as_mapping(queue.get("action_summary"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": queue.get("status"),
        "queue_date": _string_or_none(queue.get("queue_date")),
        "evaluation_timestamp": _string_or_none(queue.get("evaluation_timestamp")),
        "priority_action_count": _safe_int(action_summary.get("priority_action_count")),
        "blocked_item_count": _safe_int(action_summary.get("blocked_item_count")),
        "requires_manual_approval": True,
        "explicit_exclusions": list(queue.get("explicit_exclusions", [])),
    }


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


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
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "message": message if passed else failure_message,
    }


def _summarize_checks(checks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    passed_count = sum(1 for check in checks if check.get("passed") is True)
    failed_count = len(checks) - passed_count
    blocker_failed_count = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") == "blocker"
    )
    warning_failed_count = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") == "warning"
    )
    return {
        "check_count": len(checks),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "blocker_failed_count": blocker_failed_count,
        "warning_failed_count": warning_failed_count,
    }


def _classify_audit_status(*, queue_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if queue_status == "blocked":
        return "blocked"
    if queue_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, queue_status: str, indicators: Mapping[str, Any]) -> str:
    if indicators.get("has_order_intent") or indicators.get("has_automatic_action"):
        return "blocked"
    if not indicators.get("requires_manual_approval"):
        return "blocked"
    if queue_status == "blocked":
        return "blocked"
    if queue_status == "needs_review" or indicators.get("has_priority_actions"):
        return "needs_review"
    return "ready"


def _has_required_exclusions(queue: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(queue.get("explicit_exclusions")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _items_require_manual_approval(items: Any) -> bool:
    for item in _as_list(items):
        if not isinstance(item, Mapping):
            return False
        if item.get("requires_manual_approval") is not True:
            return False
    return True


def _count_fields_match_action_lists(queue: Mapping[str, Any]) -> bool:
    summary = _as_mapping(queue.get("action_summary"))
    return all(
        [
            _safe_int(summary.get("priority_action_count")) == len(_as_list(queue.get("priority_actions"))),
            _safe_int(summary.get("monitor_item_count")) == len(_as_list(queue.get("monitor_items"))),
            _safe_int(summary.get("deferred_action_count")) == len(_as_list(queue.get("deferred_actions"))),
            _safe_int(summary.get("blocked_item_count")) == len(_as_list(queue.get("blocked_items"))),
        ]
    )


def _blocked_items_have_reasons(queue: Mapping[str, Any]) -> bool:
    for item in _as_list(queue.get("blocked_items")):
        if not isinstance(item, Mapping):
            return False
        if not _string_or_none(item.get("reason")):
            return False
    return True


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in keys and item is not None:
                return True
            if _contains_non_null_key(item, *keys):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_null_key(item, *keys) for item in value)
    return False


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [str(item) for item in value if item is not None]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

