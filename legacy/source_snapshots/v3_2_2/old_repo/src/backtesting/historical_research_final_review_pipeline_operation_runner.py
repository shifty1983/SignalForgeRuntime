# src/backtesting/historical_research_final_review_pipeline_operation_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_final_review_pipeline_audit import (
    audit_historical_research_final_review_pipeline_record,
)
from src.backtesting.historical_research_final_review_pipeline_health import (
    evaluate_historical_research_final_review_pipeline_health,
)
from src.backtesting.historical_research_final_review_pipeline_log import (
    build_historical_research_final_review_pipeline_log_event,
    write_historical_research_final_review_pipeline_log_event,
)
from src.backtesting.historical_research_final_review_pipeline_record import (
    build_historical_research_final_review_pipeline_record,
)
from src.backtesting.historical_research_final_review_pipeline_runner import (
    run_historical_research_final_review_pipeline,
)


OPERATION_TYPE = "historical_research_final_review_pipeline_operation"


def run_historical_research_final_review_pipeline_operation(
    review_artifact_operation_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    pipeline_name: str | None = None,
    summary_operation_name: str | None = None,
    summary_name: str | None = None,
    export_operation_name: str | None = None,
    export_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    summary_log_path: str | Path | None = None,
    export_log_path: str | Path | None = None,
    operation_log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    resolved_pipeline_name = pipeline_name or f"{operation_name}.pipeline"

    final_review_pipeline = run_historical_research_final_review_pipeline(
        review_artifact_operation_result,
        operation_name=resolved_pipeline_name,
        summary_operation_name=summary_operation_name,
        summary_name=summary_name,
        export_operation_name=export_operation_name,
        export_name=export_name,
        metadata=metadata_dict,
        summary_log_path=summary_log_path,
        export_log_path=export_log_path,
    )

    operation_record = build_historical_research_final_review_pipeline_record(
        final_review_pipeline,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if operation_log_path is None:
        log_event = build_historical_research_final_review_pipeline_log_event(
            operation_record
        )
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_research_final_review_pipeline_log_event(
            operation_record,
            operation_log_path,
        )

    audit_report = audit_historical_research_final_review_pipeline_record(
        operation_record
    )

    health_report = evaluate_historical_research_final_review_pipeline_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    pipeline_summary = dict(operation_record.get("pipeline_summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "final_review_pipeline": final_review_pipeline,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "pipeline_runner_status": final_review_pipeline.get("runner_status"),
            "pipeline_status": operation_record["pipeline_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "ready_count": pipeline_summary.get("ready_count", 0),
            "needs_review_count": pipeline_summary.get("needs_review_count", 0),
            "blocked_count": pipeline_summary.get("blocked_count", 0),
            "total_count": pipeline_summary.get("total_count", 0),
            "warning_count": len(operation_record.get("warnings", [])),
            "blocked_reason_count": len(operation_record.get("blocked_reasons", [])),
        },
    }
