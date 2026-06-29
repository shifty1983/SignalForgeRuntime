# src/backtesting/historical_validation_promotion_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_validation_promotion_audit import (
    audit_historical_validation_promotion_record,
)
from src.backtesting.historical_validation_promotion_gate import (
    evaluate_historical_validation_promotion_gate,
)
from src.backtesting.historical_validation_promotion_health import (
    evaluate_historical_validation_promotion_health,
)
from src.backtesting.historical_validation_promotion_log import (
    build_historical_validation_promotion_log_event,
    write_historical_validation_promotion_log_event,
)
from src.backtesting.historical_validation_promotion_record import (
    build_historical_validation_promotion_record,
)


OPERATION_TYPE = "historical_validation_promotion"


def run_historical_validation_promotion_operation(
    validation_result: Mapping[str, Any],
    *,
    min_stable_run_ratio: float = 1.0,
    min_positive_edge_run_ratio: float = 1.0,
    min_positive_hit_rate_edge_run_ratio: float = 1.0,
    min_completed_run_ratio: float = 1.0,
    require_validated_status: bool = True,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    promotion_result = evaluate_historical_validation_promotion_gate(
        validation_result,
        min_stable_run_ratio=min_stable_run_ratio,
        min_positive_edge_run_ratio=min_positive_edge_run_ratio,
        min_positive_hit_rate_edge_run_ratio=min_positive_hit_rate_edge_run_ratio,
        min_completed_run_ratio=min_completed_run_ratio,
        require_validated_status=require_validated_status,
    )

    operation_record = build_historical_validation_promotion_record(
        promotion_result,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_validation_promotion_log_event(
            operation_record
        )
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_validation_promotion_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_validation_promotion_record(operation_record)

    health_report = evaluate_historical_validation_promotion_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "promotion_status": promotion_result["promotion_status"],
        "is_promoted": promotion_result["is_promoted"],
        "is_blocked": is_blocked,
        "promotion_result": promotion_result,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "promotion_status": promotion_result["promotion_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
            "is_promoted": promotion_result["is_promoted"],
            "matrix_run_count": promotion_result["promotion_metrics"].get(
                "matrix_run_count",
                0,
            ),
            "completed_run_ratio": promotion_result["promotion_metrics"].get(
                "completed_run_ratio",
                0.0,
            ),
            "stable_run_ratio": promotion_result["promotion_metrics"].get(
                "stable_run_ratio",
                0.0,
            ),
            "positive_edge_run_ratio": promotion_result[
                "promotion_metrics"
            ].get("positive_edge_run_ratio", 0.0),
            "positive_hit_rate_edge_run_ratio": promotion_result[
                "promotion_metrics"
            ].get("positive_hit_rate_edge_run_ratio", 0.0),
        },
    }
