# src/backtesting/historical_research_final_review_summary_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_final_review_summary import (
    build_historical_research_final_review_summary,
)
from src.backtesting.historical_research_final_review_summary_audit import (
    audit_historical_research_final_review_summary_record,
)
from src.backtesting.historical_research_final_review_summary_health import (
    evaluate_historical_research_final_review_summary_health,
)
from src.backtesting.historical_research_final_review_summary_log import (
    build_historical_research_final_review_summary_log_event,
    write_historical_research_final_review_summary_log_event,
)
from src.backtesting.historical_research_final_review_summary_record import (
    build_historical_research_final_review_summary_record,
)


OPERATION_TYPE = "historical_research_final_review_summary"


def run_historical_research_final_review_summary_operation(
    review_artifact_operation_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    summary_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    final_review_summary = build_historical_research_final_review_summary(
        review_artifact_operation_result,
        summary_name=summary_name,
        metadata=metadata_dict,
    )

    operation_record = build_historical_research_final_review_summary_record(
        final_review_summary,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_research_final_review_summary_log_event(
            operation_record
        )
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_research_final_review_summary_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_research_final_review_summary_record(
        operation_record
    )

    health_report = evaluate_historical_research_final_review_summary_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    final_counts = dict(operation_record.get("final_counts", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "final_review_summary": final_review_summary,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "summary_status": final_review_summary["summary_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "ready_count": final_counts.get("ready", 0),
            "needs_review_count": final_counts.get("needs_review", 0),
            "blocked_count": final_counts.get("blocked", 0),
            "total_count": final_counts.get("total", 0),
            "exact_matrix_cell_ready_record_count": final_review_summary.get(
                "exact_matrix_cell_ready_record_count", 0
            ),
            "matrix_metadata_needs_review_record_count": final_review_summary.get(
                "matrix_metadata_needs_review_record_count", 0
            ),
            "ready_to_build_exact_matrix_edge_summary": final_review_summary.get(
                "ready_to_build_exact_matrix_edge_summary", False
            ),
            "recommended_next_step": final_review_summary.get("recommended_next_step"),
        },
    }
