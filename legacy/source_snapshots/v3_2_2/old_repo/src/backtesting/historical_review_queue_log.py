# src/backtesting/historical_review_queue_log.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LOG_EVENT_TYPE = "historical_review_queue.operation_recorded"


def build_historical_review_queue_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    review_counts = dict(operation_record.get("review_counts", {}))

    return {
        "event_type": LOG_EVENT_TYPE,
        "operation_type": operation_record.get("operation_type", "historical_review_queue"),
        "operation_id": operation_record.get("operation_id"),
        "operation_name": operation_record.get("operation_name"),
        "operation_status": operation_record.get("operation_status"),
        "queue_status": operation_record.get("queue_status"),
        "is_blocked": bool(operation_record.get("is_blocked")),
        "validation_error_count": len(operation_record.get("validation_errors", [])),
        "warning_count": len(operation_record.get("warnings", [])),
        "blocked_reason_count": len(operation_record.get("blocked_reasons", [])),
        "promoted_review_count": review_counts.get("promoted_review", 0),
        "needs_review_count": review_counts.get("needs_review", 0),
        "blocked_review_count": review_counts.get("blocked_review", 0),
        "total_review_count": review_counts.get("total", 0),
        "review_counts": review_counts,
        "metadata": dict(operation_record.get("metadata", {})),
    }


def write_historical_review_queue_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = build_historical_review_queue_log_event(operation_record)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True, default=str))
        file.write("\n")

    return {
        "log_status": "written",
        "log_path": str(path),
        "event": event,
    }
