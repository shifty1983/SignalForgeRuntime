from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DISPATCH_OPERATION_LOG_EVENT_TYPE = "execution_dispatch_operation"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    return value


def build_execution_dispatch_operation_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": DISPATCH_OPERATION_LOG_EVENT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "operation_type": operation_record.get("operation_type"),
        "run_id": operation_record.get("run_id"),
        "status": operation_record.get("status"),
        "is_blocked": bool(operation_record.get("is_blocked")),
        "dispatch_intent_count": operation_record.get("dispatch_intent_count", 0),
        "validation_error_count": operation_record.get("validation_error_count", 0),
        "validation_errors": list(operation_record.get("validation_errors", [])),
        "summary": _json_safe(operation_record.get("summary", {})),
        "metadata": _json_safe(operation_record.get("metadata", {})),
    }


def write_execution_dispatch_operation_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    event = build_execution_dispatch_operation_log_event(operation_record)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True) + "\n")

    return event


def read_execution_dispatch_operation_log_events(
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
