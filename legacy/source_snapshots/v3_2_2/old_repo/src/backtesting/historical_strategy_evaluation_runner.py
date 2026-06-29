# src/backtesting/historical_strategy_evaluation_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from src.backtesting.historical_strategy_evaluation import (
    evaluate_historical_strategy_candidates,
)
from src.backtesting.historical_strategy_evaluation_audit import (
    audit_historical_strategy_evaluation_record,
)
from src.backtesting.historical_strategy_evaluation_health import (
    evaluate_historical_strategy_evaluation_health,
)
from src.backtesting.historical_strategy_evaluation_log import (
    build_historical_strategy_evaluation_log_event,
    write_historical_strategy_evaluation_log_event,
)
from src.backtesting.historical_strategy_evaluation_record import (
    build_historical_strategy_evaluation_record,
)


OPERATION_TYPE = "historical_strategy_evaluation"


def run_historical_strategy_evaluation_operation(
    historical_candidate_rows: Iterable[Mapping[str, Any]],
    *,
    neutral_band: float = 0.01,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    rows = [dict(row) for row in historical_candidate_rows]
    metadata_dict = dict(metadata or {})

    evaluation_report = evaluate_historical_strategy_candidates(
        rows,
        neutral_band=neutral_band,
    )

    operation_record = build_historical_strategy_evaluation_record(
        evaluation_report,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_strategy_evaluation_log_event(operation_record)
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_strategy_evaluation_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_strategy_evaluation_record(operation_record)

    health_report = evaluate_historical_strategy_evaluation_health(
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
        "is_blocked": is_blocked,
        "evaluation_report": evaluation_report,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "historical_candidate_count": len(rows),
            "evaluated_candidate_count": operation_record["summary"].get(
                "evaluated_candidate_count",
                0,
            ),
            "accepted_candidate_count": operation_record["summary"].get(
                "accepted_candidate_count",
                0,
            ),
            "rejected_candidate_count": operation_record["summary"].get(
                "rejected_candidate_count",
                0,
            ),
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
        },
    }
