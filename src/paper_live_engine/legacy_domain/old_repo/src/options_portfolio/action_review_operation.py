from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.options_portfolio.action_review import (
    EXPLICIT_EXCLUSIONS,
    build_options_manual_action_review,
)


OPERATION_SCHEMA_VERSION = "options_manual_action_review_operation.v1"
EVENT_SCHEMA_VERSION = "options_manual_action_review_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_manual_action_review_audit.v1"
HEALTH_SCHEMA_VERSION = "options_manual_action_review_health.v1"

OPERATION_TYPE = "options_manual_action_review_operation"
VALID_REVIEW_STATUSES = {"ready", "needs_review", "blocked"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_manual_action_review_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run the manual options action review as an auditable operation.

    This operation records human review decisions against an options manual
    action queue. It does not call broker APIs, route orders, submit orders,
    model fills, perform live execution, model slippage, or create automatic
    close/roll/defense orders.
    """

    review = build_options_manual_action_review(source)
    audit_report = build_options_manual_action_review_audit_report(review)
    health_report = build_options_manual_action_review_health_report(review)

    events = [
        _build_event(
            review=review,
            event_type="options_manual_action_review_operation_started",
            sequence=1,
        ),
        _build_event(
            review=review,
            event_type="options_manual_action_review_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        review=review,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": review["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_manual_action_review": review,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(review.get("explicit_exclusions", [])),
    }


def build_options_manual_action_review_audit_report(review: Mapping[str, Any]) -> dict[str, Any]:
    checks = [
        _check(
            name="review_artifact_type_valid",
            passed=review.get("artifact_type") == "options_manual_action_review",
            severity="blocker",
            message="options manual action review artifact type is valid",
            failure_message="options manual action review artifact type is invalid",
        ),
        _check(
            name="review_status_valid",
            passed=review.get("status") in VALID_REVIEW_STATUSES,
            severity="blocker",
            message="options manual action review status is valid",
            failure_message="options manual action review status is invalid",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(review),
            severity="blocker",
            message="options manual action review exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="manual_approval_required",
            passed=review.get("requires_manual_approval") is True,
            severity="blocker",
            message="options manual action review requires manual approval",
            failure_message="options manual action review does not require manual approval",
        ),
        _check(
            name="approved_actions_preserve_manual_handling",
            passed=_approved_actions_preserve_manual_handling(review.get("approved_actions")),
            severity="blocker",
            message="approved actions are approved for manual handling only",
            failure_message="one or more approved actions bypass manual handling safeguards",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(review, "order_intent"),
            severity="blocker",
            message="options manual action review did not create order intents",
            failure_message="options manual action review created one or more order intents",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                review,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options manual action review did not create automatic actions",
            failure_message="options manual action review created one or more automatic actions",
        ),
        _check(
            name="count_fields_match_review_lists",
            passed=_count_fields_match_review_lists(review),
            severity="blocker",
            message="options manual action review counts match review lists",
            failure_message="options manual action review counts do not match review lists",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(review),
            severity="warning",
            message="blocked manual action review items include reasons",
            failure_message="one or more blocked manual action review items are missing reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            review_status=str(review.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(review.get("explicit_exclusions", [])),
    }


def build_options_manual_action_review_health_report(review: Mapping[str, Any]) -> dict[str, Any]:
    review_status = str(review.get("status", "needs_review"))
    approved_actions = _as_list(review.get("approved_actions"))
    rejected_actions = _as_list(review.get("rejected_actions"))
    deferred_actions = _as_list(review.get("deferred_actions"))
    needs_review_actions = _as_list(review.get("needs_review_actions"))
    pending_actions = _as_list(review.get("pending_actions"))
    blocked_items = _as_list(review.get("blocked_items"))
    review_summary = _as_mapping(review.get("review_summary"))

    indicators = {
        "review_status": review_status,
        "queue_date": _string_or_none(review.get("queue_date")),
        "reviewed_at": _string_or_none(review.get("reviewed_at")),
        "reviewer": _string_or_none(review.get("reviewer")),
        "source_priority_action_count": _safe_int(review_summary.get("source_priority_action_count")),
        "approved_action_count": _safe_int(review_summary.get("approved_action_count")),
        "rejected_action_count": _safe_int(review_summary.get("rejected_action_count")),
        "deferred_action_count": _safe_int(review_summary.get("deferred_action_count")),
        "needs_review_action_count": _safe_int(review_summary.get("needs_review_action_count")),
        "pending_action_count": _safe_int(review_summary.get("pending_action_count")),
        "blocked_item_count": _safe_int(review_summary.get("blocked_item_count")),
        "has_approved_actions": bool(approved_actions),
        "has_rejected_actions": bool(rejected_actions),
        "has_deferred_actions": bool(deferred_actions),
        "has_needs_review_actions": bool(needs_review_actions),
        "has_pending_actions": bool(pending_actions),
        "has_blocked_items": bool(blocked_items),
        "requires_manual_approval": review.get("requires_manual_approval") is True,
        "has_order_intent": _contains_non_null_key(review, "order_intent"),
        "has_automatic_action": _contains_non_null_key(review, "automatic_action"),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(review_status=review_status, indicators=indicators),
        "indicators": indicators,
        "explicit_exclusions": list(review.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    review: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    review_summary = _as_mapping(review.get("review_summary"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": review.get("status"),
        "queue_date": _string_or_none(review.get("queue_date")),
        "reviewed_at": _string_or_none(review.get("reviewed_at")),
        "reviewer": _string_or_none(review.get("reviewer")),
        "summary": {
            "source_priority_action_count": _safe_int(review_summary.get("source_priority_action_count")),
            "approved_action_count": _safe_int(review_summary.get("approved_action_count")),
            "rejected_action_count": _safe_int(review_summary.get("rejected_action_count")),
            "deferred_action_count": _safe_int(review_summary.get("deferred_action_count")),
            "needs_review_action_count": _safe_int(review_summary.get("needs_review_action_count")),
            "pending_action_count": _safe_int(review_summary.get("pending_action_count")),
            "blocked_item_count": _safe_int(review_summary.get("blocked_item_count")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "requires_manual_approval": True,
        "explicit_exclusions": list(review.get("explicit_exclusions", [])),
    }


def _build_event(*, review: Mapping[str, Any], event_type: str, sequence: int) -> dict[str, Any]:
    review_summary = _as_mapping(review.get("review_summary"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": review.get("status"),
        "queue_date": _string_or_none(review.get("queue_date")),
        "reviewed_at": _string_or_none(review.get("reviewed_at")),
        "approved_action_count": _safe_int(review_summary.get("approved_action_count")),
        "pending_action_count": _safe_int(review_summary.get("pending_action_count")),
        "blocked_item_count": _safe_int(review_summary.get("blocked_item_count")),
        "requires_manual_approval": True,
        "explicit_exclusions": list(review.get("explicit_exclusions", [])),
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


def _classify_audit_status(*, review_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if review_status == "blocked":
        return "blocked"
    if review_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, review_status: str, indicators: Mapping[str, Any]) -> str:
    if indicators.get("has_order_intent") or indicators.get("has_automatic_action"):
        return "blocked"
    if not indicators.get("requires_manual_approval"):
        return "blocked"
    if review_status == "blocked":
        return "blocked"
    if (
        review_status == "needs_review"
        or indicators.get("has_approved_actions")
        or indicators.get("has_needs_review_actions")
        or indicators.get("has_pending_actions")
    ):
        return "needs_review"
    return "ready"


def _has_required_exclusions(review: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(review.get("explicit_exclusions")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _approved_actions_preserve_manual_handling(items: Any) -> bool:
    for item in _as_list(items):
        if not isinstance(item, Mapping):
            return False
        if item.get("requires_manual_approval") is not True:
            return False
        if item.get("approved_for_manual_handling") is not True:
            return False
        if item.get("order_intent") is not None:
            return False
        if item.get("automatic_action") is not None:
            return False
    return True


def _count_fields_match_review_lists(review: Mapping[str, Any]) -> bool:
    summary = _as_mapping(review.get("review_summary"))
    return all(
        [
            _safe_int(summary.get("approved_action_count")) == len(_as_list(review.get("approved_actions"))),
            _safe_int(summary.get("rejected_action_count")) == len(_as_list(review.get("rejected_actions"))),
            _safe_int(summary.get("deferred_action_count")) == len(_as_list(review.get("deferred_actions"))),
            _safe_int(summary.get("needs_review_action_count"))
            == len(_as_list(review.get("needs_review_actions"))),
            _safe_int(summary.get("pending_action_count")) == len(_as_list(review.get("pending_actions"))),
            _safe_int(summary.get("blocked_item_count")) == len(_as_list(review.get("blocked_items"))),
        ]
    )


def _blocked_items_have_reasons(review: Mapping[str, Any]) -> bool:
    for item in _as_list(review.get("blocked_items")):
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

