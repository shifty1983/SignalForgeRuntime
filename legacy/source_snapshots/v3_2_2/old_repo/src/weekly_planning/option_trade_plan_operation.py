from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.weekly_planning.option_trade_plan import (
    EXCLUDED_ACTIONS,
    VALID_PLAN_STATUSES,
    build_weekly_option_trade_plan,
)


OPERATION_SCHEMA_VERSION = "weekly_option_trade_plan_operation.v1"
EVENT_SCHEMA_VERSION = "weekly_option_trade_plan_operation_event.v1"
AUDIT_SCHEMA_VERSION = "weekly_option_trade_plan_audit.v1"
HEALTH_SCHEMA_VERSION = "weekly_option_trade_plan_health.v1"

OPERATION_TYPE = "weekly_option_trade_plan_operation"

REQUIRED_EXCLUSIONS = tuple(EXCLUDED_ACTIONS)


def run_weekly_option_trade_plan_operation(
    option_strategy_candidate_results: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    portfolio_snapshot: Mapping[str, Any] | None = None,
    max_new_trades: int | None = None,
    max_candidates_per_symbol: int | None = 3,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """
    Run a deterministic weekend option trade plan operation.

    This operation wraps the local weekly option trade plan artifact with
    operation, audit, health, and optional JSONL event-log outputs. It does not
    call broker APIs, route orders, submit orders, model fills, perform live
    execution, model slippage, or generate maintenance/defense actions.
    """

    weekly_option_trade_plan = build_weekly_option_trade_plan(
        option_strategy_candidate_results,
        plan_date=plan_date,
        portfolio_snapshot=portfolio_snapshot,
        max_new_trades=max_new_trades,
        max_candidates_per_symbol=max_candidates_per_symbol,
        metadata=metadata,
    )
    audit_report = build_weekly_option_trade_plan_audit_report(
        weekly_option_trade_plan
    )
    health_report = build_weekly_option_trade_plan_health_report(
        weekly_option_trade_plan
    )

    events = [
        _build_event(
            weekly_option_trade_plan=weekly_option_trade_plan,
            event_type="weekly_option_trade_plan_operation_started",
            sequence=1,
        ),
        _build_event(
            weekly_option_trade_plan=weekly_option_trade_plan,
            event_type="weekly_option_trade_plan_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        weekly_option_trade_plan=weekly_option_trade_plan,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": weekly_option_trade_plan["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "weekly_option_trade_plan": weekly_option_trade_plan,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(weekly_option_trade_plan.get("excluded", [])),
    }


def build_weekly_option_trade_plan_audit_report(
    weekly_option_trade_plan: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="plan_artifact_type_valid",
            passed=weekly_option_trade_plan.get("artifact_type")
            == "weekly_option_trade_plan",
            severity="blocker",
            message="weekly option trade plan artifact type is valid",
            failure_message="weekly option trade plan artifact type is invalid",
        ),
        _check(
            name="plan_status_valid",
            passed=weekly_option_trade_plan.get("status") in VALID_PLAN_STATUSES,
            severity="blocker",
            message="weekly option trade plan status is valid",
            failure_message="weekly option trade plan status is invalid",
        ),
        _check(
            name="plan_date_present",
            passed=bool(_string_or_none(weekly_option_trade_plan.get("plan_date"))),
            severity="blocker",
            message="weekly option trade plan date is present",
            failure_message="weekly option trade plan date is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(weekly_option_trade_plan),
            severity="blocker",
            message="weekly option trade plan exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="manual_approval_required_for_all_actions",
            passed=_all_actions_require_manual_approval(weekly_option_trade_plan),
            severity="blocker",
            message="all weekly trade actions require manual approval",
            failure_message="one or more weekly trade actions bypass manual approval",
        ),
        _check(
            name="no_order_intents_created",
            passed=_no_order_intents_created(weekly_option_trade_plan),
            severity="blocker",
            message="weekly plan did not create order intents",
            failure_message="weekly plan created one or more order intents",
        ),
        _check(
            name="no_submitted_execution_statuses",
            passed=_no_submitted_execution_statuses(weekly_option_trade_plan),
            severity="blocker",
            message="weekly plan did not mark actions as submitted",
            failure_message="weekly plan contains a submitted execution status",
        ),
        _check(
            name="count_fields_match_action_lists",
            passed=_count_fields_match_action_lists(weekly_option_trade_plan),
            severity="blocker",
            message="weekly option trade plan counts match action lists",
            failure_message="weekly option trade plan counts do not match action lists",
        ),
        _check(
            name="blocked_plan_has_reason",
            passed=_blocked_plan_has_reason(weekly_option_trade_plan),
            severity="warning",
            message="blocked weekly plan reason handling is valid",
            failure_message="blocked weekly plan is missing blocked reasons/items",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            plan_status=str(weekly_option_trade_plan.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(weekly_option_trade_plan.get("excluded", [])),
    }


def build_weekly_option_trade_plan_health_report(
    weekly_option_trade_plan: Mapping[str, Any],
) -> dict[str, Any]:
    plan_status = str(weekly_option_trade_plan.get("status", "needs_review"))
    warnings = list(_strings(weekly_option_trade_plan.get("warnings")))
    blocked_reasons = list(_strings(weekly_option_trade_plan.get("blocked_reasons")))
    blocked_items = _as_list(weekly_option_trade_plan.get("blocked_items"))
    deferred_actions = _as_list(weekly_option_trade_plan.get("deferred_actions"))

    indicators = {
        "plan_status": plan_status,
        "plan_date": _string_or_none(weekly_option_trade_plan.get("plan_date")),
        "plan_mode": _string_or_none(weekly_option_trade_plan.get("plan_mode")),
        "new_trade_action_count": _safe_int(
            weekly_option_trade_plan.get("new_trade_action_count")
        ),
        "deferred_action_count": _safe_int(
            weekly_option_trade_plan.get("deferred_action_count")
        ),
        "blocked_item_count": _safe_int(
            weekly_option_trade_plan.get("blocked_item_count")
        ),
        "source_candidate_result_count": _safe_int(
            weekly_option_trade_plan.get("source_candidate_result_count")
        ),
        "warning_count": len(warnings),
        "blocked_reason_count": len(blocked_reasons),
        "has_portfolio_snapshot": bool(
            _as_mapping(weekly_option_trade_plan.get("portfolio_snapshot_summary"))
        ),
        "has_deferred_actions": bool(deferred_actions),
        "has_blocked_items": bool(blocked_items),
        "requires_manual_approval": _all_actions_require_manual_approval(
            weekly_option_trade_plan
        ),
        "order_intents_created": not _no_order_intents_created(
            weekly_option_trade_plan
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(plan_status),
        "indicators": indicators,
        "recommendations": _build_health_recommendations(indicators),
        "explicit_exclusions": list(weekly_option_trade_plan.get("excluded", [])),
    }


def _build_operation_record(
    *,
    weekly_option_trade_plan: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _build_summary(weekly_option_trade_plan)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": _build_operation_id(weekly_option_trade_plan),
        "status": weekly_option_trade_plan.get("status", "needs_review"),
        "plan_date": weekly_option_trade_plan.get("plan_date"),
        "plan_mode": weekly_option_trade_plan.get("plan_mode"),
        "summary": summary,
        "audit_status": audit_report.get("status"),
        "health_status": health_report.get("status"),
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(weekly_option_trade_plan.get("excluded", [])),
    }


def _build_event(
    *,
    weekly_option_trade_plan: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "operation_id": _build_operation_id(weekly_option_trade_plan),
        "status": weekly_option_trade_plan.get("status", "needs_review"),
        "summary": _build_summary(weekly_option_trade_plan),
    }


def _build_summary(weekly_option_trade_plan: Mapping[str, Any]) -> dict[str, Any]:
    portfolio_summary = _as_mapping(
        weekly_option_trade_plan.get("portfolio_snapshot_summary")
    )

    return {
        "plan_date": _string_or_none(weekly_option_trade_plan.get("plan_date")),
        "plan_mode": _string_or_none(weekly_option_trade_plan.get("plan_mode")),
        "plan_status": _string_or_none(weekly_option_trade_plan.get("status")),
        "new_trade_action_count": _safe_int(
            weekly_option_trade_plan.get("new_trade_action_count")
        ),
        "deferred_action_count": _safe_int(
            weekly_option_trade_plan.get("deferred_action_count")
        ),
        "blocked_item_count": _safe_int(
            weekly_option_trade_plan.get("blocked_item_count")
        ),
        "source_candidate_result_count": _safe_int(
            weekly_option_trade_plan.get("source_candidate_result_count")
        ),
        "warning_count": len(_strings(weekly_option_trade_plan.get("warnings"))),
        "blocked_reason_count": len(
            _strings(weekly_option_trade_plan.get("blocked_reasons"))
        ),
        "portfolio_id": _string_or_none(portfolio_summary.get("portfolio_id")),
        "portfolio_as_of": _string_or_none(portfolio_summary.get("as_of")),
    }


def _build_operation_id(weekly_option_trade_plan: Mapping[str, Any]) -> str:
    plan_date = _string_or_none(weekly_option_trade_plan.get("plan_date")) or "unknown_date"
    plan_mode = _string_or_none(weekly_option_trade_plan.get("plan_mode")) or "unknown_mode"
    status = _string_or_none(weekly_option_trade_plan.get("status")) or "unknown_status"
    source_count = _safe_int(weekly_option_trade_plan.get("source_candidate_result_count"))
    action_count = _safe_int(weekly_option_trade_plan.get("new_trade_action_count"))

    return f"weekly_option_trade_plan:{plan_date}:{plan_mode}:{status}:{source_count}:{action_count}"


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
    plan_status: str,
    checks: Sequence[Mapping[str, Any]],
) -> str:
    if any(
        not check.get("passed") and check.get("severity") == "blocker"
        for check in checks
    ):
        return "blocked"

    if plan_status == "blocked":
        return "blocked"

    if plan_status == "needs_review" or any(
        not check.get("passed") for check in checks
    ):
        return "needs_review"

    return "ready"


def _classify_health_status(plan_status: str) -> str:
    if plan_status == "blocked":
        return "blocked"
    if plan_status == "needs_review":
        return "degraded"
    return "healthy"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("new_trade_action_count")) == 0:
        recommendations.append("review candidate generation because no new trade actions were selected")

    if bool(indicators.get("has_deferred_actions")):
        recommendations.append("review deferred weekly trade actions against portfolio capacity")

    if bool(indicators.get("has_blocked_items")):
        recommendations.append("review blocked weekly trade plan items")

    if _safe_int(indicators.get("warning_count")) > 0:
        recommendations.append("review weekly option trade plan warnings")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve weekly option trade plan blocked reasons")

    if not bool(indicators.get("has_portfolio_snapshot")):
        recommendations.append("include a portfolio snapshot for weekend review context")

    if bool(indicators.get("order_intents_created")):
        recommendations.append("remove order intents from weekly planning output")

    return _dedupe_strings(recommendations)


def _has_required_exclusions(weekly_option_trade_plan: Mapping[str, Any]) -> bool:
    exclusions = set(_strings(weekly_option_trade_plan.get("excluded")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _all_actions_require_manual_approval(
    weekly_option_trade_plan: Mapping[str, Any],
) -> bool:
    actions = _all_plan_actions(weekly_option_trade_plan)
    return all(action.get("requires_manual_approval") is True for action in actions)


def _no_order_intents_created(weekly_option_trade_plan: Mapping[str, Any]) -> bool:
    actions = _all_plan_actions(weekly_option_trade_plan)
    return all(action.get("order_intent") is None for action in actions)


def _no_submitted_execution_statuses(
    weekly_option_trade_plan: Mapping[str, Any],
) -> bool:
    actions = _all_plan_actions(weekly_option_trade_plan)
    return all(action.get("execution_status") == "not_submitted" for action in actions)


def _count_fields_match_action_lists(weekly_option_trade_plan: Mapping[str, Any]) -> bool:
    return (
        _safe_int(weekly_option_trade_plan.get("new_trade_action_count"))
        == len(_as_list(weekly_option_trade_plan.get("new_trade_actions")))
        and _safe_int(weekly_option_trade_plan.get("deferred_action_count"))
        == len(_as_list(weekly_option_trade_plan.get("deferred_actions")))
        and _safe_int(weekly_option_trade_plan.get("blocked_item_count"))
        == len(_as_list(weekly_option_trade_plan.get("blocked_items")))
    )


def _blocked_plan_has_reason(weekly_option_trade_plan: Mapping[str, Any]) -> bool:
    if weekly_option_trade_plan.get("status") != "blocked":
        return True

    return bool(
        _strings(weekly_option_trade_plan.get("blocked_reasons"))
        or _as_list(weekly_option_trade_plan.get("blocked_items"))
    )


def _all_plan_actions(weekly_option_trade_plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    actions: list[Mapping[str, Any]] = []
    for key in ("new_trade_actions", "deferred_actions"):
        for item in _as_list(weekly_option_trade_plan.get(key)):
            if isinstance(item, Mapping):
                actions.append(item)
    return actions


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


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

