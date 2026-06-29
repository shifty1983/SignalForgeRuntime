# src/backtesting/historical_research_planning_log.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LOG_EVENT_TYPE = "historical_research_planning.operation_recorded"


def build_historical_research_planning_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    planning_counts = dict(operation_record.get("planning_counts", {}))

    return {
        "event_type": LOG_EVENT_TYPE,
        "operation_type": operation_record.get(
            "operation_type",
            "historical_research_planning",
        ),
        "operation_id": operation_record.get("operation_id"),
        "operation_name": operation_record.get("operation_name"),
        "operation_status": operation_record.get("operation_status"),
        "planning_queue_status": operation_record.get("planning_queue_status"),
        "is_ready": bool(operation_record.get("is_ready")),
        "is_blocked": bool(operation_record.get("is_blocked")),
        "validation_error_count": len(operation_record.get("validation_errors", [])),
        "warning_count": len(operation_record.get("warnings", [])),
        "blocked_reason_count": len(operation_record.get("blocked_reasons", [])),
        "priority_count": planning_counts.get("priority", 0),
        "needs_review_count": planning_counts.get("needs_review", 0),
        "blocked_count": planning_counts.get("blocked", 0),
        "total_count": planning_counts.get("total", 0),
        "planning_counts": planning_counts,
        "metadata": dict(operation_record.get("metadata", {})),
    }


def write_historical_research_planning_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = build_historical_research_planning_log_event(operation_record)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True, default=str))
        file.write("\n")

    return {
        "log_status": "written",
        "log_path": str(path),
        "event": event,
    }
