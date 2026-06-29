from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from src.options_strategy.catalog import is_defined_risk_strategy


EXPLICIT_EXCLUSIONS: tuple[str, ...] = (
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
)

COMPLETED_STATUSES = {
    "complete",
    "completed",
    "completed_manually",
    "executed",
    "executed_manually",
    "manual_execution_completed",
    "done",
}
SKIPPED_STATUSES = {"skip", "skipped", "not_taken", "no_action", "cancel", "canceled", "cancelled"}
DEFERRED_STATUSES = {"defer", "deferred", "wait", "waiting"}
PENDING_STATUSES = {"pending", "pending_execution", "not_yet_done"}
REVIEW_STATUSES = {"needs_review", "review", "needs_more_info"}
BLOCKED_STATUSES = {"block", "blocked"}


def build_options_manual_execution_record(source: Mapping[str, Any]) -> dict[str, Any]:
    """Record what happened after approved manual options actions.

    The artifact records manual handling outcomes only. It never creates order
    intents, routes orders, calls broker APIs, syncs broker order state, models
    fills, performs live execution, or creates automatic close/roll/defense
    orders.
    """

    if not isinstance(source, Mapping):
        return _blocked_result(reason="source must be a mapping")

    review = _mapping(source.get("options_manual_action_review") or source.get("manual_action_review"))
    if not review:
        return _blocked_result(
            execution_recorded_at=_string_or_none(source.get("execution_recorded_at")),
            reason="missing_options_manual_action_review",
        )

    execution_recorded_at = _string_or_none(
        source.get("execution_recorded_at")
        or source.get("recorded_at")
        or source.get("reviewed_at")
    )
    recorder = _string_or_none(source.get("recorder") or source.get("reviewer"))

    approved_actions = _list_of_mappings(review.get("approved_actions"))
    execution_records = _execution_records(source.get("manual_execution_records") or source.get("execution_records"))

    completed_manual_actions: list[dict[str, Any]] = []
    skipped_manual_actions: list[dict[str, Any]] = []
    deferred_manual_actions: list[dict[str, Any]] = []
    pending_manual_actions: list[dict[str, Any]] = []
    needs_review_actions: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    used_execution_indexes: set[int] = set()

    for approved_index, action in enumerate(approved_actions):
        keyed_action = _with_action_key(action, approved_index=approved_index)
        strategy = _string_or_none(keyed_action.get("strategy"))

        if strategy and not is_defined_risk_strategy(strategy):
            blocked_items.append(
                _blocked_item(
                    keyed_action,
                    reason="undefined_risk_strategy_blocked",
                    recorder=recorder,
                    execution_recorded_at=execution_recorded_at,
                )
            )
            continue

        matched_index, execution_record = _find_execution_record(keyed_action, execution_records)
        if matched_index is not None:
            used_execution_indexes.add(matched_index)

        if execution_record is None:
            pending_manual_actions.append(
                _manual_execution_item(
                    keyed_action,
                    recorder=recorder,
                    execution_recorded_at=execution_recorded_at,
                    execution_status="pending_manual_execution",
                    execution_note="no manual execution record provided",
                )
            )
            continue

        normalized_status = _normalize_status(
            execution_record.get("execution_status")
            or execution_record.get("status")
            or execution_record.get("decision")
        )
        execution_note = _string_or_none(
            execution_record.get("note")
            or execution_record.get("comment")
            or execution_record.get("reason")
        )

        execution_item = _manual_execution_item(
            keyed_action,
            recorder=recorder,
            execution_recorded_at=execution_recorded_at,
            execution_status=normalized_status,
            execution_note=execution_note,
            manual_execution_reference=_string_or_none(
                execution_record.get("manual_execution_reference")
                or execution_record.get("external_reference")
                or execution_record.get("reference")
            ),
        )

        if normalized_status in COMPLETED_STATUSES:
            completed_manual_actions.append(
                {
                    **execution_item,
                    "execution_status": "completed_manually_outside_system",
                    "executed_outside_system": True,
                    "manual_confirmation": _bool_or_default(
                        execution_record.get("manual_confirmation")
                        or execution_record.get("confirmed"),
                        default=True,
                    ),
                    "order_intent": None,
                    "broker_order_id": None,
                    "automatic_action": None,
                }
            )
        elif normalized_status in SKIPPED_STATUSES:
            skipped_manual_actions.append({**execution_item, "execution_status": "skipped_manual_action"})
        elif normalized_status in DEFERRED_STATUSES:
            deferred_manual_actions.append({**execution_item, "execution_status": "deferred_manual_execution"})
        elif normalized_status in PENDING_STATUSES:
            pending_manual_actions.append({**execution_item, "execution_status": "pending_manual_execution"})
        elif normalized_status in BLOCKED_STATUSES:
            blocked_items.append(
                _blocked_item(
                    keyed_action,
                    reason=execution_note or "manual_execution_blocked",
                    recorder=recorder,
                    execution_recorded_at=execution_recorded_at,
                )
            )
        else:
            needs_review_actions.append({**execution_item, "execution_status": "needs_review"})

    for execution_index, execution_record in enumerate(execution_records):
        if execution_index in used_execution_indexes:
            continue
        blocked_items.append(
            {
                "reason": "unmatched_manual_execution_record",
                "execution_record_index": execution_index,
                "action_key": _string_or_none(execution_record.get("action_key") or execution_record.get("action_id")),
                "queue_index": execution_record.get("queue_index"),
                "approved_index": execution_record.get("approved_index"),
                "recorder": recorder,
                "execution_recorded_at": execution_recorded_at,
            }
        )

    source_blocked_items = [
        _blocked_item(item, reason=_string_or_none(item.get("reason")) or "source_blocked_item")
        for item in _list_of_mappings(review.get("blocked_items"))
    ]
    blocked_items.extend(source_blocked_items)

    status = _status(
        review_status=_string_or_none(review.get("status")),
        approved_actions=approved_actions,
        completed_manual_actions=completed_manual_actions,
        skipped_manual_actions=skipped_manual_actions,
        deferred_manual_actions=deferred_manual_actions,
        pending_manual_actions=pending_manual_actions,
        needs_review_actions=needs_review_actions,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "options_manual_execution_record",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "queue_date": _string_or_none(source.get("queue_date") or review.get("queue_date")),
        "reviewed_at": _string_or_none(source.get("reviewed_at") or review.get("reviewed_at")),
        "execution_recorded_at": execution_recorded_at,
        "recorder": recorder,
        "completed_manual_actions": _sort_execution_items(completed_manual_actions),
        "skipped_manual_actions": _sort_execution_items(skipped_manual_actions),
        "deferred_manual_actions": _sort_execution_items(deferred_manual_actions),
        "pending_manual_actions": _sort_execution_items(pending_manual_actions),
        "needs_review_actions": _sort_execution_items(needs_review_actions),
        "blocked_items": _sort_blocked_items(blocked_items),
        "execution_summary": {
            "source_approved_action_count": len(approved_actions),
            "manual_execution_record_count": len(execution_records),
            "completed_manual_action_count": len(completed_manual_actions),
            "skipped_manual_action_count": len(skipped_manual_actions),
            "deferred_manual_action_count": len(deferred_manual_actions),
            "pending_manual_action_count": len(pending_manual_actions),
            "needs_review_action_count": len(needs_review_actions),
            "blocked_item_count": len(blocked_items),
        },
        "source_review_summary": {
            "artifact_type": _string_or_none(review.get("artifact_type")),
            "status": _string_or_none(review.get("status")),
            "approved_action_count": len(approved_actions),
            "rejected_action_count": len(_list_of_mappings(review.get("rejected_actions"))),
            "deferred_action_count": len(_list_of_mappings(review.get("deferred_actions"))),
            "pending_action_count": len(_list_of_mappings(review.get("pending_actions"))),
            "blocked_item_count": len(_list_of_mappings(review.get("blocked_items"))),
        },
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def make_manual_execution_action_key(action: Mapping[str, Any], *, approved_index: int | None = None) -> str:
    if not isinstance(action, Mapping):
        return "manual_execution_action_invalid"

    existing = _string_or_none(action.get("action_key") or action.get("action_id") or action.get("id"))
    if existing:
        return existing

    parts = [
        _string_or_none(action.get("action_source")) or "",
        _string_or_none(action.get("action_type")) or "",
        _string_or_none(action.get("symbol")) or "",
        _string_or_none(action.get("position_id")) or "",
        _string_or_none(action.get("strategy")) or "",
        _string_or_none(action.get("action")) or "",
    ]
    if approved_index is not None:
        parts.append(str(approved_index))

    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"manual_execution_action_{digest}"


def _with_action_key(action: Mapping[str, Any], *, approved_index: int) -> dict[str, Any]:
    result = dict(action)
    result["action_key"] = make_manual_execution_action_key(action, approved_index=approved_index)
    result["approved_index"] = approved_index
    return result


def _execution_records(records: Any) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for index, record in enumerate(_list_of_mappings(records)):
        result = dict(record)
        result["_execution_record_index"] = index
        indexed.append(result)
    return indexed


def _find_execution_record(
    action: Mapping[str, Any],
    execution_records: Sequence[Mapping[str, Any]],
) -> tuple[int | None, Mapping[str, Any] | None]:
    action_key = _string_or_none(action.get("action_key"))
    queue_index = action.get("queue_index")
    approved_index = action.get("approved_index")

    for index, record in enumerate(execution_records):
        record_key = _string_or_none(record.get("action_key") or record.get("action_id"))
        if action_key and record_key and action_key == record_key:
            return index, record

        if approved_index is not None and record.get("approved_index") == approved_index:
            return index, record

        if queue_index is not None and record.get("queue_index") == queue_index:
            return index, record

    return None, None


def _manual_execution_item(
    action: Mapping[str, Any],
    *,
    recorder: str | None,
    execution_recorded_at: str | None,
    execution_status: str,
    execution_note: str | None = None,
    manual_execution_reference: str | None = None,
) -> dict[str, Any]:
    return {
        "action_key": _string_or_none(action.get("action_key")),
        "approved_index": action.get("approved_index"),
        "queue_index": action.get("queue_index"),
        "action_source": _string_or_none(action.get("action_source")),
        "action_type": _string_or_none(action.get("action_type")),
        "symbol": _string_or_none(action.get("symbol")),
        "position_id": _string_or_none(action.get("position_id")),
        "strategy": _string_or_none(action.get("strategy")),
        "action": _string_or_none(action.get("action")),
        "urgency": _string_or_none(action.get("urgency")),
        "priority_rank": _int_or_none(action.get("priority_rank") or action.get("priority")),
        "execution_status": execution_status,
        "execution_note": execution_note,
        "manual_execution_reference": manual_execution_reference,
        "recorder": recorder,
        "execution_recorded_at": execution_recorded_at,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
    }


def _blocked_result(
    *,
    reason: str,
    queue_date: str | None = None,
    reviewed_at: str | None = None,
    execution_recorded_at: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "options_manual_execution_record",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "queue_date": queue_date,
        "reviewed_at": reviewed_at,
        "execution_recorded_at": execution_recorded_at,
        "recorder": None,
        "completed_manual_actions": [],
        "skipped_manual_actions": [],
        "deferred_manual_actions": [],
        "pending_manual_actions": [],
        "needs_review_actions": [],
        "blocked_items": [{"reason": reason}],
        "execution_summary": {
            "source_approved_action_count": 0,
            "manual_execution_record_count": 0,
            "completed_manual_action_count": 0,
            "skipped_manual_action_count": 0,
            "deferred_manual_action_count": 0,
            "pending_manual_action_count": 0,
            "needs_review_action_count": 0,
            "blocked_item_count": 1,
        },
        "source_review_summary": {},
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_item(
    item: Mapping[str, Any],
    *,
    reason: str,
    recorder: str | None = None,
    execution_recorded_at: str | None = None,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "action_key": _string_or_none(item.get("action_key") or item.get("action_id")),
        "approved_index": item.get("approved_index"),
        "queue_index": item.get("queue_index"),
        "symbol": _string_or_none(item.get("symbol")),
        "position_id": _string_or_none(item.get("position_id")),
        "strategy": _string_or_none(item.get("strategy")),
        "action": _string_or_none(item.get("action")),
        "recorder": recorder,
        "execution_recorded_at": execution_recorded_at,
    }


def _status(
    *,
    review_status: str | None,
    approved_actions: Sequence[Mapping[str, Any]],
    completed_manual_actions: Sequence[Mapping[str, Any]],
    skipped_manual_actions: Sequence[Mapping[str, Any]],
    deferred_manual_actions: Sequence[Mapping[str, Any]],
    pending_manual_actions: Sequence[Mapping[str, Any]],
    needs_review_actions: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> str:
    if blocked_items or review_status == "blocked":
        return "blocked"
    if not approved_actions:
        return "needs_review"
    if pending_manual_actions or needs_review_actions:
        return "needs_review"
    if completed_manual_actions or skipped_manual_actions or deferred_manual_actions:
        return "ready"
    return "needs_review"


def _sort_execution_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(item) for item in items),
        key=lambda item: (
            _int_sort_key(item.get("approved_index")),
            _int_sort_key(item.get("queue_index")),
            _string_or_none(item.get("symbol")) or "",
            _string_or_none(item.get("action_key")) or "",
        ),
    )


def _sort_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(item) for item in items),
        key=lambda item: (
            _string_or_none(item.get("reason")) or "",
            _int_sort_key(item.get("approved_index")),
            _int_sort_key(item.get("queue_index")),
            _string_or_none(item.get("action_key")) or "",
        ),
    )


def _normalize_status(value: Any) -> str:
    raw = _string_or_none(value)
    if not raw:
        return "needs_review"
    return raw.strip().lower().replace(" ", "_").replace("-", "_")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_sort_key(value: Any) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 999_999


def _bool_or_default(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "y"}:
            return True
        if normalized in {"false", "no", "0", "n"}:
            return False
    return bool(value)

