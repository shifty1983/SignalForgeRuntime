# src/backtesting/historical_research_handoff_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_handoff_audit import (
    audit_historical_research_handoff_record,
)
from src.backtesting.historical_research_handoff_bundle import (
    build_historical_research_handoff_bundle,
)
from src.backtesting.historical_research_handoff_health import (
    evaluate_historical_research_handoff_health,
)
from src.backtesting.historical_research_handoff_log import (
    build_historical_research_handoff_log_event,
    write_historical_research_handoff_log_event,
)
from src.backtesting.historical_research_handoff_record import (
    build_historical_research_handoff_record,
)


OPERATION_TYPE = "historical_research_handoff"


def run_historical_research_handoff_operation(
    priority_operation_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    bundle_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    handoff_bundle = build_historical_research_handoff_bundle(
        priority_operation_result,
        bundle_name=bundle_name,
        metadata=metadata_dict,
    )

    operation_record = build_historical_research_handoff_record(
        handoff_bundle,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_research_handoff_log_event(operation_record)
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_research_handoff_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_research_handoff_record(operation_record)

    health_report = evaluate_historical_research_handoff_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    handoff_summary = dict(operation_record.get("handoff_summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "handoff_bundle": handoff_bundle,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "bundle_status": handoff_bundle["bundle_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "priority_count": handoff_summary.get("priority_count", 0),
            "needs_review_count": handoff_summary.get("needs_review_count", 0),
            "blocked_count": handoff_summary.get("blocked_count", 0),
            "total_count": handoff_summary.get("total_count", 0),
        },
    }
