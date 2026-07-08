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


def build_options_strategy_improvement_review(source: Mapping[str, Any]) -> dict[str, Any]:
    """Review options strategy improvement queue outputs.

    This artifact creates a manual review decision only. It does not change
    strategy logic, pause strategies, update parameters, route orders, submit
    orders, model fills, perform live execution, or model slippage.
    """

    if not isinstance(source, Mapping):
        return _blocked_review("source must be a mapping")

    queues = _queue_records(source)
    if not queues:
        return _blocked_review("missing_options_strategy_improvement_queue")

    review_date = _string_or_none(
        source.get("review_date") or source.get("queue_date") or source.get("as_of_date")
    )
    blocked_items: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    source_statuses: list[str] = []

    for queue_index, queue in enumerate(queues):
        if not isinstance(queue, Mapping):
            blocked_items.append(
                {"reason": "strategy_improvement_queue_is_not_mapping", "queue_index": queue_index}
            )
            continue

        if review_date is None:
            review_date = _string_or_none(queue.get("queue_date"))

        source_status = _normalized(queue.get("status"))
        source_statuses.append(source_status)

        if queue.get("artifact_type") not in (None, "options_strategy_improvement_queue"):
            blocked_items.append(
                {
                    "reason": "invalid_strategy_improvement_queue_artifact_type",
                    "queue_index": queue_index,
                    "artifact_type": queue.get("artifact_type"),
                }
            )

        if source_status == "blocked":
            blocked_items.append(
                {"reason": "source_strategy_improvement_queue_blocked", "queue_index": queue_index}
            )

        blocked_items.extend(_tag_blocked_items(queue.get("blocked_items"), queue_index))

        for task in _as_list(queue.get("improvement_tasks")):
            if isinstance(task, Mapping):
                tasks.append({**dict(task), "source_queue_index": queue_index})

    manual_decision = _manual_decision(
        source_statuses=source_statuses,
        tasks=tasks,
        blocked_items=blocked_items,
    )
    status = _status_from_decision(manual_decision)
    review_summary = _review_summary(tasks=tasks, blocked_items=blocked_items)
    review_actions = _review_actions(
        manual_decision=manual_decision,
        tasks=tasks,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "options_strategy_improvement_review",
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
        "review_date": review_date,
        "source_queue_count": len(queues),
        "manual_decision": manual_decision,
        "decision_reason": _decision_reason(manual_decision, review_summary),
        "review_summary": review_summary,
        "review_actions": review_actions,
        "source_tasks": _sorted_tasks(tasks),
        "blocked_items": _sorted_blocked_items(blocked_items),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _queue_records(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if source.get("artifact_type") == "options_strategy_improvement_queue":
        return [source]

    for key in (
        "options_strategy_improvement_queues",
        "strategy_improvement_queues",
        "improvement_queues",
        "queues",
    ):
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [item for item in value if isinstance(item, Mapping)]

    value = source.get("options_strategy_improvement_queue")
    if isinstance(value, Mapping):
        return [value]

    value = source.get("strategy_improvement_queue")
    if isinstance(value, Mapping):
        return [value]

    return []


def _manual_decision(
    *,
    source_statuses: Sequence[str],
    tasks: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> str:
    if blocked_items or "blocked" in source_statuses:
        return "blocked"

    if any(_normalized(task.get("edge_classification")) == "blocked" for task in tasks):
        return "blocked"

    if any(_normalized(task.get("edge_classification")) == "underperforming" for task in tasks):
        return "pause_candidate"

    if tasks or "needs_review" in source_statuses:
        return "research_required"

    return "continue_tracking"


def _status_from_decision(manual_decision: str) -> str:
    if manual_decision == "blocked":
        return "blocked"
    if manual_decision in {"research_required", "pause_candidate"}:
        return "needs_review"
    return "ready"


def _decision_reason(manual_decision: str, review_summary: Mapping[str, Any]) -> str:
    if manual_decision == "blocked":
        return "blocked_strategy_improvement_inputs_require_manual_resolution"
    if manual_decision == "pause_candidate":
        return "underperforming_edge_tasks_require_manual_pause_candidate_review"
    if manual_decision == "research_required":
        return "improvement_tasks_require_manual_research_before_strategy_changes"
    return "no_improvement_tasks_detected_continue_tracking"


def _review_summary(
    *,
    tasks: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "source_task_count": len(tasks),
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


def _review_actions(
    *,
    manual_decision: str,
    tasks: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if manual_decision == "continue_tracking":
        return [
            {
                "action": "continue_tracking",
                "priority": "normal",
                "reason": "no_improvement_tasks_detected",
                "affected_task_ids": [],
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ]

    if manual_decision == "research_required":
        return [
            {
                "action": "complete_manual_research_before_strategy_changes",
                "priority": "normal",
                "reason": "needs_more_data_or_research_tasks_present",
                "affected_task_ids": _task_ids(tasks),
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ]

    if manual_decision == "pause_candidate":
        return [
            {
                "action": "manually_review_pause_candidate",
                "priority": "high",
                "reason": "underperforming_edge_tasks_present",
                "affected_task_ids": _task_ids(tasks),
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ]

    return [
        {
            "action": "resolve_blocked_strategy_improvement_review",
            "priority": "high",
            "reason": "blocked_items_present",
            "affected_task_ids": _task_ids(tasks),
            "blocked_item_count": len(blocked_items),
            "requires_manual_approval": True,
            "order_intent": None,
            "broker_order_id": None,
            "automatic_action": None,
        }
    ]


def _task_ids(tasks: Sequence[Mapping[str, Any]]) -> list[str]:
    ids = [_string_or_none(task.get("task_id")) for task in tasks]
    return sorted(item for item in ids if item)


def _sorted_tasks(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(task) for task in tasks],
        key=lambda item: (
            0 if item.get("priority") == "high" else 1,
            str(item.get("scope", "")),
            str(item.get("scope_value", "")),
            str(item.get("task_id", "")),
        ),
    )


def _tag_blocked_items(value: Any, queue_index: int) -> list[dict[str, Any]]:
    return [
        {**dict(item), "queue_index": queue_index}
        for item in _as_list(value)
        if isinstance(item, Mapping)
    ]


def _sorted_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("queue_index", "")),
            str(item.get("task_id", "")),
            str(item.get("reason", "")),
        ),
    )


def _blocked_review(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "options_strategy_improvement_review",
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
        "review_date": None,
        "source_queue_count": 0,
        "manual_decision": "blocked",
        "decision_reason": "blocked_strategy_improvement_inputs_require_manual_resolution",
        "review_summary": {
            "source_task_count": 0,
            "high_priority_task_count": 0,
            "normal_priority_task_count": 0,
            "needs_more_data_task_count": 0,
            "underperforming_task_count": 0,
            "blocked_task_count": 0,
            "overall_task_count": 0,
            "strategy_task_count": 0,
            "symbol_task_count": 0,
            "setup_family_task_count": 0,
            "blocked_item_count": 1,
        },
        "review_actions": [
            {
                "action": "resolve_blocked_strategy_improvement_review",
                "priority": "high",
                "reason": reason,
                "affected_task_ids": [],
                "blocked_item_count": 1,
                "requires_manual_approval": True,
                "order_intent": None,
                "broker_order_id": None,
                "automatic_action": None,
            }
        ],
        "source_tasks": [],
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")

