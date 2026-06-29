from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


EXECUTION_PLANNING_LOG_EVENT_TYPE = "execution_planning_operation_record"


def build_execution_planning_log_event(record: Any) -> dict[str, Any]:
    normalized_record = _json_safe_record(record)

    validation_errors = normalized_record.get("validation_errors", [])
    if validation_errors is None:
        validation_errors = []

    return {
        "event_type": EXECUTION_PLANNING_LOG_EVENT_TYPE,
        "operation_type": normalized_record.get("operation_type"),
        "operation_id": normalized_record.get("operation_id"),
        "status": normalized_record.get("status"),
        "created_at": normalized_record.get("created_at"),
        "summary": _json_safe(normalized_record.get("summary", {})),
        "validation_error_count": len(validation_errors),
        "validation_errors": _json_safe(list(validation_errors)),
        "metadata": _json_safe(normalized_record.get("metadata", {})),
    }


def append_execution_planning_log_event(
    *,
    record: Any,
    log_path: str | Path,
) -> dict[str, Any]:
    event = build_execution_planning_log_event(record)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True) + "\n")

    return event


def load_execution_planning_log_events(log_path: str | Path) -> list[dict[str, Any]]:
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


def _json_safe_record(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return _json_safe_dict(value)

    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_dict(asdict(value))

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe_record(value.to_dict())

    if hasattr(value, "__dict__"):
        return _json_safe_dict(vars(value))

    raise TypeError(f"Unsupported record type: {type(value).__name__}")


def _json_safe_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe(item) for key, item in value.items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_dict(value)

    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_dict(asdict(value))

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value
