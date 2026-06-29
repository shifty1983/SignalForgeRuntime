# src/backtesting/historical_research_review_artifact_log.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LOG_EVENT_TYPE = "historical_research_review_artifact.operation_recorded"


def build_historical_research_review_artifact_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    artifact_summary = dict(operation_record.get("artifact_summary", {}))

    return {
        "event_type": LOG_EVENT_TYPE,
        "operation_type": operation_record.get(
            "operation_type",
            "historical_research_review_artifact",
        ),
        "operation_id": operation_record.get("operation_id"),
        "operation_name": operation_record.get("operation_name"),
        "operation_status": operation_record.get("operation_status"),
        "artifact_status": operation_record.get("artifact_status"),
        "is_ready": bool(operation_record.get("is_ready")),
        "is_blocked": bool(operation_record.get("is_blocked")),
        "validation_error_count": len(operation_record.get("validation_errors", [])),
        "warning_count": len(operation_record.get("warnings", [])),
        "blocked_reason_count": len(operation_record.get("blocked_reasons", [])),
        "ready_count": artifact_summary.get("ready_count", 0),
        "needs_review_count": artifact_summary.get("needs_review_count", 0),
        "blocked_count": artifact_summary.get("blocked_count", 0),
        "total_count": artifact_summary.get("total_count", 0),
        "artifact_summary": artifact_summary,
        "metadata": dict(operation_record.get("metadata", {})),
    }


def write_historical_research_review_artifact_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = build_historical_research_review_artifact_log_event(operation_record)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True, default=str))
        file.write("\n")

    return {
        "log_status": "written",
        "log_path": str(path),
        "event": event,
    }
