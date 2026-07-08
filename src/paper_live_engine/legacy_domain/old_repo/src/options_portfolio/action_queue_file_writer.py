from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.options_portfolio.action_queue_operation import (
    run_options_manual_action_queue_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_manual_action_queue_files.v1"
OPERATION_TYPE = "options_manual_action_queue_file_writer"

DEFAULT_FILENAMES = {
    "options_manual_action_queue": "options_manual_action_queue.json",
    "operation_result": "options_manual_action_queue_operation.json",
    "audit_report": "options_manual_action_queue_audit.json",
    "health_report": "options_manual_action_queue_health.json",
    "events": "options_manual_action_queue_events.json",
    "event_log": "options_manual_action_queue_operation.jsonl",
}


def write_options_manual_action_queue_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    queue_date: str | None = None,
    evaluation_timestamp: str | None = None,
    max_priority_actions: int | None = None,
    max_new_trade_actions: int | None = None,
    max_defense_actions: int | None = None,
    include_monitor_items: bool | None = None,
) -> dict[str, Any]:
    """Write options manual action-queue artifacts to local files.

    The writer creates review artifacts only. It does not call broker APIs,
    route orders, submit orders, model fills, perform live execution, model
    slippage, or create automatic close/roll/defense orders.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(
        source,
        queue_date=queue_date,
        evaluation_timestamp=evaluation_timestamp,
        max_priority_actions=max_priority_actions,
        max_new_trade_actions=max_new_trade_actions,
        max_defense_actions=max_defense_actions,
        include_monitor_items=include_monitor_items,
    )

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_manual_action_queue_operation(
        source_args["operation_source"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    action_queue = _as_mapping(operation_result.get("options_manual_action_queue"))
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "options_manual_action_queue": output_path
        / DEFAULT_FILENAMES["options_manual_action_queue"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["options_manual_action_queue"], action_queue)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["events"], events)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "source_summary": _build_source_summary(source_args["operation_source"]),
        "operation_result": operation_result,
        "explicit_exclusions": list(operation_result.get("explicit_exclusions", [])),
    }


def _extract_source_args(
    source: Any,
    *,
    queue_date: str | None,
    evaluation_timestamp: str | None,
    max_priority_actions: int | None,
    max_new_trade_actions: int | None,
    max_defense_actions: int | None,
    include_monitor_items: bool | None,
) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {"operation_source": source, "metadata": {}}

    operation_source = dict(source)

    weekly_plan = _extract_first_mapping(
        source,
        "weekly_option_trade_plan",
        "weekly_trade_plan",
        "weekly_plan",
        "trade_plan",
    )
    if weekly_plan is not None:
        operation_source["weekly_option_trade_plan"] = weekly_plan

    defense_review = _extract_first_mapping(
        source,
        "options_strategy_defense_review",
        "strategy_defense_review",
        "defense_review",
    )
    if defense_review is not None:
        operation_source["options_strategy_defense_review"] = defense_review

    risk_monitor = _extract_first_mapping(
        source,
        "options_position_risk_monitor",
        "position_risk_monitor",
        "risk_monitor",
    )
    if risk_monitor is not None:
        operation_source["options_position_risk_monitor"] = risk_monitor

    selected_queue_date = _string_or_none(queue_date) or _string_or_none(
        source.get("queue_date") or source.get("plan_date")
    )
    if selected_queue_date is not None:
        operation_source["queue_date"] = selected_queue_date

    selected_evaluation_timestamp = _string_or_none(evaluation_timestamp) or _string_or_none(
        source.get("evaluation_timestamp")
    )
    if selected_evaluation_timestamp is not None:
        operation_source["evaluation_timestamp"] = selected_evaluation_timestamp

    selected_max_priority_actions = _optional_non_negative_int(
        max_priority_actions,
        fallback=source.get("max_priority_actions"),
    )
    if selected_max_priority_actions is not None:
        operation_source["max_priority_actions"] = selected_max_priority_actions

    selected_max_new_trade_actions = _optional_non_negative_int(
        max_new_trade_actions,
        fallback=source.get("max_new_trade_actions"),
    )
    if selected_max_new_trade_actions is not None:
        operation_source["max_new_trade_actions"] = selected_max_new_trade_actions

    selected_max_defense_actions = _optional_non_negative_int(
        max_defense_actions,
        fallback=source.get("max_defense_actions"),
    )
    if selected_max_defense_actions is not None:
        operation_source["max_defense_actions"] = selected_max_defense_actions

    if include_monitor_items is not None:
        operation_source["include_monitor_items"] = bool(include_monitor_items)
    elif "include_monitor_items" in source:
        operation_source["include_monitor_items"] = bool(source.get("include_monitor_items"))

    return {
        "operation_source": operation_source,
        "metadata": _metadata(source.get("metadata")),
    }


def _extract_first_mapping(source: Mapping[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return None


def _metadata(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_non_negative_int(value: Any, *, fallback: Any) -> int | None:
    selected = value if value is not None else fallback
    if selected is None:
        return None
    try:
        integer = int(selected)
    except (TypeError, ValueError):
        return selected
    return max(0, integer)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_file_summary(files: Mapping[str, Path]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "written_files": sorted(files.keys()),
        "missing_files": sorted(
            key for key, path in files.items() if not path.exists()
        ),
        "empty_files": sorted(
            key
            for key, path in files.items()
            if path.exists() and path.stat().st_size == 0
        ),
    }


def _build_source_summary(operation_source: Any) -> dict[str, Any]:
    if not isinstance(operation_source, Mapping):
        return {
            "source_shape": type(operation_source).__name__,
            "queue_date": None,
            "evaluation_timestamp": None,
            "has_weekly_option_trade_plan": False,
            "has_options_strategy_defense_review": False,
            "has_options_position_risk_monitor": False,
            "max_priority_actions": None,
            "max_new_trade_actions": None,
            "max_defense_actions": None,
            "include_monitor_items": None,
        }

    return {
        "source_shape": "mapping",
        "queue_date": _string_or_none(operation_source.get("queue_date")),
        "evaluation_timestamp": _string_or_none(operation_source.get("evaluation_timestamp")),
        "has_weekly_option_trade_plan": isinstance(
            operation_source.get("weekly_option_trade_plan"), Mapping
        ),
        "has_options_strategy_defense_review": isinstance(
            operation_source.get("options_strategy_defense_review"), Mapping
        ),
        "has_options_position_risk_monitor": isinstance(
            operation_source.get("options_position_risk_monitor"), Mapping
        ),
        "max_priority_actions": operation_source.get("max_priority_actions"),
        "max_new_trade_actions": operation_source.get("max_new_trade_actions"),
        "max_defense_actions": operation_source.get("max_defense_actions"),
        "include_monitor_items": operation_source.get("include_monitor_items"),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None

