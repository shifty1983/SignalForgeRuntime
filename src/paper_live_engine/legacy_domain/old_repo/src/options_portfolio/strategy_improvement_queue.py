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
)

UNDEFINED_RISK_STRATEGIES = {
    "naked_short_call",
    "naked_short_put",
    "short_straddle",
    "short_strangle",
    "uncovered_ratio_spread",
    "uncovered_call",
}


def build_options_strategy_improvement_queue(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build manual research/improvement tasks from options edge validation reviews.

    This artifact is advisory only. It does not change strategies, update parameters,
    route orders, submit orders, model fills, or perform live execution.
    """

    if not isinstance(source, Mapping):
        return _blocked_queue("source must be a mapping")

    reviews = _review_records(source)
    if not reviews:
        return _blocked_queue("missing_options_edge_validation_review")

    queue_date = _string_or_none(source.get("queue_date") or source.get("review_date"))
    blocked_items: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    source_statuses: list[str] = []

    for review_index, review in enumerate(reviews):
        if not isinstance(review, Mapping):
            blocked_items.append(
                {"reason": "edge_validation_review_is_not_mapping", "review_index": review_index}
            )
            continue

        source_statuses.append(_normalized(review.get("status")))
        if queue_date is None:
            queue_date = _string_or_none(review.get("review_date"))

        if review.get("artifact_type") not in (None, "options_edge_validation_review"):
            blocked_items.append(
                {
                    "reason": "invalid_edge_validation_review_artifact_type",
                    "review_index": review_index,
                    "artifact_type": review.get("artifact_type"),
                }
            )

        if _normalized(review.get("status")) == "blocked":
            blocked_items.append(
                {"reason": "source_edge_validation_review_blocked", "review_index": review_index}
            )

        blocked_items.extend(_tag_blocked_items(review.get("blocked_items"), review_index))

        tasks.extend(_tasks_from_review_actions(review, review_index=review_index))
        tasks.extend(_tasks_from_review_sections(review, review_index=review_index))

    for task in tasks:
        strategy = _normalized(task.get("scope_value")) if task.get("scope") == "strategy" else ""
        if strategy in UNDEFINED_RISK_STRATEGIES:
            blocked_items.append(
                {
                    "reason": "undefined_risk_strategy_blocked",
                    "strategy": strategy,
                    "review_index": task.get("source_review_index"),
                }
            )

    deduped_tasks = _dedupe_tasks(tasks)
    numbered_tasks = _number_tasks(deduped_tasks)

    status = _status(
        source_statuses=source_statuses,
        tasks=numbered_tasks,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "options_strategy_improvement_queue",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "queue_date": queue_date,
        "source_review_count": len(reviews),
        "task_summary": _task_summary(numbered_tasks, blocked_items),
        "improvement_tasks": numbered_tasks,
        "blocked_items": _sorted_blocked_items(blocked_items),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _review_records(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if source.get("artifact_type") == "options_edge_validation_review":
        return [source]

    for key in (
        "options_edge_validation_reviews",
        "edge_validation_reviews",
        "reviews",
    ):
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [item for item in value if isinstance(item, Mapping)]

    value = source.get("options_edge_validation_review")
    if isinstance(value, Mapping):
        return [value]

    return []


def _tasks_from_review_actions(
    review: Mapping[str, Any], *, review_index: int
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []

    for action in _as_list(review.get("review_actions")):
        if not isinstance(action, Mapping):
            continue

        action_name = _normalized(action.get("action"))
        if action_name == "continue_tracking_supported_edge":
            continue

        scope, scope_value = _scope_from_action(action)
        edge_classification = _classification_from_action(action_name)

        tasks.append(
            _task(
                task_type=_task_type_from_action(action_name),
                scope=scope,
                scope_value=scope_value,
                edge_classification=edge_classification,
                reason=_string_or_none(action.get("reason")) or action_name,
                priority=_priority(action.get("priority"), edge_classification),
                source_review_index=review_index,
                recommended_manual_action=_manual_action_for(edge_classification, scope),
            )
        )

    return tasks


def _tasks_from_review_sections(
    review: Mapping[str, Any], *, review_index: int
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []

    overall = _as_mapping(review.get("overall_review"))
    if overall:
        tasks.extend(
            _tasks_from_review_row(
                overall,
                scope="overall",
                scope_value="overall",
                review_index=review_index,
            )
        )

    for section_key, scope, value_key in (
        ("strategy_reviews", "strategy", "strategy"),
        ("symbol_reviews", "symbol", "symbol"),
        ("setup_family_reviews", "setup_family", "setup_family"),
    ):
        for row in _as_list(review.get(section_key)):
            if isinstance(row, Mapping):
                tasks.extend(
                    _tasks_from_review_row(
                        row,
                        scope=scope,
                        scope_value=_string_or_none(row.get(value_key)) or "unknown",
                        review_index=review_index,
                    )
                )

    return tasks


def _tasks_from_review_row(
    row: Mapping[str, Any],
    *,
    scope: str,
    scope_value: str,
    review_index: int,
) -> list[dict[str, Any]]:
    edge_classification = _normalized(row.get("edge_classification"))
    if edge_classification not in {"needs_more_data", "underperforming", "blocked"}:
        return []

    if edge_classification == "needs_more_data":
        task_type = "collect_more_outcome_data"
    elif edge_classification == "underperforming":
        task_type = "review_underperforming_edge"
    else:
        task_type = "review_blocked_edge_validation_inputs"

    return [
        _task(
            task_type=task_type,
            scope=scope,
            scope_value=scope_value,
            edge_classification=edge_classification,
            reason=_string_or_none(row.get("reason")) or edge_classification,
            priority="high" if edge_classification in {"underperforming", "blocked"} else "normal",
            source_review_index=review_index,
            recommended_manual_action=_manual_action_for(edge_classification, scope),
            closed_outcome_count=_safe_int(row.get("closed_outcome_count"), default=0),
            win_rate=_float_or_none(row.get("win_rate")),
            total_realized_pnl=_float_or_none(row.get("total_realized_pnl")),
            average_return_pct=_float_or_none(row.get("average_return_pct")),
        )
    ]


def _task(
    *,
    task_type: str,
    scope: str,
    scope_value: str,
    edge_classification: str,
    reason: str,
    priority: str,
    source_review_index: int,
    recommended_manual_action: str,
    closed_outcome_count: int | None = None,
    win_rate: float | None = None,
    total_realized_pnl: float | None = None,
    average_return_pct: float | None = None,
) -> dict[str, Any]:
    return {
        "task_type": task_type,
        "scope": scope,
        "scope_value": scope_value,
        "priority": "high" if priority == "high" else "normal",
        "edge_classification": edge_classification,
        "reason": reason,
        "recommended_manual_action": recommended_manual_action,
        "source_review_index": source_review_index,
        "closed_outcome_count": closed_outcome_count,
        "win_rate": win_rate,
        "total_realized_pnl": total_realized_pnl,
        "average_return_pct": average_return_pct,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
    }


def _scope_from_action(action: Mapping[str, Any]) -> tuple[str, str]:
    for scope in ("strategy", "symbol", "setup_family"):
        value = _string_or_none(action.get(scope))
        if value:
            return scope, value
    return "overall", "overall"


def _classification_from_action(action_name: str) -> str:
    if "blocked" in action_name:
        return "blocked"
    if "underperforming" in action_name:
        return "underperforming"
    if "collect_more" in action_name or "needs_more_data" in action_name:
        return "needs_more_data"
    if "review_strategy_edge" in action_name or "review_symbol_edge" in action_name or "review_setup_family_edge" in action_name:
        return "needs_more_data"
    return "needs_more_data"


def _task_type_from_action(action_name: str) -> str:
    if "blocked" in action_name:
        return "review_blocked_edge_validation_inputs"
    if "underperforming" in action_name:
        return "review_underperforming_edge"
    if "collect_more" in action_name:
        return "collect_more_outcome_data"
    if action_name in {"review_strategy_edge", "review_symbol_edge", "review_setup_family_edge"}:
        return "review_group_edge"
    return action_name or "review_edge_validation_output"


def _priority(value: Any, edge_classification: str) -> str:
    priority = _normalized(value)
    if priority in {"high", "normal"}:
        return priority
    return "high" if edge_classification in {"underperforming", "blocked"} else "normal"


def _manual_action_for(edge_classification: str, scope: str) -> str:
    if edge_classification == "blocked":
        return "manually inspect blocked edge-validation inputs before using conclusions"
    if edge_classification == "underperforming":
        return f"manually review {scope} logic, setup filters, sizing assumptions, and exit rules"
    if edge_classification == "needs_more_data":
        return f"continue collecting {scope} outcome samples before changing strategy logic"
    return "manually review edge-validation output"


def _dedupe_tasks(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for task in tasks:
        key = (
            task.get("task_type"),
            task.get("scope"),
            task.get("scope_value"),
            task.get("edge_classification"),
            task.get("reason"),
            task.get("source_review_index"),
        )
        existing = unique.get(key)
        if existing is None:
            unique[key] = dict(task)
        elif existing.get("priority") != "high" and task.get("priority") == "high":
            unique[key] = dict(task)

    return sorted(
        unique.values(),
        key=lambda item: (
            0 if item.get("priority") == "high" else 1,
            str(item.get("scope", "")),
            str(item.get("scope_value", "")),
            str(item.get("task_type", "")),
            str(item.get("reason", "")),
        ),
    )


def _number_tasks(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"task_id": f"strategy_improvement_task_{index:03d}", **dict(task)}
        for index, task in enumerate(tasks, start=1)
    ]


def _task_summary(
    tasks: Sequence[Mapping[str, Any]], blocked_items: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "total_task_count": len(tasks),
        "high_priority_task_count": sum(1 for task in tasks if task.get("priority") == "high"),
        "normal_priority_task_count": sum(1 for task in tasks if task.get("priority") == "normal"),
        "needs_more_data_task_count": sum(
            1 for task in tasks if task.get("edge_classification") == "needs_more_data"
        ),
        "underperforming_task_count": sum(
            1 for task in tasks if task.get("edge_classification") == "underperforming"
        ),
        "blocked_task_count": sum(
            1 for task in tasks if task.get("edge_classification") == "blocked"
        ),
        "overall_task_count": sum(1 for task in tasks if task.get("scope") == "overall"),
        "strategy_task_count": sum(1 for task in tasks if task.get("scope") == "strategy"),
        "symbol_task_count": sum(1 for task in tasks if task.get("scope") == "symbol"),
        "setup_family_task_count": sum(1 for task in tasks if task.get("scope") == "setup_family"),
        "blocked_item_count": len(blocked_items),
    }


def _status(
    *,
    source_statuses: Sequence[str],
    tasks: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> str:
    if blocked_items or "blocked" in source_statuses:
        return "blocked"
    if tasks or "needs_review" in source_statuses:
        return "needs_review"
    return "ready"


def _blocked_queue(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "options_strategy_improvement_queue",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "queue_date": None,
        "source_review_count": 0,
        "task_summary": {
            "total_task_count": 1,
            "high_priority_task_count": 1,
            "normal_priority_task_count": 0,
            "needs_more_data_task_count": 0,
            "underperforming_task_count": 0,
            "blocked_task_count": 1,
            "overall_task_count": 1,
            "strategy_task_count": 0,
            "symbol_task_count": 0,
            "setup_family_task_count": 0,
            "blocked_item_count": 1,
        },
        "improvement_tasks": [
            {
                "task_id": "strategy_improvement_task_001",
                "task_type": "review_blocked_edge_validation_inputs",
                "scope": "overall",
                "scope_value": "overall",
                "priority": "high",
                "edge_classification": "blocked",
                "reason": reason,
                "recommended_manual_action": "manually inspect blocked edge-validation inputs before using conclusions",
                "source_review_index": None,
                "closed_outcome_count": None,
                "win_rate": None,
                "total_realized_pnl": None,
                "average_return_pct": None,
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ],
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _tag_blocked_items(value: Any, review_index: int) -> list[dict[str, Any]]:
    return [
        {**dict(item), "review_index": review_index}
        for item in _as_list(value)
        if isinstance(item, Mapping)
    ]


def _sorted_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("review_index", "")),
            str(item.get("strategy", "")),
            str(item.get("symbol", "")),
            str(item.get("reason", "")),
        ),
    )


def _safe_int(value: Any, *, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")

