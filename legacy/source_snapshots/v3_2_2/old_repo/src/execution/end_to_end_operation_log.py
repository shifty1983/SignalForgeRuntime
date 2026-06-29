from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def build_execution_end_to_end_operation_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build a JSON-safe log event for an end-to-end execution dry-run operation.
    """

    return _json_safe(
        {
            "event_type": "execution_end_to_end_operation_recorded",
            "operation_id": operation_record.get("operation_id"),
            "operation_type": operation_record.get("operation_type"),
            "dry_run_id": operation_record.get("summary", {}).get("dry_run_id"),
            "status": operation_record.get("status"),
            "is_blocked": operation_record.get("is_blocked"),
            "blocked_stage": operation_record.get("blocked_stage"),
            "validation_errors": operation_record.get("validation_errors", []),
            "summary": operation_record.get("summary", {}),
        }
    )


def write_execution_end_to_end_operation_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    """
    Append the operation event to a JSONL log and return the event.
    """

    event = build_execution_end_to_end_operation_log_event(operation_record)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True))
        file.write("\n")

    return event


def read_execution_end_to_end_operation_log_events(
    log_path: str | Path,
) -> list[dict[str, Any]]:
    path = Path(log_path)

    if not path.exists():
        return []

    events: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                events.append(json.loads(stripped))

    return events


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(value[key])
            for key in sorted(value.keys(), key=str)
        }

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)
