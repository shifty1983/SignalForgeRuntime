# src/backtesting/historical_data_readiness_adapter_log.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LOG_EVENT_TYPE = "historical_data_readiness_adapter_operation.operation_recorded"


def build_historical_data_readiness_adapter_log_event(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    readiness_summary = dict(operation_record.get("readiness_summary", {}))

    return {
        "event_type": LOG_EVENT_TYPE,
        "operation_type": operation_record.get(
            "operation_type",
            "historical_data_readiness_adapter_operation",
        ),
        "operation_id": operation_record.get("operation_id"),
        "operation_name": operation_record.get("operation_name"),
        "operation_status": operation_record.get("operation_status"),
        "adapter_status": operation_record.get("adapter_status"),
        "source_adapter_type": operation_record.get("source_adapter_type"),
        "is_ready": bool(operation_record.get("is_ready")),
        "is_blocked": bool(operation_record.get("is_blocked")),
        "validation_error_count": len(operation_record.get("validation_errors", [])),
        "warning_count": len(operation_record.get("warnings", [])),
        "blocked_reason_count": len(operation_record.get("blocked_reasons", [])),
        "candidate_count": readiness_summary.get("candidate_count", 0),
        "price_row_count": readiness_summary.get("price_row_count", 0),
        "accepted_candidate_count": readiness_summary.get(
            "accepted_candidate_count",
            0,
        ),
        "rejected_candidate_count": readiness_summary.get(
            "rejected_candidate_count",
            0,
        ),
        "symbol_count": readiness_summary.get("symbol_count", 0),
        "candidate_symbol_count": readiness_summary.get("candidate_symbol_count", 0),
        "max_forward_window": readiness_summary.get("max_forward_window"),
        "readiness_summary": readiness_summary,
        "metadata": dict(operation_record.get("metadata", {})),
    }


def write_historical_data_readiness_adapter_log_event(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = build_historical_data_readiness_adapter_log_event(operation_record)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True, default=str))
        file.write("\n")

    return {
        "log_status": "written",
        "log_path": str(path),
        "event": event,
    }
