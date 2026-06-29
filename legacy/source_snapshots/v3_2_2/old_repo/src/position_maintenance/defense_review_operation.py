from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.position_maintenance.defense_review import (
    VALID_DEFENSE_REVIEW_STATUSES,
    build_options_strategy_defense_review,
)
from src.position_maintenance.defense_candidate_builder import EXCLUDED_ACTIONS


OPERATION_SCHEMA_VERSION = "options_strategy_defense_review_operation.v1"
EVENT_SCHEMA_VERSION = "options_strategy_defense_review_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_strategy_defense_review_audit.v1"
HEALTH_SCHEMA_VERSION = "options_strategy_defense_review_health.v1"

OPERATION_TYPE = "options_strategy_defense_review_operation"
REQUIRED_EXCLUSIONS = tuple(EXCLUDED_ACTIONS)


def run_options_strategy_defense_review_operation(
    positions: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    market_regime: str | None = None,
    regime_options_policy: Mapping[str, Any] | None = None,
    asset_behavior_options_policy: Mapping[str, Any] | None = None,
    option_behavior_options_policy: Mapping[str, Any] | None = None,
    max_candidates_per_position: int | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """
    Run a deterministic options-strategy defense review operation.

    This wraps the manual options strategy defense review with operation,
    audit, health, and optional JSONL event-log outputs. It does not call
    broker APIs, route orders, submit orders, model fills, perform live
    execution, model slippage, or create automatic close/roll/defense orders.
    """

    defense_review = build_options_strategy_defense_review(
        positions,
        plan_date=plan_date,
        market_regime=market_regime,
        regime_options_policy=regime_options_policy,
        asset_behavior_options_policy=asset_behavior_options_policy,
        option_behavior_options_policy=option_behavior_options_policy,
        max_candidates_per_position=max_candidates_per_position,
    )
    audit_report = build_options_strategy_defense_review_audit_report(defense_review)
    health_report = build_options_strategy_defense_review_health_report(defense_review)

    events = [
        _build_event(
            defense_review=defense_review,
            event_type="options_strategy_defense_review_operation_started",
            sequence=1,
        ),
        _build_event(
            defense_review=defense_review,
            event_type="options_strategy_defense_review_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        defense_review=defense_review,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": defense_review["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_strategy_defense_review": defense_review,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(defense_review.get("excluded", [])),
    }


def build_options_strategy_defense_review_audit_report(
    defense_review: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="review_artifact_type_valid",
            passed=defense_review.get("artifact_type") == "options_strategy_defense_review",
            severity="blocker",
            message="options strategy defense review artifact type is valid",
            failure_message="options strategy defense review artifact type is invalid",
        ),
        _check(
            name="review_status_valid",
            passed=defense_review.get("status") in VALID_DEFENSE_REVIEW_STATUSES,
            severity="blocker",
            message="options strategy defense review status is valid",
            failure_message="options strategy defense review status is invalid",
        ),
        _check(
            name="plan_date_present",
            passed=bool(_string_or_none(defense_review.get("plan_date"))),
            severity="blocker",
            message="options strategy defense review date is present",
            failure_message="options strategy defense review date is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(defense_review),
            severity="blocker",
            message="options strategy defense review exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="manual_approval_required_for_all_outputs",
            passed=_all_outputs_require_manual_approval(defense_review),
            severity="blocker",
            message="all options strategy defense review outputs require manual approval",
            failure_message="one or more defense review outputs bypass manual approval",
        ),
        _check(
            name="no_order_intents_created",
            passed=_no_order_intents_created(defense_review),
            severity="blocker",
            message="options strategy defense review did not create order intents",
            failure_message="options strategy defense review created one or more order intents",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=_no_automatic_actions_created(defense_review),
            severity="blocker",
            message="options strategy defense review did not create automatic actions",
            failure_message="options strategy defense review created one or more automatic actions",
        ),
        _check(
            name="count_fields_match_review_lists",
            passed=_count_fields_match_review_lists(defense_review),
            severity="blocker",
            message="options strategy defense review counts match review lists",
            failure_message="options strategy defense review counts do not match review lists",
        ),
        _check(
            name="blocked_review_has_reason",
            passed=_blocked_review_has_reason(defense_review),
            severity="warning",
            message="blocked options strategy defense review reason handling is valid",
            failure_message="blocked options strategy defense review is missing blocked reasons/items",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            review_status=str(defense_review.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(defense_review.get("excluded", [])),
    }


def build_options_strategy_defense_review_health_report(
    defense_review: Mapping[str, Any],
) -> dict[str, Any]:
    review_status = str(defense_review.get("status", "needs_review"))
    warnings = list(_strings(defense_review.get("warnings")))
    blocked_reasons = list(_strings(defense_review.get("blocked_reasons")))
    review_candidates = _as_list(defense_review.get("review_candidates"))
    monitor_items = _as_list(defense_review.get("monitor_items"))
    blocked_items = _as_list(defense_review.get("blocked_items"))
    urgency_summary = _as_mapping(defense_review.get("urgency_summary"))

    indicators = {
        "review_status": review_status,
        "plan_date": _string_or_none(defense_review.get("plan_date")),
        "review_mode": _string_or_none(defense_review.get("review_mode")),
        "market_regime": _string_or_none(defense_review.get("market_regime")),
        "position_count": _safe_int(defense_review.get("position_count")),
        "playbook_count": _safe_int(defense_review.get("playbook_count")),
        "candidate_count": _safe_int(defense_review.get("candidate_count")),
        "manual_review_count": _safe_int(defense_review.get("manual_review_count")),
        "monitor_item_count": _safe_int(defense_review.get("monitor_item_count")),
        "blocked_count": _safe_int(defense_review.get("blocked_count")),
        "warning_count": len(warnings),
        "blocked_reason_count": len(blocked_reasons),
        "high_urgency_count": _safe_int(urgency_summary.get("high")),
        "has_review_candidates": bool(review_candidates),
        "has_monitor_items": bool(monitor_items),
        "has_blocked_items": bool(blocked_items),
        "requires_manual_approval": _all_outputs_require_manual_approval(defense_review),
        "order_intents_created": not _no_order_intents_created(defense_review),
        "automatic_actions_created": not _no_automatic_actions_created(defense_review),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(review_status),
        "indicators": indicators,
        "recommendations": _build_health_recommendations(indicators),
        "explicit_exclusions": list(defense_review.get("excluded", [])),
    }


def _build_operation_record(
    *,
    defense_review: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary = _build_summary(defense_review)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": _build_operation_id(defense_review),
        "status": defense_review.get("status", "needs_review"),
        "plan_date": defense_review.get("plan_date"),
        "review_mode": defense_review.get("review_mode"),
        "summary": summary,
        "metadata": dict(metadata or {}),
        "audit_status": audit_report.get("status"),
        "health_status": health_report.get("status"),
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(defense_review.get("excluded", [])),
    }


def _build_event(
    *,
    defense_review: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "operation_id": _build_operation_id(defense_review),
        "status": defense_review.get("status", "needs_review"),
        "summary": _build_summary(defense_review),
    }


def _build_summary(defense_review: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "plan_date": _string_or_none(defense_review.get("plan_date")),
        "review_mode": _string_or_none(defense_review.get("review_mode")),
        "review_status": _string_or_none(defense_review.get("status")),
        "market_regime": _string_or_none(defense_review.get("market_regime")),
        "position_count": _safe_int(defense_review.get("position_count")),
        "playbook_count": _safe_int(defense_review.get("playbook_count")),
        "candidate_count": _safe_int(defense_review.get("candidate_count")),
        "manual_review_count": _safe_int(defense_review.get("manual_review_count")),
        "monitor_item_count": _safe_int(defense_review.get("monitor_item_count")),
        "blocked_count": _safe_int(defense_review.get("blocked_count")),
        "warning_count": len(_strings(defense_review.get("warnings"))),
        "blocked_reason_count": len(_strings(defense_review.get("blocked_reasons"))),
    }


def _build_operation_id(defense_review: Mapping[str, Any]) -> str:
    plan_date = _string_or_none(defense_review.get("plan_date")) or "unknown_date"
    review_mode = _string_or_none(defense_review.get("review_mode")) or "unknown_mode"
    status = _string_or_none(defense_review.get("status")) or "unknown_status"
    position_count = _safe_int(defense_review.get("position_count"))
    candidate_count = _safe_int(defense_review.get("candidate_count"))
    blocked_count = _safe_int(defense_review.get("blocked_count"))

    return (
        f"options_strategy_defense_review:{plan_date}:{review_mode}:{status}:"
        f"{position_count}:{candidate_count}:{blocked_count}"
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


def _classify_audit_status(*, review_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(
        not check.get("passed") and check.get("severity") == "blocker"
        for check in checks
    ):
        return "blocked"
    if review_status == "blocked":
        return "blocked"
    if review_status == "needs_review" or any(not check.get("passed") for check in checks):
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

    if bool(indicators.get("has_review_candidates")):
        recommendations.append("review options strategy defense candidates requiring manual approval")

    if _safe_int(indicators.get("high_urgency_count")) > 0:
        recommendations.append("prioritize high-urgency options strategy defense reviews")

    if bool(indicators.get("has_blocked_items")):
        recommendations.append("review blocked or undefined-risk options strategy defense items")

    if _safe_int(indicators.get("warning_count")) > 0:
        recommendations.append("review options strategy defense warnings")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve options strategy defense blocked reasons")

    if bool(indicators.get("order_intents_created")):
        recommendations.append("remove order intents from options strategy defense review output")

    if bool(indicators.get("automatic_actions_created")):
        recommendations.append("remove automatic actions from options strategy defense review output")

    return _dedupe_strings(recommendations)


def _has_required_exclusions(defense_review: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(defense_review.get("excluded")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _all_outputs_require_manual_approval(defense_review: Mapping[str, Any]) -> bool:
    outputs = _all_review_outputs(defense_review)
    if defense_review.get("requires_manual_approval") is not True:
        return False
    return all(output.get("requires_manual_approval") is True for output in outputs)


def _no_order_intents_created(defense_review: Mapping[str, Any]) -> bool:
    outputs = _all_review_outputs(defense_review)
    return defense_review.get("order_intent") is None and all(
        output.get("order_intent") is None for output in outputs
    )


def _no_automatic_actions_created(defense_review: Mapping[str, Any]) -> bool:
    outputs = _all_review_outputs(defense_review)
    return defense_review.get("automatic_action") is None and all(
        output.get("automatic_action") is None
        and output.get("maintenance_action") is None
        and output.get("defense_action") is None
        for output in outputs
    )


def _count_fields_match_review_lists(defense_review: Mapping[str, Any]) -> bool:
    return (
        _safe_int(defense_review.get("candidate_count"))
        == len(_as_list(defense_review.get("review_candidates")))
        and _safe_int(defense_review.get("manual_review_count"))
        == len(_as_list(defense_review.get("review_candidates")))
        and _safe_int(defense_review.get("monitor_item_count"))
        == len(_as_list(defense_review.get("monitor_items")))
        and _safe_int(defense_review.get("blocked_count"))
        == len(_as_list(defense_review.get("blocked_items")))
    )


def _blocked_review_has_reason(defense_review: Mapping[str, Any]) -> bool:
    if defense_review.get("status") != "blocked":
        return True
    return bool(
        _strings(defense_review.get("blocked_reasons"))
        or _as_list(defense_review.get("blocked_items"))
    )


def _all_review_outputs(defense_review: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    outputs: list[Mapping[str, Any]] = []
    for key in ("review_candidates", "monitor_items", "blocked_items"):
        for item in _as_list(defense_review.get(key)):
            if isinstance(item, Mapping):
                outputs.append(item)
    return outputs


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

