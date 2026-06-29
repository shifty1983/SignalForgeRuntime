# src/backtesting/historical_research_priority_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_priority_audit import (
    audit_historical_research_priority_record,
)
from src.backtesting.historical_research_priority_health import (
    evaluate_historical_research_priority_health,
)
from src.backtesting.historical_research_priority_log import (
    build_historical_research_priority_log_event,
    write_historical_research_priority_log_event,
)
from src.backtesting.historical_research_priority_record import (
    build_historical_research_priority_record,
)
from src.backtesting.historical_research_priority_report import (
    build_historical_research_priority_report,
)


OPERATION_TYPE = "historical_research_priority"


def run_historical_research_priority_operation(
    decision_snapshot: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    report_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    priority_report = build_historical_research_priority_report(
        decision_snapshot,
        report_name=report_name,
        metadata=metadata_dict,
    )

    operation_record = build_historical_research_priority_record(
        priority_report,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_research_priority_log_event(operation_record)
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_research_priority_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_research_priority_record(operation_record)

    health_report = evaluate_historical_research_priority_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    priority_summary = dict(operation_record.get("priority_summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "priority_report": priority_report,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "report_status": priority_report["report_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "priority_count": priority_summary.get("priority_count", 0),
            "needs_review_count": priority_summary.get("needs_review_count", 0),
            "blocked_count": priority_summary.get("blocked_count", 0),
            "total_count": priority_summary.get("total_count", 0),
        },
    }
