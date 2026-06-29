# src/backtesting/historical_research_planning_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_planning_audit import (
    audit_historical_research_planning_record,
)
from src.backtesting.historical_research_planning_health import (
    evaluate_historical_research_planning_health,
)
from src.backtesting.historical_research_planning_log import (
    build_historical_research_planning_log_event,
    write_historical_research_planning_log_event,
)
from src.backtesting.historical_research_planning_queue import (
    build_historical_research_planning_queue,
)
from src.backtesting.historical_research_planning_record import (
    build_historical_research_planning_record,
)


OPERATION_TYPE = "historical_research_planning"


def run_historical_research_planning_operation(
    handoff_operation_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    planning_queue_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    planning_queue = build_historical_research_planning_queue(
        handoff_operation_result,
        planning_queue_name=planning_queue_name,
        metadata=metadata_dict,
    )

    operation_record = build_historical_research_planning_record(
        planning_queue,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_research_planning_log_event(operation_record)
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_research_planning_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_research_planning_record(operation_record)

    health_report = evaluate_historical_research_planning_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    planning_counts = dict(operation_record.get("planning_counts", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "planning_queue": planning_queue,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "planning_queue_status": planning_queue["planning_queue_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "priority_count": planning_counts.get("priority", 0),
            "needs_review_count": planning_counts.get("needs_review", 0),
            "blocked_count": planning_counts.get("blocked", 0),
            "total_count": planning_counts.get("total", 0),
        },
    }
