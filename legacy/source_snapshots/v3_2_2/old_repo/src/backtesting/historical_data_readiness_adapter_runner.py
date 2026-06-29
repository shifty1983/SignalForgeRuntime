# src/backtesting/historical_data_readiness_adapter_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.backtesting.historical_data_readiness_adapter import (
    adapt_historical_data_for_validation,
)
from src.backtesting.historical_data_readiness_adapter_audit import (
    audit_historical_data_readiness_adapter_record,
)
from src.backtesting.historical_data_readiness_adapter_health import (
    evaluate_historical_data_readiness_adapter_health,
)
from src.backtesting.historical_data_readiness_adapter_log import (
    build_historical_data_readiness_adapter_log_event,
    write_historical_data_readiness_adapter_log_event,
)
from src.backtesting.historical_data_readiness_adapter_record import (
    build_historical_data_readiness_adapter_record,
)


OPERATION_TYPE = "historical_data_readiness_adapter_operation"


def run_historical_data_readiness_adapter_operation(
    candidate_records: Iterable[Mapping[str, Any]],
    price_records: Iterable[Mapping[str, Any]],
    *,
    forward_windows: Sequence[int] = (1,),
    candidate_field_map: Mapping[str, str] | None = None,
    price_field_map: Mapping[str, str] | None = None,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    adapter_result = adapt_historical_data_for_validation(
        candidate_records,
        price_records,
        forward_windows=forward_windows,
        candidate_field_map=candidate_field_map,
        price_field_map=price_field_map,
        metadata=metadata_dict,
    )

    operation_record = build_historical_data_readiness_adapter_record(
        adapter_result,
        operation_name=operation_name,
        metadata=metadata_dict,
    )

    if log_path is None:
        log_event = build_historical_data_readiness_adapter_log_event(
            operation_record
        )
        log_result = {
            "log_status": "skipped",
            "log_path": None,
            "event": log_event,
        }
    else:
        log_result = write_historical_data_readiness_adapter_log_event(
            operation_record,
            log_path,
        )

    audit_report = audit_historical_data_readiness_adapter_record(operation_record)

    health_report = evaluate_historical_data_readiness_adapter_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = (
        operation_record["is_blocked"]
        or not audit_report["is_audit_passed"]
        or health_report["is_blocked"]
    )

    runner_status = "blocked" if is_blocked else "completed"

    readiness_summary = dict(operation_record.get("readiness_summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "adapter_result": adapter_result,
        "operation_record": operation_record,
        "log_result": log_result,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": {
            "adapter_status": adapter_result["adapter_status"],
            "operation_status": operation_record["operation_status"],
            "audit_status": audit_report["audit_status"],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
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
            "candidate_symbol_count": readiness_summary.get(
                "candidate_symbol_count",
                0,
            ),
            "max_forward_window": readiness_summary.get("max_forward_window"),
            "validation_error_count": len(operation_record.get("validation_errors", [])),
            "warning_count": len(operation_record.get("warnings", [])),
            "blocked_reason_count": len(operation_record.get("blocked_reasons", [])),
        },
    }
