from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.position_maintenance.position_review import (
    EXCLUDED_ACTIONS,
    VALID_REVIEW_STATUSES,
    build_position_maintenance_review,
)


OPERATION_SCHEMA_VERSION = "position_maintenance_review_operation.v1"
EVENT_SCHEMA_VERSION = "position_maintenance_review_operation_event.v1"
AUDIT_SCHEMA_VERSION = "position_maintenance_review_audit.v1"
HEALTH_SCHEMA_VERSION = "position_maintenance_review_health.v1"

OPERATION_TYPE = "position_maintenance_review_operation"

REQUIRED_EXCLUSIONS = tuple(EXCLUDED_ACTIONS)


def run_position_maintenance_review_operation(
    open_positions: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    market_regime: str | None = None,
    thresholds: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """
    Run a deterministic position maintenance review operation.

    This operation wraps the local position maintenance review artifact with
    operation, audit, health, and optional JSONL event-log outputs. It does not
    call broker APIs, route orders, submit orders, model fills, perform live
    execution, model slippage, or create automatic close/roll/defense orders.
    """

    position_maintenance_review = build_position_maintenance_review(
        open_positions,
        plan_date=plan_date,
        market_regime=market_regime,
        thresholds=thresholds,
        metadata=metadata,
    )
    audit_report = build_position_maintenance_review_audit_report(
        position_maintenance_review
    )
    health_report = build_position_maintenance_review_health_report(
        position_maintenance_review
    )

    events = [
        _build_event(
            position_maintenance_review=position_maintenance_review,
            event_type="position_maintenance_review_operation_started",
            sequence=1,
        ),
        _build_event(
            position_maintenance_review=position_maintenance_review,
            event_type="position_maintenance_review_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        position_maintenance_review=position_maintenance_review,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": position_maintenance_review["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "position_maintenance_review": position_maintenance_review,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(position_maintenance_review.get("excluded", [])),
    }


def build_position_maintenance_review_audit_report(
    position_maintenance_review: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="review_artifact_type_valid",
            passed=position_maintenance_review.get("artifact_type")
            == "position_maintenance_review",
            severity="blocker",
            message="position maintenance review artifact type is valid",
            failure_message="position maintenance review artifact type is invalid",
        ),
        _check(
            name="review_status_valid",
            passed=position_maintenance_review.get("status") in VALID_REVIEW_STATUSES,
            severity="blocker",
            message="position maintenance review status is valid",
            failure_message="position maintenance review status is invalid",
        ),
        _check(
            name="plan_date_present",
            passed=bool(_string_or_none(position_maintenance_review.get("plan_date"))),
            severity="blocker",
            message="position maintenance review date is present",
            failure_message="position maintenance review date is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(position_maintenance_review),
            severity="blocker",
            message="position maintenance review exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="manual_approval_required_for_all_review_outputs",
            passed=_all_review_outputs_require_manual_approval(
                position_maintenance_review
            ),
            severity="blocker",
            message="all position maintenance review outputs require manual approval",
            failure_message="one or more review outputs bypass manual approval",
        ),
        _check(
            name="no_order_intents_created",
            passed=_no_order_intents_created(position_maintenance_review),
            severity="blocker",
            message="position maintenance review did not create order intents",
            failure_message="position maintenance review created one or more order intents",
        ),
        _check(
            name="no_maintenance_or_defense_actions_created",
            passed=_no_maintenance_or_defense_actions_created(
                position_maintenance_review
            ),
            severity="blocker",
            message="position maintenance review did not create maintenance or defense actions",
            failure_message="position maintenance review created maintenance or defense actions",
        ),
        _check(
            name="count_fields_match_review_lists",
            passed=_count_fields_match_review_lists(position_maintenance_review),
            severity="blocker",
            message="position maintenance review counts match review lists",
            failure_message="position maintenance review counts do not match review lists",
        ),
        _check(
            name="blocked_review_has_reason",
            passed=_blocked_review_has_reason(position_maintenance_review),
            severity="warning",
            message="blocked position maintenance reason handling is valid",
            failure_message="blocked position maintenance review is missing blocked reasons/items",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            review_status=str(position_maintenance_review.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(position_maintenance_review.get("excluded", [])),
    }


def build_position_maintenance_review_health_report(
    position_maintenance_review: Mapping[str, Any],
) -> dict[str, Any]:
    review_status = str(position_maintenance_review.get("status", "needs_review"))
    warnings = list(_strings(position_maintenance_review.get("warnings")))
    blocked_reasons = list(_strings(position_maintenance_review.get("blocked_reasons")))
    review_actions = _as_list(position_maintenance_review.get("review_actions"))
    monitor_items = _as_list(position_maintenance_review.get("monitor_items"))
    blocked_items = _as_list(position_maintenance_review.get("blocked_items"))

    indicators = {
        "review_status": review_status,
        "plan_date": _string_or_none(position_maintenance_review.get("plan_date")),
        "review_mode": _string_or_none(position_maintenance_review.get("review_mode")),
        "market_regime": _string_or_none(position_maintenance_review.get("market_regime")),
        "position_count": _safe_int(position_maintenance_review.get("position_count")),
        "review_action_count": _safe_int(
            position_maintenance_review.get("review_action_count")
        ),
        "monitor_item_count": _safe_int(
            position_maintenance_review.get("monitor_item_count")
        ),
        "blocked_item_count": _safe_int(
            position_maintenance_review.get("blocked_item_count")
        ),
        "warning_count": len(warnings),
        "blocked_reason_count": len(blocked_reasons),
        "high_urgency_review_action_count": _high_urgency_review_action_count(
            review_actions
        ),
        "has_review_actions": bool(review_actions),
        "has_monitor_items": bool(monitor_items),
        "has_blocked_items": bool(blocked_items),
        "requires_manual_approval": _all_review_outputs_require_manual_approval(
            position_maintenance_review
        ),
        "order_intents_created": not _no_order_intents_created(
            position_maintenance_review
        ),
        "maintenance_or_defense_actions_created": not _no_maintenance_or_defense_actions_created(
            position_maintenance_review
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(review_status),
        "indicators": indicators,
        "recommendations": _build_health_recommendations(indicators),
        "explicit_exclusions": list(position_maintenance_review.get("excluded", [])),
    }


def _build_operation_record(
    *,
    position_maintenance_review: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _build_summary(position_maintenance_review)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": _build_operation_id(position_maintenance_review),
        "status": position_maintenance_review.get("status", "needs_review"),
        "plan_date": position_maintenance_review.get("plan_date"),
        "review_mode": position_maintenance_review.get("review_mode"),
        "summary": summary,
        "audit_status": audit_report.get("status"),
        "health_status": health_report.get("status"),
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(position_maintenance_review.get("excluded", [])),
    }


def _build_event(
    *,
    position_maintenance_review: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "operation_id": _build_operation_id(position_maintenance_review),
        "status": position_maintenance_review.get("status", "needs_review"),
        "summary": _build_summary(position_maintenance_review),
    }


def _build_summary(position_maintenance_review: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "plan_date": _string_or_none(position_maintenance_review.get("plan_date")),
        "review_mode": _string_or_none(position_maintenance_review.get("review_mode")),
        "review_status": _string_or_none(position_maintenance_review.get("status")),
        "market_regime": _string_or_none(
            position_maintenance_review.get("market_regime")
        ),
        "position_count": _safe_int(position_maintenance_review.get("position_count")),
        "review_action_count": _safe_int(
            position_maintenance_review.get("review_action_count")
        ),
        "monitor_item_count": _safe_int(
            position_maintenance_review.get("monitor_item_count")
        ),
        "blocked_item_count": _safe_int(
            position_maintenance_review.get("blocked_item_count")
        ),
        "warning_count": len(_strings(position_maintenance_review.get("warnings"))),
        "blocked_reason_count": len(
            _strings(position_maintenance_review.get("blocked_reasons"))
        ),
    }


def _build_operation_id(position_maintenance_review: Mapping[str, Any]) -> str:
    plan_date = _string_or_none(position_maintenance_review.get("plan_date")) or "unknown_date"
    review_mode = _string_or_none(position_maintenance_review.get("review_mode")) or "unknown_mode"
    status = _string_or_none(position_maintenance_review.get("status")) or "unknown_status"
    position_count = _safe_int(position_maintenance_review.get("position_count"))
    review_action_count = _safe_int(position_maintenance_review.get("review_action_count"))
    blocked_item_count = _safe_int(position_maintenance_review.get("blocked_item_count"))

    return (
        f"position_maintenance_review:{plan_date}:{review_mode}:{status}:"
        f"{position_count}:{review_action_count}:{blocked_item_count}"
    )


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True))
            handle.write("\n")


def _normalize_event_log_path(
    event_log_path: str | PathLike[str] | None,
) -> Path | None:
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


def _classify_audit_status(
    *,
    review_status: str,
    checks: Sequence[Mapping[str, Any]],
) -> str:
    if any(
        not check.get("passed") and check.get("severity") == "blocker"
        for check in checks
    ):
        return "blocked"

    if review_status == "blocked":
        return "blocked"

    if review_status == "needs_review" or any(
        not check.get("passed") for check in checks
    ):
        return "needs_review"

    return "ready"


def _classify_health_status(review_status: str) -> str:
    if review_status == "blocked":
        return "blocked"
    if review_status == "needs_review":
        return "degraded"
    return "healthy"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if bool(indicators.get("has_review_actions")):
        recommendations.append("review position maintenance actions requiring manual attention")

    if _safe_int(indicators.get("high_urgency_review_action_count")) > 0:
        recommendations.append("prioritize high-urgency position reviews before opening new trades")

    if bool(indicators.get("has_blocked_items")):
        recommendations.append("review blocked or undefined-risk position maintenance items")

    if _safe_int(indicators.get("warning_count")) > 0:
        recommendations.append("review position maintenance warnings")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve position maintenance blocked reasons")

    if bool(indicators.get("order_intents_created")):
        recommendations.append("remove order intents from position maintenance review output")

    if bool(indicators.get("maintenance_or_defense_actions_created")):
        recommendations.append("remove automatic maintenance or defense actions from review output")

    return _dedupe_strings(recommendations)


def _has_required_exclusions(position_maintenance_review: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(position_maintenance_review.get("excluded")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _all_review_outputs_require_manual_approval(
    position_maintenance_review: Mapping[str, Any],
) -> bool:
    outputs = _all_review_outputs(position_maintenance_review)
    return all(output.get("requires_manual_approval") is True for output in outputs)


def _no_order_intents_created(position_maintenance_review: Mapping[str, Any]) -> bool:
    outputs = _all_review_outputs(position_maintenance_review)
    return all(output.get("order_intent") is None for output in outputs)


def _no_maintenance_or_defense_actions_created(
    position_maintenance_review: Mapping[str, Any],
) -> bool:
    outputs = _all_review_outputs(position_maintenance_review)
    return all(
        output.get("maintenance_action") is None and output.get("defense_action") is None
        for output in outputs
    )


def _count_fields_match_review_lists(
    position_maintenance_review: Mapping[str, Any],
) -> bool:
    return (
        _safe_int(position_maintenance_review.get("review_action_count"))
        == len(_as_list(position_maintenance_review.get("review_actions")))
        and _safe_int(position_maintenance_review.get("monitor_item_count"))
        == len(_as_list(position_maintenance_review.get("monitor_items")))
        and _safe_int(position_maintenance_review.get("blocked_item_count"))
        == len(_as_list(position_maintenance_review.get("blocked_items")))
    )


def _blocked_review_has_reason(position_maintenance_review: Mapping[str, Any]) -> bool:
    if position_maintenance_review.get("status") != "blocked":
        return True

    return bool(
        _strings(position_maintenance_review.get("blocked_reasons"))
        or _as_list(position_maintenance_review.get("blocked_items"))
    )


def _all_review_outputs(
    position_maintenance_review: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    outputs: list[Mapping[str, Any]] = []
    for key in ("review_actions", "monitor_items", "blocked_items"):
        for item in _as_list(position_maintenance_review.get(key)):
            if isinstance(item, Mapping):
                outputs.append(item)
    return outputs


def _high_urgency_review_action_count(review_actions: Sequence[Any]) -> int:
    return sum(
        1
        for action in review_actions
        if isinstance(action, Mapping) and action.get("urgency") == "high"
    )


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


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

