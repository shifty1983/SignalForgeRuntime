from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.options_portfolio.action_execution_record import (
    EXPLICIT_EXCLUSIONS,
    build_options_manual_execution_record,
)


OPERATION_SCHEMA_VERSION = "options_manual_execution_record_operation.v1"
EVENT_SCHEMA_VERSION = "options_manual_execution_record_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_manual_execution_record_audit.v1"
HEALTH_SCHEMA_VERSION = "options_manual_execution_record_health.v1"

OPERATION_TYPE = "options_manual_execution_record_operation"
VALID_EXECUTION_STATUSES = {"ready", "needs_review", "blocked"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_manual_execution_record_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run the manual options execution record as an auditable operation.

    This operation records what was handled manually after approved actions. It
    never calls broker APIs, routes orders, submits orders, models fills,
    performs live execution, models slippage, or creates automatic close/roll/
    defense orders.
    """

    execution_record = build_options_manual_execution_record(source)
    audit_report = build_options_manual_execution_record_audit_report(execution_record)
    health_report = build_options_manual_execution_record_health_report(execution_record)

    events = [
        _build_event(
            execution_record=execution_record,
            event_type="options_manual_execution_record_operation_started",
            sequence=1,
        ),
        _build_event(
            execution_record=execution_record,
            event_type="options_manual_execution_record_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        execution_record=execution_record,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": execution_record["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_manual_execution_record": execution_record,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(execution_record.get("explicit_exclusions", [])),
    }


def build_options_manual_execution_record_audit_report(
    execution_record: Mapping[str, Any]
) -> dict[str, Any]:
    checks = [
        _check(
            name="execution_artifact_type_valid",
            passed=execution_record.get("artifact_type") == "options_manual_execution_record",
            severity="blocker",
            message="options manual execution record artifact type is valid",
            failure_message="options manual execution record artifact type is invalid",
        ),
        _check(
            name="execution_status_valid",
            passed=execution_record.get("status") in VALID_EXECUTION_STATUSES,
            severity="blocker",
            message="options manual execution record status is valid",
            failure_message="options manual execution record status is invalid",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(execution_record),
            severity="blocker",
            message="options manual execution record exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="manual_approval_required",
            passed=execution_record.get("requires_manual_approval") is True,
            severity="blocker",
            message="options manual execution record preserves manual approval requirement",
            failure_message="options manual execution record does not preserve manual approval requirement",
        ),
        _check(
            name="completed_actions_preserve_manual_safeguards",
            passed=_completed_actions_preserve_manual_safeguards(
                execution_record.get("completed_manual_actions")
            ),
            severity="blocker",
            message="completed manual actions preserve manual execution safeguards",
            failure_message="one or more completed manual actions bypass safety safeguards",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(execution_record, "order_intent"),
            severity="blocker",
            message="options manual execution record did not create order intents",
            failure_message="options manual execution record created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(execution_record, "broker_order_id"),
            severity="blocker",
            message="options manual execution record did not create broker order ids",
            failure_message="options manual execution record created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                execution_record,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options manual execution record did not create automatic actions",
            failure_message="options manual execution record created one or more automatic actions",
        ),
        _check(
            name="count_fields_match_execution_lists",
            passed=_count_fields_match_execution_lists(execution_record),
            severity="blocker",
            message="options manual execution record counts match execution lists",
            failure_message="options manual execution record counts do not match execution lists",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(execution_record),
            severity="warning",
            message="blocked manual execution items include reasons",
            failure_message="one or more blocked manual execution items are missing reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            execution_status=str(execution_record.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(execution_record.get("explicit_exclusions", [])),
    }


def build_options_manual_execution_record_health_report(
    execution_record: Mapping[str, Any]
) -> dict[str, Any]:
    execution_status = str(execution_record.get("status", "needs_review"))
    completed_manual_actions = _as_list(execution_record.get("completed_manual_actions"))
    skipped_manual_actions = _as_list(execution_record.get("skipped_manual_actions"))
    deferred_manual_actions = _as_list(execution_record.get("deferred_manual_actions"))
    pending_manual_actions = _as_list(execution_record.get("pending_manual_actions"))
    needs_review_actions = _as_list(execution_record.get("needs_review_actions"))
    blocked_items = _as_list(execution_record.get("blocked_items"))
    execution_summary = _as_mapping(execution_record.get("execution_summary"))

    indicators = {
        "execution_status": execution_status,
        "queue_date": _string_or_none(execution_record.get("queue_date")),
        "reviewed_at": _string_or_none(execution_record.get("reviewed_at")),
        "execution_recorded_at": _string_or_none(execution_record.get("execution_recorded_at")),
        "recorder": _string_or_none(execution_record.get("recorder")),
        "source_approved_action_count": _safe_int(
            execution_summary.get("source_approved_action_count")
        ),
        "manual_execution_record_count": _safe_int(
            execution_summary.get("manual_execution_record_count")
        ),
        "completed_manual_action_count": _safe_int(
            execution_summary.get("completed_manual_action_count")
        ),
        "skipped_manual_action_count": _safe_int(
            execution_summary.get("skipped_manual_action_count")
        ),
        "deferred_manual_action_count": _safe_int(
            execution_summary.get("deferred_manual_action_count")
        ),
        "pending_manual_action_count": _safe_int(
            execution_summary.get("pending_manual_action_count")
        ),
        "needs_review_action_count": _safe_int(
            execution_summary.get("needs_review_action_count")
        ),
        "blocked_item_count": _safe_int(execution_summary.get("blocked_item_count")),
        "has_completed_manual_actions": bool(completed_manual_actions),
        "has_skipped_manual_actions": bool(skipped_manual_actions),
        "has_deferred_manual_actions": bool(deferred_manual_actions),
        "has_pending_manual_actions": bool(pending_manual_actions),
        "has_needs_review_actions": bool(needs_review_actions),
        "has_blocked_items": bool(blocked_items),
        "requires_manual_approval": execution_record.get("requires_manual_approval") is True,
        "has_order_intent": _contains_non_null_key(execution_record, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(execution_record, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(execution_record, "automatic_action"),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            execution_status=execution_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(execution_record.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    execution_record: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    execution_summary = _as_mapping(execution_record.get("execution_summary"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": execution_record.get("status"),
        "queue_date": _string_or_none(execution_record.get("queue_date")),
        "reviewed_at": _string_or_none(execution_record.get("reviewed_at")),
        "execution_recorded_at": _string_or_none(execution_record.get("execution_recorded_at")),
        "recorder": _string_or_none(execution_record.get("recorder")),
        "summary": {
            "source_approved_action_count": _safe_int(
                execution_summary.get("source_approved_action_count")
            ),
            "manual_execution_record_count": _safe_int(
                execution_summary.get("manual_execution_record_count")
            ),
            "completed_manual_action_count": _safe_int(
                execution_summary.get("completed_manual_action_count")
            ),
            "skipped_manual_action_count": _safe_int(
                execution_summary.get("skipped_manual_action_count")
            ),
            "deferred_manual_action_count": _safe_int(
                execution_summary.get("deferred_manual_action_count")
            ),
            "pending_manual_action_count": _safe_int(
                execution_summary.get("pending_manual_action_count")
            ),
            "needs_review_action_count": _safe_int(
                execution_summary.get("needs_review_action_count")
            ),
            "blocked_item_count": _safe_int(execution_summary.get("blocked_item_count")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "requires_manual_approval": True,
        "explicit_exclusions": list(execution_record.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    execution_record: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    execution_summary = _as_mapping(execution_record.get("execution_summary"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": execution_record.get("status"),
        "queue_date": _string_or_none(execution_record.get("queue_date")),
        "execution_recorded_at": _string_or_none(execution_record.get("execution_recorded_at")),
        "completed_manual_action_count": _safe_int(
            execution_summary.get("completed_manual_action_count")
        ),
        "pending_manual_action_count": _safe_int(
            execution_summary.get("pending_manual_action_count")
        ),
        "blocked_item_count": _safe_int(execution_summary.get("blocked_item_count")),
        "requires_manual_approval": True,
        "explicit_exclusions": list(execution_record.get("explicit_exclusions", [])),
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


def _classify_audit_status(*, execution_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if execution_status == "blocked":
        return "blocked"
    if execution_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, execution_status: str, indicators: Mapping[str, Any]) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
    ):
        return "blocked"
    if not indicators.get("requires_manual_approval"):
        return "blocked"
    if execution_status == "blocked":
        return "blocked"
    if (
        execution_status == "needs_review"
        or indicators.get("has_pending_manual_actions")
        or indicators.get("has_needs_review_actions")
    ):
        return "needs_review"
    return "ready"


def _has_required_exclusions(execution_record: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(execution_record.get("explicit_exclusions")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _completed_actions_preserve_manual_safeguards(items: Any) -> bool:
    for item in _as_list(items):
        if not isinstance(item, Mapping):
            return False
        if item.get("requires_manual_approval") is not True:
            return False
        if item.get("order_intent") is not None:
            return False
        if item.get("broker_order_id") is not None:
            return False
        if item.get("automatic_action") is not None:
            return False
        if item.get("executed_outside_system") is not True:
            return False
    return True


def _count_fields_match_execution_lists(execution_record: Mapping[str, Any]) -> bool:
    summary = _as_mapping(execution_record.get("execution_summary"))
    return all(
        [
            _safe_int(summary.get("completed_manual_action_count"))
            == len(_as_list(execution_record.get("completed_manual_actions"))),
            _safe_int(summary.get("skipped_manual_action_count"))
            == len(_as_list(execution_record.get("skipped_manual_actions"))),
            _safe_int(summary.get("deferred_manual_action_count"))
            == len(_as_list(execution_record.get("deferred_manual_actions"))),
            _safe_int(summary.get("pending_manual_action_count"))
            == len(_as_list(execution_record.get("pending_manual_actions"))),
            _safe_int(summary.get("needs_review_action_count"))
            == len(_as_list(execution_record.get("needs_review_actions"))),
            _safe_int(summary.get("blocked_item_count"))
            == len(_as_list(execution_record.get("blocked_items"))),
        ]
    )


def _blocked_items_have_reasons(execution_record: Mapping[str, Any]) -> bool:
    for item in _as_list(execution_record.get("blocked_items")):
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

