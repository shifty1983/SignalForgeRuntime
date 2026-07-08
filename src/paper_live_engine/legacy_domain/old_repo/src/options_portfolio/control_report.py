from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


EXPLICIT_EXCLUSIONS = (
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
)


SECTION_DEFINITIONS = (
    {
        "section": "weekly_trade_plan",
        "label": "Weekly trade plan",
        "keys": ("weekly_option_trade_plan", "options_weekly_trade_plan", "trade_plan"),
    },
    {
        "section": "position_risk_monitor",
        "label": "Position risk monitor",
        "keys": ("options_position_risk_monitor", "position_risk_monitor", "risk_monitor"),
    },
    {
        "section": "manual_action_queue",
        "label": "Manual action queue",
        "keys": ("options_manual_action_queue", "manual_action_queue", "action_queue"),
    },
    {
        "section": "manual_action_review",
        "label": "Manual action review",
        "keys": ("options_manual_action_review", "manual_action_review", "action_review"),
    },
    {
        "section": "manual_execution_record",
        "label": "Manual execution record",
        "keys": (
            "options_manual_execution_record",
            "options_manual_action_execution_record",
            "manual_execution_record",
            "execution_record",
        ),
    },
    {
        "section": "manual_action_outcome_record",
        "label": "Manual action outcome record",
        "keys": (
            "options_manual_action_outcome_record",
            "manual_action_outcome_record",
            "outcome_record",
        ),
    },
    {
        "section": "edge_validation_summary",
        "label": "Edge validation summary",
        "keys": (
            "options_edge_validation_summary",
            "edge_validation_summary",
        ),
    },
    {
        "section": "edge_validation_review",
        "label": "Edge validation review",
        "keys": (
            "options_edge_validation_review",
            "edge_validation_review",
        ),
    },
    {
        "section": "strategy_improvement_queue",
        "label": "Strategy improvement queue",
        "keys": (
            "options_strategy_improvement_queue",
            "strategy_improvement_queue",
        ),
    },
    {
        "section": "strategy_improvement_review",
        "label": "Strategy improvement review",
        "keys": (
            "options_strategy_improvement_review",
            "strategy_improvement_review",
        ),
    },
    {
        "section": "strategy_decision_log",
        "label": "Strategy decision log",
        "keys": (
            "options_strategy_decision_log",
            "strategy_decision_log",
            "decision_log",
        ),
    },
)


def build_options_portfolio_control_report(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build a top-level options portfolio control report.

    This report aggregates existing planning, maintenance, manual action,
    outcome, edge validation, strategy improvement, and human decision artifacts.

    It is advisory and audit-focused only. It does not call brokers, route
    orders, submit orders, model fills, perform live execution, model slippage,
    close positions, roll positions, defend positions, change strategies,
    update parameters, or pause strategies automatically.
    """

    if not isinstance(source, Mapping):
        return _blocked_report("source must be a mapping")

    report_date = _string_or_none(
        source.get("report_date")
        or source.get("control_date")
        or source.get("as_of_date")
        or source.get("run_date")
    )

    sections: list[dict[str, Any]] = []
    missing_sections: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    needs_review_items: list[dict[str, Any]] = []

    for definition in SECTION_DEFINITIONS:
        artifact = _find_artifact(source, definition["keys"])
        section = _section_record(definition, artifact)
        sections.append(section)

        if report_date is None:
            report_date = _first_date_from_artifact(artifact)

        if not section["is_present"]:
            missing_sections.append(
                {
                    "section": section["section"],
                    "reason": "missing_control_report_source_artifact",
                }
            )
            continue

        if section["status"] == "blocked":
            blocked_items.append(
                {
                    "section": section["section"],
                    "reason": "source_artifact_blocked",
                    "source_status": section["status"],
                }
            )

        if section["blocked_item_count"] > 0:
            blocked_items.append(
                {
                    "section": section["section"],
                    "reason": "source_artifact_has_blocked_items",
                    "blocked_item_count": section["blocked_item_count"],
                }
            )

        if section["status"] == "needs_review":
            needs_review_items.append(
                {
                    "section": section["section"],
                    "reason": "source_artifact_needs_review",
                    "source_status": section["status"],
                }
            )

        if section["needs_review_item_count"] > 0:
            needs_review_items.append(
                {
                    "section": section["section"],
                    "reason": "source_artifact_has_needs_review_items",
                    "needs_review_item_count": section["needs_review_item_count"],
                }
            )

    if not any(section["is_present"] for section in sections):
        return _blocked_report("missing_options_portfolio_control_sources")

    control_summary = _control_summary(
        sections=sections,
        missing_sections=missing_sections,
        blocked_items=blocked_items,
        needs_review_items=needs_review_items,
    )
    operator_dashboard = _operator_dashboard(source=source, sections=sections)
    status = _status(control_summary)

    return {
        "artifact_type": "options_portfolio_control_report",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "report_date": report_date,
        "control_summary": control_summary,
        "operator_dashboard": operator_dashboard,
        "control_sections": sections,
        "missing_sections": missing_sections,
        "needs_review_items": _sorted_items(needs_review_items),
        "blocked_items": _sorted_items(blocked_items),
        "control_actions": _control_actions(
            status=status,
            control_summary=control_summary,
            operator_dashboard=operator_dashboard,
        ),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _find_artifact(source: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return value

    nested_sources = (
        source.get("artifacts"),
        source.get("source_artifacts"),
        source.get("control_sources"),
    )
    for nested in nested_sources:
        if isinstance(nested, Mapping):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, Mapping):
                    return value

    return {}


def _section_record(definition: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    if not artifact:
        return {
            "section": definition["section"],
            "label": definition["label"],
            "is_present": False,
            "artifact_type": None,
            "status": "missing",
            "is_ready": False,
            "summary": {},
            "item_count": 0,
            "blocked_item_count": 0,
            "needs_review_item_count": 0,
            "manual_action_count": 0,
        }

    summary = _source_summary(artifact)
    blocked_item_count = _blocked_item_count(artifact, summary)
    needs_review_item_count = _needs_review_item_count(artifact, summary)

    return {
        "section": definition["section"],
        "label": definition["label"],
        "is_present": True,
        "artifact_type": _string_or_none(artifact.get("artifact_type")),
        "status": _normalized(artifact.get("status")) or "needs_review",
        "is_ready": artifact.get("is_ready") is True,
        "summary": summary,
        "item_count": _item_count(artifact, summary),
        "blocked_item_count": blocked_item_count,
        "needs_review_item_count": needs_review_item_count,
        "manual_action_count": _manual_action_count(artifact, summary),
    }


def _source_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    for key in (
        "control_summary",
        "operation_summary",
        "task_summary",
        "review_summary",
        "decision_summary",
        "outcome_summary",
        "edge_summary",
        "summary",
    ):
        value = artifact.get(key)
        if isinstance(value, Mapping):
            return dict(value)

    summary: dict[str, Any] = {}

    for key in (
        "manual_decision",
        "source_review_manual_decision",
        "overall_edge_classification",
        "edge_classification",
        "review_date",
        "queue_date",
        "log_date",
        "summary_date",
    ):
        if key in artifact:
            summary[key] = artifact.get(key)

    return summary


def _item_count(artifact: Mapping[str, Any], summary: Mapping[str, Any]) -> int:
    for key in (
        "total_task_count",
        "source_task_count",
        "logged_decision_count",
        "manual_outcome_record_count",
        "closed_outcome_count",
        "review_action_count",
        "action_count",
        "candidate_count",
        "position_count",
        "trade_plan_count",
    ):
        value = _safe_int(summary.get(key), default=-1)
        if value >= 0:
            return value

    count = 0
    for key in (
        "improvement_tasks",
        "source_tasks",
        "decision_entries",
        "review_actions",
        "manual_actions",
        "action_items",
        "planned_trades",
        "positions",
        "closed_outcomes",
    ):
        value = artifact.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            count += len(value)
    return count


def _blocked_item_count(artifact: Mapping[str, Any], summary: Mapping[str, Any]) -> int:
    value = _safe_int(summary.get("blocked_item_count"), default=-1)
    if value >= 0:
        return value
    return len(_as_list(artifact.get("blocked_items")))


def _needs_review_item_count(artifact: Mapping[str, Any], summary: Mapping[str, Any]) -> int:
    for key in (
        "needs_review_item_count",
        "needs_review_count",
        "needs_review_outcome_count",
        "pending_decision_count",
        "pending_outcome_count",
        "high_priority_task_count",
        "underperforming_task_count",
        "needs_more_data_task_count",
    ):
        value = _safe_int(summary.get(key), default=-1)
        if value > 0:
            return value

    count = 0
    for key in (
        "needs_review_items",
        "pending_decisions",
        "pending_outcomes",
        "needs_review_outcomes",
    ):
        value = artifact.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            count += len(value)
    return count


def _manual_action_count(artifact: Mapping[str, Any], summary: Mapping[str, Any]) -> int:
    for key in (
        "manual_action_count",
        "review_action_count",
        "logged_decision_count",
        "total_task_count",
    ):
        value = _safe_int(summary.get(key), default=-1)
        if value >= 0:
            return value

    count = 0
    for key in (
        "manual_actions",
        "review_actions",
        "decision_entries",
        "improvement_tasks",
    ):
        value = artifact.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            count += len(value)
    return count


def _control_summary(
    *,
    sections: Sequence[Mapping[str, Any]],
    missing_sections: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
    needs_review_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    present_sections = [section for section in sections if section.get("is_present") is True]

    return {
        "section_count": len(sections),
        "present_section_count": len(present_sections),
        "missing_section_count": len(missing_sections),
        "ready_section_count": sum(1 for section in present_sections if section.get("status") == "ready"),
        "needs_review_section_count": sum(
            1 for section in present_sections if section.get("status") == "needs_review"
        ),
        "blocked_section_count": sum(
            1 for section in present_sections if section.get("status") == "blocked"
        ),
        "blocked_item_count": len(blocked_items),
        "needs_review_item_count": len(needs_review_items),
        "total_item_count": sum(_safe_int(section.get("item_count")) for section in present_sections),
        "total_manual_action_count": sum(
            _safe_int(section.get("manual_action_count")) for section in present_sections
        ),
    }


def _operator_dashboard(
    *,
    source: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    section_by_name = {section["section"]: section for section in sections}

    edge_review = _find_artifact(
        source,
        ("options_edge_validation_review", "edge_validation_review"),
    )
    strategy_review = _find_artifact(
        source,
        ("options_strategy_improvement_review", "strategy_improvement_review"),
    )
    decision_log = _find_artifact(
        source,
        ("options_strategy_decision_log", "strategy_decision_log", "decision_log"),
    )

    weekly_plan_status = section_by_name["weekly_trade_plan"]["status"]
    risk_monitor_status = section_by_name["position_risk_monitor"]["status"]
    action_queue_status = section_by_name["manual_action_queue"]["status"]
    action_review_status = section_by_name["manual_action_review"]["status"]

    return {
        "trade_plan_status": weekly_plan_status,
        "can_consider_new_trades": weekly_plan_status == "ready" and action_review_status != "blocked",
        "risk_monitor_status": risk_monitor_status,
        "needs_position_defense_review": risk_monitor_status in {"needs_review", "blocked"},
        "manual_action_queue_status": action_queue_status,
        "manual_action_review_status": action_review_status,
        "manual_actions_require_review": action_queue_status == "needs_review"
        or action_review_status == "needs_review",
        "edge_validation_status": section_by_name["edge_validation_review"]["status"],
        "overall_edge_classification": _overall_edge_classification(edge_review),
        "strategy_improvement_decision": _string_or_none(strategy_review.get("manual_decision")),
        "human_decision_logged": _decision_logged(decision_log),
        "human_decision_count": _human_decision_count(decision_log),
    }


def _overall_edge_classification(edge_review: Mapping[str, Any]) -> str | None:
    overall = edge_review.get("overall_review")
    if isinstance(overall, Mapping):
        value = _string_or_none(overall.get("edge_classification"))
        if value:
            return value

    value = _string_or_none(edge_review.get("overall_edge_classification"))
    if value:
        return value

    summary = _source_summary(edge_review)
    return _string_or_none(summary.get("overall_edge_classification"))


def _decision_logged(decision_log: Mapping[str, Any]) -> bool:
    summary = _source_summary(decision_log)
    return _safe_int(summary.get("logged_decision_count")) > 0 or bool(
        _as_list(decision_log.get("decision_entries"))
    )


def _human_decision_count(decision_log: Mapping[str, Any]) -> int:
    summary = _source_summary(decision_log)
    count = _safe_int(summary.get("logged_decision_count"), default=-1)
    if count >= 0:
        return count
    return len(_as_list(decision_log.get("decision_entries")))


def _status(control_summary: Mapping[str, Any]) -> str:
    if _safe_int(control_summary.get("blocked_item_count")) > 0:
        return "blocked"
    if _safe_int(control_summary.get("blocked_section_count")) > 0:
        return "blocked"
    if _safe_int(control_summary.get("needs_review_item_count")) > 0:
        return "needs_review"
    if _safe_int(control_summary.get("needs_review_section_count")) > 0:
        return "needs_review"
    if _safe_int(control_summary.get("missing_section_count")) > 0:
        return "needs_review"
    return "ready"


def _control_actions(
    *,
    status: str,
    control_summary: Mapping[str, Any],
    operator_dashboard: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if status == "blocked":
        return [
            {
                "action": "resolve_blocked_portfolio_control_inputs",
                "priority": "high",
                "reason": "blocked_sections_or_items_present",
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ]

    if status == "needs_review":
        actions = [
            {
                "action": "review_portfolio_control_items",
                "priority": "normal",
                "reason": "needs_review_or_missing_sections_present",
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ]

        if operator_dashboard.get("needs_position_defense_review") is True:
            actions.append(
                {
                    "action": "manually_review_position_defense_candidates",
                    "priority": "high",
                    "reason": "position_risk_monitor_requires_review",
                    "requires_manual_approval": True,
                    "order_intent": None,
                    "broker_order_id": None,
                    "automatic_action": None,
                }
            )

        if operator_dashboard.get("manual_actions_require_review") is True:
            actions.append(
                {
                    "action": "manually_review_action_queue",
                    "priority": "normal",
                    "reason": "manual_action_queue_or_review_requires_review",
                    "requires_manual_approval": True,
                    "order_intent": None,
                    "broker_order_id": None,
                    "automatic_action": None,
                }
            )

        return actions

    return [
        {
            "action": "continue_manual_portfolio_control_process",
            "priority": "normal",
            "reason": "all_present_control_sections_ready",
            "requires_manual_approval": True,
            "order_intent": None,
            "broker_order_id": None,
            "automatic_action": None,
        }
    ]


def _blocked_report(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "options_portfolio_control_report",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "report_date": None,
        "control_summary": {
            "section_count": len(SECTION_DEFINITIONS),
            "present_section_count": 0,
            "missing_section_count": len(SECTION_DEFINITIONS),
            "ready_section_count": 0,
            "needs_review_section_count": 0,
            "blocked_section_count": 0,
            "blocked_item_count": 1,
            "needs_review_item_count": 0,
            "total_item_count": 0,
            "total_manual_action_count": 0,
        },
        "operator_dashboard": {},
        "control_sections": [],
        "missing_sections": [],
        "needs_review_items": [],
        "blocked_items": [{"reason": reason}],
        "control_actions": [
            {
                "action": "resolve_blocked_portfolio_control_inputs",
                "priority": "high",
                "reason": reason,
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _first_date_from_artifact(artifact: Mapping[str, Any]) -> str | None:
    if not artifact:
        return None

    for key in (
        "report_date",
        "summary_date",
        "review_date",
        "queue_date",
        "log_date",
        "as_of_date",
    ):
        value = _string_or_none(artifact.get(key))
        if value:
            return value

    summary = _source_summary(artifact)
    for key in (
        "report_date",
        "summary_date",
        "review_date",
        "queue_date",
        "log_date",
        "as_of_date",
    ):
        value = _string_or_none(summary.get(key))
        if value:
            return value

    return None


def _sorted_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("section", "")),
            str(item.get("reason", "")),
        ),
    )


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _safe_int(value: Any, *, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")

