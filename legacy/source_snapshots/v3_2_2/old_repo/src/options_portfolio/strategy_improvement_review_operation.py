from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.strategy_improvement_review import (
    EXPLICIT_EXCLUSIONS,
    build_options_strategy_improvement_review,
)


OPERATION_SCHEMA_VERSION = "options_strategy_improvement_review_operation.v1"
EVENT_SCHEMA_VERSION = "options_strategy_improvement_review_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_strategy_improvement_review_audit.v1"
HEALTH_SCHEMA_VERSION = "options_strategy_improvement_review_health.v1"

OPERATION_TYPE = "options_strategy_improvement_review_operation"
VALID_REVIEW_STATUSES = {"ready", "needs_review", "blocked"}
VALID_MANUAL_DECISIONS = {
    "continue_tracking",
    "research_required",
    "pause_candidate",
    "blocked",
}
VALID_ACTION_PRIORITIES = {"high", "normal"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_strategy_improvement_review_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run options strategy improvement review as an auditable operation.

    This operation produces a manual decision only. It never calls broker APIs,
    routes orders, submits orders, models fills, performs live execution, models
    slippage, creates automatic close/roll/defense orders, changes strategy
    logic/parameters automatically, or pauses strategies automatically.
    """

    improvement_review = build_options_strategy_improvement_review(source or {})
    audit_report = build_options_strategy_improvement_review_audit_report(improvement_review)
    health_report = build_options_strategy_improvement_review_health_report(improvement_review)
    operation_status = _classify_operation_status(
        review_status=str(improvement_review.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            improvement_review=improvement_review,
            event_type="options_strategy_improvement_review_operation_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            improvement_review=improvement_review,
            event_type="options_strategy_improvement_review_operation_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        improvement_review=improvement_review,
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
        "options_strategy_improvement_review": improvement_review,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(improvement_review.get("explicit_exclusions", [])),
    }


def build_options_strategy_improvement_review_audit_report(
    improvement_review: Mapping[str, Any]
) -> dict[str, Any]:
    checks = [
        _check(
            name="improvement_review_artifact_type_valid",
            passed=improvement_review.get("artifact_type") == "options_strategy_improvement_review",
            severity="blocker",
            message="options strategy improvement review artifact type is valid",
            failure_message="options strategy improvement review artifact type is invalid",
        ),
        _check(
            name="improvement_review_status_valid",
            passed=improvement_review.get("status") in VALID_REVIEW_STATUSES,
            severity="blocker",
            message="options strategy improvement review status is valid",
            failure_message="options strategy improvement review status is invalid",
        ),
        _check(
            name="manual_decision_valid",
            passed=improvement_review.get("manual_decision") in VALID_MANUAL_DECISIONS,
            severity="blocker",
            message="options strategy improvement manual decision is valid",
            failure_message="options strategy improvement manual decision is invalid",
        ),
        _check(
            name="review_summary_present",
            passed=isinstance(improvement_review.get("review_summary"), Mapping),
            severity="blocker",
            message="options strategy improvement review summary is present",
            failure_message="options strategy improvement review summary is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(improvement_review),
            severity="blocker",
            message="options strategy improvement review exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(improvement_review, "order_intent"),
            severity="blocker",
            message="options strategy improvement review did not create order intents",
            failure_message="options strategy improvement review created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(improvement_review, "broker_order_id"),
            severity="blocker",
            message="options strategy improvement review did not create broker order ids",
            failure_message="options strategy improvement review created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                improvement_review,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options strategy improvement review did not create automatic actions",
            failure_message="options strategy improvement review created one or more automatic actions",
        ),
        _check(
            name="no_automatic_strategy_or_parameter_changes_created",
            passed=not _contains_non_null_key(
                improvement_review,
                "automatic_strategy_change",
                "automatic_parameter_change",
                "strategy_change",
                "parameter_change",
            ),
            severity="blocker",
            message="options strategy improvement review did not create automatic strategy or parameter changes",
            failure_message="options strategy improvement review created automatic strategy or parameter changes",
        ),
        _check(
            name="no_automatic_pause_actions_created",
            passed=not _contains_non_null_key(
                improvement_review,
                "automatic_pause_action",
                "pause_action",
            ),
            severity="blocker",
            message="options strategy improvement review did not create automatic pause actions",
            failure_message="options strategy improvement review created automatic pause actions",
        ),
        _check(
            name="review_actions_have_valid_priorities",
            passed=_review_actions_have_valid_priorities(improvement_review),
            severity="warning",
            message="options strategy improvement review actions have valid priorities",
            failure_message="one or more options strategy improvement review actions have invalid priorities",
        ),
        _check(
            name="review_actions_require_manual_approval",
            passed=_review_actions_require_manual_approval(improvement_review),
            severity="warning",
            message="options strategy improvement review actions require manual approval",
            failure_message="one or more options strategy improvement review actions do not require manual approval",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(improvement_review),
            severity="warning",
            message="blocked options strategy improvement review items include reasons",
            failure_message="one or more blocked options strategy improvement review items are missing reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            review_status=str(improvement_review.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(improvement_review.get("explicit_exclusions", [])),
    }


def build_options_strategy_improvement_review_health_report(
    improvement_review: Mapping[str, Any]
) -> dict[str, Any]:
    review_status = str(improvement_review.get("status", "needs_review"))
    review_summary = _as_mapping(improvement_review.get("review_summary"))
    review_actions = _as_list(improvement_review.get("review_actions"))
    blocked_items = _as_list(improvement_review.get("blocked_items"))

    indicators = {
        "review_status": review_status,
        "manual_decision": _string_or_none(improvement_review.get("manual_decision")),
        "review_date": _string_or_none(improvement_review.get("review_date")),
        "source_queue_count": _safe_int(improvement_review.get("source_queue_count")),
        "source_task_count": _safe_int(review_summary.get("source_task_count")),
        "high_priority_task_count": _safe_int(review_summary.get("high_priority_task_count")),
        "normal_priority_task_count": _safe_int(review_summary.get("normal_priority_task_count")),
        "needs_more_data_task_count": _safe_int(review_summary.get("needs_more_data_task_count")),
        "underperforming_task_count": _safe_int(review_summary.get("underperforming_task_count")),
        "blocked_task_count": _safe_int(review_summary.get("blocked_task_count")),
        "overall_task_count": _safe_int(review_summary.get("overall_task_count")),
        "strategy_task_count": _safe_int(review_summary.get("strategy_task_count")),
        "symbol_task_count": _safe_int(review_summary.get("symbol_task_count")),
        "setup_family_task_count": _safe_int(review_summary.get("setup_family_task_count")),
        "blocked_item_count": len(blocked_items),
        "review_action_count": len(review_actions),
        "has_pause_candidate_decision": improvement_review.get("manual_decision") == "pause_candidate",
        "has_research_required_decision": improvement_review.get("manual_decision") == "research_required",
        "has_blocked_decision": improvement_review.get("manual_decision") == "blocked",
        "has_blocked_items": bool(blocked_items),
        "has_order_intent": _contains_non_null_key(improvement_review, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(improvement_review, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(improvement_review, "automatic_action"),
        "has_automatic_strategy_change": _contains_non_null_key(
            improvement_review,
            "automatic_strategy_change",
            "automatic_parameter_change",
            "strategy_change",
            "parameter_change",
        ),
        "has_automatic_pause_action": _contains_non_null_key(
            improvement_review,
            "automatic_pause_action",
            "pause_action",
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            review_status=review_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(improvement_review.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    improvement_review: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    review_summary = _as_mapping(improvement_review.get("review_summary"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "review_date": _string_or_none(improvement_review.get("review_date")),
        "source_queue_count": _safe_int(improvement_review.get("source_queue_count")),
        "operation_summary": {
            "manual_decision": improvement_review.get("manual_decision"),
            "source_task_count": _safe_int(review_summary.get("source_task_count")),
            "high_priority_task_count": _safe_int(review_summary.get("high_priority_task_count")),
            "normal_priority_task_count": _safe_int(review_summary.get("normal_priority_task_count")),
            "needs_more_data_task_count": _safe_int(review_summary.get("needs_more_data_task_count")),
            "underperforming_task_count": _safe_int(review_summary.get("underperforming_task_count")),
            "blocked_task_count": _safe_int(review_summary.get("blocked_task_count")),
            "overall_task_count": _safe_int(review_summary.get("overall_task_count")),
            "strategy_task_count": _safe_int(review_summary.get("strategy_task_count")),
            "symbol_task_count": _safe_int(review_summary.get("symbol_task_count")),
            "setup_family_task_count": _safe_int(review_summary.get("setup_family_task_count")),
            "blocked_item_count": _safe_int(review_summary.get("blocked_item_count")),
            "review_action_count": len(_as_list(improvement_review.get("review_actions"))),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(improvement_review.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    improvement_review: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    review_summary = _as_mapping(improvement_review.get("review_summary"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "review_date": _string_or_none(improvement_review.get("review_date")),
        "manual_decision": improvement_review.get("manual_decision"),
        "source_queue_count": _safe_int(improvement_review.get("source_queue_count")),
        "source_task_count": _safe_int(review_summary.get("source_task_count")),
        "high_priority_task_count": _safe_int(review_summary.get("high_priority_task_count")),
        "blocked_item_count": _safe_int(review_summary.get("blocked_item_count")),
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
    review_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {review_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {review_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(*, review_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if review_status == "blocked":
        return "blocked"
    if review_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, review_status: str, indicators: Mapping[str, Any]) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
        or indicators.get("has_automatic_strategy_change")
        or indicators.get("has_automatic_pause_action")
    ):
        return "blocked"
    if review_status == "blocked" or indicators.get("has_blocked_decision") or indicators.get("has_blocked_items"):
        return "blocked"
    if (
        review_status == "needs_review"
        or indicators.get("has_pause_candidate_decision")
        or indicators.get("has_research_required_decision")
    ):
        return "needs_review"
    return "ready"


def _has_required_exclusions(improvement_review: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(improvement_review.get("explicit_exclusions")))
    return all(item in exclusions for item in REQUIRED_EXCLUSIONS)


def _review_actions_have_valid_priorities(improvement_review: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("priority") in VALID_ACTION_PRIORITIES
        for item in _as_list(improvement_review.get("review_actions"))
    )


def _review_actions_require_manual_approval(improvement_review: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("requires_manual_approval") is True
        for item in _as_list(improvement_review.get("review_actions"))
    )


def _blocked_items_have_reasons(improvement_review: Mapping[str, Any]) -> bool:
    return all(
        bool(_as_mapping(item).get("reason"))
        for item in _as_list(improvement_review.get("blocked_items"))
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

