# src/backtesting/historical_strategy_evaluation_log.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LOG_EVENT_TYPE = "historical_strategy_evaluation.operation_recorded"


def build_historical_strategy_evaluation_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    operation_status = operation_record.get("operation_status", "unknown")

    return {
        "event_type": LOG_EVENT_TYPE,
        "operation_type": operation_record.get(
            "operation_type",
            "historical_strategy_evaluation",
        ),
        "operation_id": operation_record.get("operation_id"),
        "operation_name": operation_record.get("operation_name"),
        "operation_status": operation_status,
        "is_blocked": bool(operation_record.get("is_blocked")),
        "validation_error_count": len(operation_record.get("validation_errors", [])),
        "evaluated_candidate_count": operation_record.get("summary", {}).get(
            "evaluated_candidate_count",
            0,
        ),
        "accepted_candidate_count": operation_record.get("summary", {}).get(
            "accepted_candidate_count",
            0,
        ),
        "rejected_candidate_count": operation_record.get("summary", {}).get(
            "rejected_candidate_count",
            0,
        ),
        "summary": dict(operation_record.get("summary", {})),
        "accepted_vs_rejected": dict(
            operation_record.get("accepted_vs_rejected", {})
        ),
        "metadata": dict(operation_record.get("metadata", {})),
    }


def write_historical_strategy_evaluation_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = build_historical_strategy_evaluation_log_event(operation_record)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True, default=str))
        file.write("\n")

    return {
        "log_status": "written",
        "log_path": str(path),
        "event": event,
    }
