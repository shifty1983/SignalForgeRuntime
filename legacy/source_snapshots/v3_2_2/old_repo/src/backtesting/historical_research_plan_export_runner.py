# src/backtesting/historical_research_plan_export_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_plan_export import (
    export_historical_research_plan,
)
from src.backtesting.historical_research_plan_export_audit import (
    audit_historical_research_plan_export_record,
)
from src.backtesting.historical_research_plan_export_health import (
    evaluate_historical_research_plan_export_health,
)
from src.backtesting.historical_research_plan_export_log import (
    build_historical_research_plan_export_log_event,
    write_historical_research_plan_export_log_event,
)
from src.backtesting.historical_research_plan_export_record import (
    build_historical_research_plan_export_record,
)


OPERATION_TYPE = "historical_research_plan_export"


def run_historical_research_plan_export_operation(
    plan_snapshot: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    export_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    research_plan_export = export_historical_research_plan(
        plan_snapshot,
        export_name=export_name,
        metadata=metadata_dict,
    )

    operation_record = build_historical_research_plan_export_record(
        research_plan_export,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_research_plan_export_log_event(operation_record)
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_research_plan_export_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_research_plan_export_record(operation_record)

    health_report = evaluate_historical_research_plan_export_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    export_summary = dict(operation_record.get("export_summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "research_plan_export": research_plan_export,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "export_status": research_plan_export["export_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "ready_count": export_summary.get("ready_count", 0),
            "needs_review_count": export_summary.get("needs_review_count", 0),
            "blocked_count": export_summary.get("blocked_count", 0),
            "total_count": export_summary.get("total_count", 0),
        },
    }
