from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.options_portfolio.action_outcome_record import (
    EXPLICIT_EXCLUSIONS,
    build_options_manual_action_outcome_record,
)


OPERATION_SCHEMA_VERSION = "options_manual_action_outcome_record_operation.v1"
EVENT_SCHEMA_VERSION = "options_manual_action_outcome_record_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_manual_action_outcome_record_audit.v1"
HEALTH_SCHEMA_VERSION = "options_manual_action_outcome_record_health.v1"

OPERATION_TYPE = "options_manual_action_outcome_record_operation"
VALID_OUTCOME_STATUSES = {"ready", "needs_review", "blocked"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_manual_action_outcome_record_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run manual options action outcome recording as an auditable operation.

    This operation records what happened after manual action handling. It never
    calls broker APIs, routes orders, submits orders, models fills, performs
    live execution, models slippage, or creates automatic close/roll/defense
    orders.
    """

    outcome_record = build_options_manual_action_outcome_record(source)
    audit_report = build_options_manual_action_outcome_record_audit_report(outcome_record)
    health_report = build_options_manual_action_outcome_record_health_report(outcome_record)

    events = [
        _build_event(
            outcome_record=outcome_record,
            event_type="options_manual_action_outcome_record_operation_started",
            sequence=1,
        ),
        _build_event(
            outcome_record=outcome_record,
            event_type="options_manual_action_outcome_record_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        outcome_record=outcome_record,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )
    
    operation_status = _classify_operation_status(
        outcome_status=str(outcome_record.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_status,
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_manual_action_outcome_record": outcome_record,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(outcome_record.get("explicit_exclusions", [])),
    }


def build_options_manual_action_outcome_record_audit_report(
    outcome_record: Mapping[str, Any]
) -> dict[str, Any]:
    checks = [
        _check(
            name="outcome_artifact_type_valid",
            passed=outcome_record.get("artifact_type") == "options_manual_action_outcome_record",
            severity="blocker",
            message="options manual action outcome record artifact type is valid",
            failure_message="options manual action outcome record artifact type is invalid",
        ),
        _check(
            name="outcome_status_valid",
            passed=outcome_record.get("status") in VALID_OUTCOME_STATUSES,
            severity="blocker",
            message="options manual action outcome record status is valid",
            failure_message="options manual action outcome record status is invalid",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(outcome_record),
            severity="blocker",
            message="options manual action outcome record exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="closed_outcomes_preserve_manual_safeguards",
            passed=_outcomes_preserve_manual_safeguards(outcome_record.get("closed_outcomes")),
            severity="blocker",
            message="closed outcomes preserve manual-only safeguards",
            failure_message="one or more closed outcomes bypass safety safeguards",
        ),
        _check(
            name="open_outcomes_preserve_manual_safeguards",
            passed=_outcomes_preserve_manual_safeguards(outcome_record.get("open_outcomes")),
            severity="blocker",
            message="open outcomes preserve manual-only safeguards",
            failure_message="one or more open outcomes bypass safety safeguards",
        ),
        _check(
            name="pending_outcomes_preserve_manual_safeguards",
            passed=_outcomes_preserve_manual_safeguards(outcome_record.get("pending_outcomes")),
            severity="blocker",
            message="pending outcomes preserve manual-only safeguards",
            failure_message="one or more pending outcomes bypass safety safeguards",
        ),
        _check(
            name="needs_review_outcomes_preserve_manual_safeguards",
            passed=_outcomes_preserve_manual_safeguards(outcome_record.get("needs_review_outcomes")),
            severity="blocker",
            message="needs-review outcomes preserve manual-only safeguards",
            failure_message="one or more needs-review outcomes bypass safety safeguards",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(outcome_record, "order_intent"),
            severity="blocker",
            message="options manual action outcome record did not create order intents",
            failure_message="options manual action outcome record created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(outcome_record, "broker_order_id"),
            severity="blocker",
            message="options manual action outcome record did not create broker order ids",
            failure_message="options manual action outcome record created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                outcome_record,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options manual action outcome record did not create automatic actions",
            failure_message="options manual action outcome record created one or more automatic actions",
        ),
        _check(
            name="count_fields_match_outcome_lists",
            passed=_count_fields_match_outcome_lists(outcome_record),
            severity="blocker",
            message="options manual action outcome record counts match outcome lists",
            failure_message="options manual action outcome record counts do not match outcome lists",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(outcome_record),
            severity="warning",
            message="blocked manual outcome items include reasons",
            failure_message="one or more blocked manual outcome items are missing reasons",
        ),
        _check(
            name="no_pending_outcomes",
            passed=len(_as_list(outcome_record.get("pending_outcomes"))) == 0,
            severity="warning",
            message="options manual action outcome record has no pending outcomes",
            failure_message="options manual action outcome record has pending outcomes requiring review",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            outcome_status=str(outcome_record.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(outcome_record.get("explicit_exclusions", [])),
    }


def build_options_manual_action_outcome_record_health_report(
    outcome_record: Mapping[str, Any]
) -> dict[str, Any]:
    outcome_status = str(outcome_record.get("status", "needs_review"))
    closed_outcomes = _as_list(outcome_record.get("closed_outcomes"))
    open_outcomes = _as_list(outcome_record.get("open_outcomes"))
    pending_outcomes = _as_list(outcome_record.get("pending_outcomes"))
    needs_review_outcomes = _as_list(outcome_record.get("needs_review_outcomes"))
    blocked_items = _as_list(outcome_record.get("blocked_items"))
    outcome_summary = _as_mapping(outcome_record.get("outcome_summary"))
    edge_validation_inputs = _as_mapping(outcome_record.get("edge_validation_inputs"))

    indicators = {
        "outcome_status": outcome_status,
        "queue_date": _string_or_none(outcome_record.get("queue_date")),
        "reviewed_at": _string_or_none(outcome_record.get("reviewed_at")),
        "execution_recorded_at": _string_or_none(outcome_record.get("execution_recorded_at")),
        "outcome_recorded_at": _string_or_none(outcome_record.get("outcome_recorded_at")),
        "recorder": _string_or_none(outcome_record.get("recorder")),
        "source_completed_action_count": _safe_int(
            outcome_summary.get("source_completed_action_count")
        ),
        "manual_outcome_record_count": _safe_int(
            outcome_summary.get("manual_outcome_record_count")
        ),
        "closed_outcome_count": _safe_int(outcome_summary.get("closed_outcome_count")),
        "open_outcome_count": _safe_int(outcome_summary.get("open_outcome_count")),
        "pending_outcome_count": _safe_int(outcome_summary.get("pending_outcome_count")),
        "needs_review_outcome_count": _safe_int(
            outcome_summary.get("needs_review_outcome_count")
        ),
        "blocked_item_count": _safe_int(outcome_summary.get("blocked_item_count")),
        "win_count": _safe_int(outcome_summary.get("win_count")),
        "loss_count": _safe_int(outcome_summary.get("loss_count")),
        "flat_count": _safe_int(outcome_summary.get("flat_count")),
        "total_realized_pnl": _safe_float(outcome_summary.get("total_realized_pnl")),
        "average_return_pct": _safe_float_or_none(outcome_summary.get("average_return_pct")),
        "average_days_held": _safe_float_or_none(
            edge_validation_inputs.get("average_days_held")
        ),
        "edge_closed_action_count": _safe_int(edge_validation_inputs.get("closed_action_count")),
        "has_closed_outcomes": bool(closed_outcomes),
        "has_open_outcomes": bool(open_outcomes),
        "has_pending_outcomes": bool(pending_outcomes),
        "has_needs_review_outcomes": bool(needs_review_outcomes),
        "has_blocked_items": bool(blocked_items),
        "has_order_intent": _contains_non_null_key(outcome_record, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(outcome_record, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(outcome_record, "automatic_action"),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            outcome_status=outcome_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(outcome_record.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    outcome_record: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    outcome_summary = _as_mapping(outcome_record.get("outcome_summary"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": outcome_record.get("status"),
        "queue_date": _string_or_none(outcome_record.get("queue_date")),
        "reviewed_at": _string_or_none(outcome_record.get("reviewed_at")),
        "execution_recorded_at": _string_or_none(outcome_record.get("execution_recorded_at")),
        "outcome_recorded_at": _string_or_none(outcome_record.get("outcome_recorded_at")),
        "recorder": _string_or_none(outcome_record.get("recorder")),
        "summary": {
            "source_completed_action_count": _safe_int(
                outcome_summary.get("source_completed_action_count")
            ),
            "manual_outcome_record_count": _safe_int(
                outcome_summary.get("manual_outcome_record_count")
            ),
            "closed_outcome_count": _safe_int(outcome_summary.get("closed_outcome_count")),
            "open_outcome_count": _safe_int(outcome_summary.get("open_outcome_count")),
            "pending_outcome_count": _safe_int(outcome_summary.get("pending_outcome_count")),
            "needs_review_outcome_count": _safe_int(
                outcome_summary.get("needs_review_outcome_count")
            ),
            "blocked_item_count": _safe_int(outcome_summary.get("blocked_item_count")),
            "win_count": _safe_int(outcome_summary.get("win_count")),
            "loss_count": _safe_int(outcome_summary.get("loss_count")),
            "flat_count": _safe_int(outcome_summary.get("flat_count")),
            "total_realized_pnl": _safe_float(outcome_summary.get("total_realized_pnl")),
            "average_return_pct": _safe_float_or_none(outcome_summary.get("average_return_pct")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "manual_only": True,
        "explicit_exclusions": list(outcome_record.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    outcome_record: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    outcome_summary = _as_mapping(outcome_record.get("outcome_summary"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": outcome_record.get("status"),
        "queue_date": _string_or_none(outcome_record.get("queue_date")),
        "outcome_recorded_at": _string_or_none(outcome_record.get("outcome_recorded_at")),
        "closed_outcome_count": _safe_int(outcome_summary.get("closed_outcome_count")),
        "pending_outcome_count": _safe_int(outcome_summary.get("pending_outcome_count")),
        "blocked_item_count": _safe_int(outcome_summary.get("blocked_item_count")),
        "manual_only": True,
        "explicit_exclusions": list(outcome_record.get("explicit_exclusions", [])),
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


def _classify_audit_status(*, outcome_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if outcome_status == "blocked":
        return "blocked"
    if outcome_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, outcome_status: str, indicators: Mapping[str, Any]) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
    ):
        return "blocked"
    if outcome_status == "blocked":
        return "blocked"
    if (
        outcome_status == "needs_review"
        or indicators.get("has_pending_outcomes")
        or indicators.get("has_needs_review_outcomes")
    ):
        return "needs_review"
    return "ready"


def _has_required_exclusions(outcome_record: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(outcome_record.get("explicit_exclusions")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _outcomes_preserve_manual_safeguards(items: Any) -> bool:
    for item in _as_list(items):
        if not isinstance(item, Mapping):
            return False
        if item.get("manual_only") is not True:
            return False
        if item.get("order_intent") is not None:
            return False
        if item.get("broker_order_id") is not None:
            return False
        if item.get("automatic_action") is not None:
            return False
    return True


def _count_fields_match_outcome_lists(outcome_record: Mapping[str, Any]) -> bool:
    summary = _as_mapping(outcome_record.get("outcome_summary"))
    return all(
        [
            _safe_int(summary.get("closed_outcome_count"))
            == len(_as_list(outcome_record.get("closed_outcomes"))),
            _safe_int(summary.get("open_outcome_count"))
            == len(_as_list(outcome_record.get("open_outcomes"))),
            _safe_int(summary.get("pending_outcome_count"))
            == len(_as_list(outcome_record.get("pending_outcomes"))),
            _safe_int(summary.get("needs_review_outcome_count"))
            == len(_as_list(outcome_record.get("needs_review_outcomes"))),
            _safe_int(summary.get("blocked_item_count"))
            == len(_as_list(outcome_record.get("blocked_items"))),
        ]
    )


def _blocked_items_have_reasons(outcome_record: Mapping[str, Any]) -> bool:
    for item in _as_list(outcome_record.get("blocked_items")):
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


def _safe_float(value: Any) -> float:
    result = _safe_float_or_none(value)
    return float(result) if result is not None else 0.0


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _classify_operation_status(
    *,
    outcome_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {outcome_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {outcome_status, audit_status, health_status}:
        return "needs_review"
    return "ready"
