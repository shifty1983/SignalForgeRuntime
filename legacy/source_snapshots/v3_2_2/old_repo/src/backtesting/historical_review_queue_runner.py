# src/backtesting/historical_review_queue_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from src.backtesting.historical_review_queue_audit import (
    audit_historical_review_queue_record,
)
from src.backtesting.historical_review_queue_health import (
    evaluate_historical_review_queue_health,
)
from src.backtesting.historical_review_queue_log import (
    build_historical_review_queue_log_event,
    write_historical_review_queue_log_event,
)
from src.backtesting.historical_review_queue_record import (
    build_historical_review_queue_record,
)
from src.backtesting.historical_validation_review_queue import (
    build_historical_validation_review_queue,
)


OPERATION_TYPE = "historical_review_queue"


def run_historical_review_queue_operation(
    summary_exports: Iterable[Mapping[str, Any]],
    *,
    queue_name: str = OPERATION_TYPE,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    exports = [dict(item) for item in summary_exports]
    metadata_dict = dict(metadata or {})

    queue_result = build_historical_validation_review_queue(
        exports,
        queue_name=queue_name,
        metadata=metadata_dict,
    )

    operation_record = build_historical_review_queue_record(
        queue_result,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_review_queue_log_event(operation_record)
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_review_queue_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_review_queue_record(operation_record)

    health_report = evaluate_historical_review_queue_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    review_counts = dict(operation_record.get("review_counts", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "queue_result": queue_result,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "queue_status": queue_result["queue_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "promoted_review_count": review_counts.get("promoted_review", 0),
            "needs_review_count": review_counts.get("needs_review", 0),
            "blocked_review_count": review_counts.get("blocked_review", 0),
            "total_review_count": review_counts.get("total", 0),
        },
    }
