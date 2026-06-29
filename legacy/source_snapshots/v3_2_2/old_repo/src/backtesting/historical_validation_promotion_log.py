# src/backtesting/historical_validation_promotion_log.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LOG_EVENT_TYPE = "historical_validation_promotion.operation_recorded"


def build_historical_validation_promotion_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    promotion_metrics = dict(operation_record.get("promotion_metrics", {}))
    summary = dict(operation_record.get("summary", {}))

    return {
        "event_type": LOG_EVENT_TYPE,
        "operation_type": operation_record.get(
            "operation_type",
            "historical_validation_promotion",
        ),
        "operation_id": operation_record.get("operation_id"),
        "operation_name": operation_record.get("operation_name"),
        "operation_status": operation_record.get("operation_status"),
        "promotion_status": operation_record.get("promotion_status"),
        "is_promoted": bool(operation_record.get("is_promoted")),
        "is_blocked": bool(operation_record.get("is_blocked")),
        "validation_error_count": len(operation_record.get("validation_errors", [])),
        "blocked_reason_count": len(operation_record.get("blocked_reasons", [])),
        "warning_count": len(operation_record.get("warnings", [])),
        "matrix_run_count": promotion_metrics.get("matrix_run_count", 0),
        "completed_run_ratio": promotion_metrics.get("completed_run_ratio", 0.0),
        "stable_run_ratio": promotion_metrics.get("stable_run_ratio", 0.0),
        "positive_edge_run_ratio": promotion_metrics.get(
            "positive_edge_run_ratio",
            0.0,
        ),
        "positive_hit_rate_edge_run_ratio": promotion_metrics.get(
            "positive_hit_rate_edge_run_ratio",
            0.0,
        ),
        "summary": summary,
        "metadata": dict(operation_record.get("metadata", {})),
    }


def write_historical_validation_promotion_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = build_historical_validation_promotion_log_event(operation_record)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True, default=str))
        file.write("\n")

    return {
        "log_status": "written",
        "log_path": str(path),
        "event": event,
    }
