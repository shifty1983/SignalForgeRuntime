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

VALID_HUMAN_DECISIONS = {
    "continue_tracking",
    "research_required",
    "pause_candidate_reviewed",
    "strategy_change_deferred",
    "blocked",
}


def build_options_strategy_decision_log(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build a manual options strategy decision log.

    This artifact records human decisions after strategy improvement review. It
    never calls broker APIs, routes orders, submits orders, models fills,
    performs live execution, models slippage, changes strategies automatically,
    updates parameters automatically, or pauses strategies automatically.
    """

    if not isinstance(source, Mapping):
        return _blocked_log("source must be a mapping")

    review = _review_record(source)
    if not review:
        return _blocked_log("missing_options_strategy_improvement_review")

    log_date = _string_or_none(
        source.get("log_date")
        or source.get("decision_date")
        or source.get("review_date")
        or review.get("review_date")
    )

    blocked_items: list[dict[str, Any]] = []
    decision_entries: list[dict[str, Any]] = []
    pending_decisions: list[dict[str, Any]] = []

    if review.get("artifact_type") not in (None, "options_strategy_improvement_review"):
        blocked_items.append(
            {
                "reason": "invalid_strategy_improvement_review_artifact_type",
                "artifact_type": review.get("artifact_type"),
            }
        )

    if _normalized(review.get("status")) == "blocked":
        blocked_items.append({"reason": "source_strategy_improvement_review_blocked"})

    blocked_items.extend(_tag_review_blocked_items(review.get("blocked_items")))

    human_decisions = _human_decision_records(source)

    if not human_decisions and not blocked_items:
        pending_decisions.append(_pending_decision_from_review(review))

    for index, human_decision in enumerate(human_decisions, start=1):
        if not isinstance(human_decision, Mapping):
            blocked_items.append(
                {"reason": "human_decision_record_is_not_mapping", "decision_index": index}
            )
            continue

        decision = _normalized(human_decision.get("decision"))
        if decision not in VALID_HUMAN_DECISIONS:
            blocked_items.append(
                {
                    "reason": "invalid_human_strategy_decision",
                    "decision_index": index,
                    "decision": human_decision.get("decision"),
                }
            )
            continue

        if _contains_non_null_key(
            human_decision,
            "order_intent",
            "broker_order_id",
            "automatic_action",
            "automatic_strategy_change",
            "automatic_parameter_change",
            "automatic_pause_action",
            "strategy_change",
            "parameter_change",
            "pause_action",
        ):
            blocked_items.append(
                {
                    "reason": "human_decision_contains_automatic_or_order_action",
                    "decision_index": index,
                    "decision": decision,
                }
            )
            continue

        decision_entries.append(
            _decision_entry(
                human_decision=human_decision,
                review=review,
                decision=decision,
                index=index,
                log_date=log_date,
            )
        )

    status = _status(
        blocked_items=blocked_items,
        pending_decisions=pending_decisions,
    )

    return {
        "artifact_type": "options_strategy_decision_log",
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
        "log_date": log_date,
        "source_review_status": _normalized(review.get("status")),
        "source_review_manual_decision": _normalized(review.get("manual_decision")),
        "decision_summary": _decision_summary(
            decision_entries=decision_entries,
            pending_decisions=pending_decisions,
            blocked_items=blocked_items,
        ),
        "decision_entries": _sorted_decision_entries(decision_entries),
        "pending_decisions": pending_decisions,
        "blocked_items": _sorted_blocked_items(blocked_items),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _review_record(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if source.get("artifact_type") == "options_strategy_improvement_review":
        return source

    for key in (
        "options_strategy_improvement_review",
        "strategy_improvement_review",
        "improvement_review",
        "review",
    ):
        value = source.get(key)
        if isinstance(value, Mapping):
            return value

    return {}


def _human_decision_records(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in (
        "human_decisions",
        "manual_decisions",
        "strategy_decisions",
        "decisions",
    ):
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [item for item in value if isinstance(item, Mapping)]

    for key in (
        "human_decision",
        "manual_decision_record",
        "strategy_decision",
        "decision_record",
    ):
        value = source.get(key)
        if isinstance(value, Mapping):
            return [value]

    if source.get("decision") is not None:
        return [
            {
                "decision": source.get("decision"),
                "reason": source.get("decision_reason") or source.get("reason"),
                "decision_scope": source.get("decision_scope") or source.get("scope"),
                "decision_scope_value": source.get("decision_scope_value")
                or source.get("scope_value"),
                "affected_task_ids": source.get("affected_task_ids"),
                "approver": source.get("approver"),
            }
        ]

    return []


def _pending_decision_from_review(review: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pending_reason": "missing_human_strategy_decision",
        "source_review_manual_decision": _normalized(review.get("manual_decision")),
        "source_review_status": _normalized(review.get("status")),
        "affected_task_ids": _affected_task_ids_from_review(review),
        "requires_manual_approval": True,
    }


def _decision_entry(
    *,
    human_decision: Mapping[str, Any],
    review: Mapping[str, Any],
    decision: str,
    index: int,
    log_date: str | None,
) -> dict[str, Any]:
    return {
        "decision_log_entry_id": _string_or_none(human_decision.get("decision_log_entry_id"))
        or f"strategy_decision_log_entry_{index:03d}",
        "decision_id": _string_or_none(human_decision.get("decision_id"))
        or f"strategy_decision_{index:03d}",
        "decision": decision,
        "decision_date": _string_or_none(human_decision.get("decision_date")) or log_date,
        "decision_scope": _decision_scope(human_decision),
        "decision_scope_value": _decision_scope_value(human_decision),
        "reason": _string_or_none(human_decision.get("reason")) or _reason_for_decision(decision),
        "approver": _string_or_none(human_decision.get("approver")) or "manual_review",
        "source_review_manual_decision": _normalized(review.get("manual_decision")),
        "source_review_status": _normalized(review.get("status")),
        "affected_task_ids": _affected_task_ids(human_decision, review),
        "manual_notes": _string_or_none(human_decision.get("manual_notes")),
        "recommended_next_manual_step": _next_manual_step(decision),
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }


def _decision_scope(human_decision: Mapping[str, Any]) -> str:
    value = _normalized(
        human_decision.get("decision_scope")
        or human_decision.get("scope")
        or human_decision.get("task_scope")
    )
    return value or "overall"


def _decision_scope_value(human_decision: Mapping[str, Any]) -> str:
    value = _string_or_none(
        human_decision.get("decision_scope_value")
        or human_decision.get("scope_value")
        or human_decision.get("task_scope_value")
    )
    return value or "overall"


def _affected_task_ids(
    human_decision: Mapping[str, Any],
    review: Mapping[str, Any],
) -> list[str]:
    explicit = _as_list(human_decision.get("affected_task_ids"))
    if explicit:
        return sorted(str(item) for item in explicit if _string_or_none(item))
    return _affected_task_ids_from_review(review)


def _affected_task_ids_from_review(review: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []

    for action in _as_list(review.get("review_actions")):
        if isinstance(action, Mapping):
            ids.extend(str(item) for item in _as_list(action.get("affected_task_ids")))

    for task in _as_list(review.get("source_tasks")):
        if isinstance(task, Mapping):
            task_id = _string_or_none(task.get("task_id"))
            if task_id:
                ids.append(task_id)

    return sorted(set(ids))


def _reason_for_decision(decision: str) -> str:
    if decision == "continue_tracking":
        return "human_decision_to_continue_tracking"
    if decision == "research_required":
        return "human_decision_requires_research_before_strategy_changes"
    if decision == "pause_candidate_reviewed":
        return "human_review_completed_for_pause_candidate"
    if decision == "strategy_change_deferred":
        return "human_decision_deferred_strategy_change"
    return "human_decision_blocked"


def _next_manual_step(decision: str) -> str:
    if decision == "continue_tracking":
        return "continue tracking outcomes without changing strategy logic"
    if decision == "research_required":
        return "complete manual research before changing strategy logic"
    if decision == "pause_candidate_reviewed":
        return "document manual pause-candidate conclusion outside automated execution"
    if decision == "strategy_change_deferred":
        return "defer strategy changes and keep collecting validation evidence"
    return "resolve blocked decision inputs manually"


def _decision_summary(
    *,
    decision_entries: Sequence[Mapping[str, Any]],
    pending_decisions: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "logged_decision_count": len(decision_entries),
        "pending_decision_count": len(pending_decisions),
        "continue_tracking_count": _count_decision(decision_entries, "continue_tracking"),
        "research_required_count": _count_decision(decision_entries, "research_required"),
        "pause_candidate_reviewed_count": _count_decision(
            decision_entries, "pause_candidate_reviewed"
        ),
        "strategy_change_deferred_count": _count_decision(
            decision_entries, "strategy_change_deferred"
        ),
        "blocked_decision_count": _count_decision(decision_entries, "blocked"),
        "blocked_item_count": len(blocked_items),
    }


def _count_decision(entries: Sequence[Mapping[str, Any]], decision: str) -> int:
    return sum(1 for entry in entries if entry.get("decision") == decision)


def _status(
    *,
    blocked_items: Sequence[Mapping[str, Any]],
    pending_decisions: Sequence[Mapping[str, Any]],
) -> str:
    if blocked_items:
        return "blocked"
    if pending_decisions:
        return "needs_review"
    return "ready"


def _tag_review_blocked_items(value: Any) -> list[dict[str, Any]]:
    return [
        {**dict(item), "source": "options_strategy_improvement_review"}
        for item in _as_list(value)
        if isinstance(item, Mapping)
    ]


def _sorted_decision_entries(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(entry) for entry in entries],
        key=lambda item: (
            str(item.get("decision_date", "")),
            str(item.get("decision_scope", "")),
            str(item.get("decision_scope_value", "")),
            str(item.get("decision_id", "")),
        ),
    )


def _sorted_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("source", "")),
            str(item.get("decision_index", "")),
            str(item.get("reason", "")),
        ),
    )


def _blocked_log(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "options_strategy_decision_log",
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
        "log_date": None,
        "source_review_status": None,
        "source_review_manual_decision": None,
        "decision_summary": {
            "logged_decision_count": 0,
            "pending_decision_count": 0,
            "continue_tracking_count": 0,
            "research_required_count": 0,
            "pause_candidate_reviewed_count": 0,
            "strategy_change_deferred_count": 0,
            "blocked_decision_count": 0,
            "blocked_item_count": 1,
        },
        "decision_entries": [],
        "pending_decisions": [],
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value.get(key) is not None:
                return True
        return any(_contains_non_null_key(item, *keys) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_null_key(item, *keys) for item in value)
    return False


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

