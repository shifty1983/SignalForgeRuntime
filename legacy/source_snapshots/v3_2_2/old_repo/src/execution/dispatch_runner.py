from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from src.execution.dispatch_contract import build_execution_dispatch_contract
from src.execution.dispatch_operation_audit import (
    audit_execution_dispatch_operation_record,
)
from src.execution.dispatch_operation_health import (
    evaluate_execution_dispatch_operation_health,
)
from src.execution.dispatch_operation_log import (
    write_execution_dispatch_operation_log_event,
)
from src.execution.dispatch_operation_record import (
    build_execution_dispatch_operation_record,
)


DISPATCH_RUNNER_NAME = "execution_dispatch_runner"


def _copy_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def build_execution_dispatch_runner_summary(
    *,
    operation_record: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    log_written: bool,
) -> dict[str, Any]:
    return {
        "runner_name": DISPATCH_RUNNER_NAME,
        "operation_id": operation_record.get("operation_id"),
        "run_id": operation_record.get("run_id"),
        "operation_status": operation_record.get("status"),
        "dispatch_intent_count": operation_record.get("dispatch_intent_count", 0),
        "validation_error_count": operation_record.get("validation_error_count", 0),
        "is_blocked": bool(operation_record.get("is_blocked")),
        "audit_status": audit_report.get("audit_status"),
        "health_status": health_report.get("health_status"),
        "is_healthy": bool(health_report.get("is_healthy")),
        "failure_count": health_report.get("failure_count", 0),
        "log_written": log_written,
    }


def run_execution_dispatch(
    planned_order_instructions: Sequence[Any],
    *,
    operation_id: str = "execution_dispatch_operation",
    run_id: str = "execution_dispatch_run",
    log_path: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run broker-neutral execution dispatch intent orchestration.

    This runner only produces dispatch intent records. It does not call broker APIs,
    route orders, submit orders, model fills, perform live execution, or calculate
    slippage.
    """
    runner_metadata = _copy_metadata(metadata)
    runner_metadata.setdefault("runner_name", DISPATCH_RUNNER_NAME)
    runner_metadata.setdefault("dry_run_only", True)

    contract_result = build_execution_dispatch_contract(planned_order_instructions)

    operation_record = build_execution_dispatch_operation_record(
        contract_result,
        operation_id=operation_id,
        run_id=run_id,
        metadata=runner_metadata,
    )

    log_event = None
    log_written = False
    if log_path is not None:
        log_event = write_execution_dispatch_operation_log_event(
            operation_record,
            log_path,
        )
        log_written = True

    audit_report = audit_execution_dispatch_operation_record(operation_record)
    health_report = evaluate_execution_dispatch_operation_health(
        operation_record,
        audit_report,
    )

    summary = build_execution_dispatch_runner_summary(
        operation_record=operation_record,
        audit_report=audit_report,
        health_report=health_report,
        log_written=log_written,
    )

    return {
        "runner_name": DISPATCH_RUNNER_NAME,
        "operation_id": operation_id,
        "run_id": run_id,
        "contract_result": contract_result,
        "operation_record": operation_record,
        "log_event": log_event,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": summary,
        "is_blocked": bool(operation_record.get("is_blocked")),
        "is_healthy": bool(health_report.get("is_healthy")),
    }


def validate_execution_dispatch_runner_result(
    runner_result: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []

    required_fields = (
        "runner_name",
        "operation_id",
        "run_id",
        "contract_result",
        "operation_record",
        "log_event",
        "audit_report",
        "health_report",
        "summary",
        "is_blocked",
        "is_healthy",
    )

    for field_name in required_fields:
        if field_name not in runner_result:
            errors.append(f"runner_result missing required field: {field_name}")

    if runner_result.get("runner_name") != DISPATCH_RUNNER_NAME:
        errors.append(f"runner_result runner_name must be {DISPATCH_RUNNER_NAME}")

    operation_record = runner_result.get("operation_record", {})
    audit_report = runner_result.get("audit_report", {})
    health_report = runner_result.get("health_report", {})
    summary = runner_result.get("summary", {})

    if not isinstance(operation_record, Mapping):
        errors.append("runner_result operation_record must be a mapping")
        operation_record = {}

    if not isinstance(audit_report, Mapping):
        errors.append("runner_result audit_report must be a mapping")
        audit_report = {}

    if not isinstance(health_report, Mapping):
        errors.append("runner_result health_report must be a mapping")
        health_report = {}

    if not isinstance(summary, Mapping):
        errors.append("runner_result summary must be a mapping")
        summary = {}

    if runner_result.get("operation_id") != operation_record.get("operation_id"):
        errors.append("runner_result operation_id does not match operation_record")

    if runner_result.get("run_id") != operation_record.get("run_id"):
        errors.append("runner_result run_id does not match operation_record")

    if bool(runner_result.get("is_blocked")) != bool(operation_record.get("is_blocked")):
        errors.append("runner_result is_blocked does not match operation_record")

    if bool(runner_result.get("is_healthy")) != bool(health_report.get("is_healthy")):
        errors.append("runner_result is_healthy does not match health_report")

    if summary.get("operation_id") != operation_record.get("operation_id"):
        errors.append("runner_result summary operation_id does not match operation_record")

    if summary.get("run_id") != operation_record.get("run_id"):
        errors.append("runner_result summary run_id does not match operation_record")

    if summary.get("audit_status") != audit_report.get("audit_status"):
        errors.append("runner_result summary audit_status does not match audit_report")

    if summary.get("health_status") != health_report.get("health_status"):
        errors.append("runner_result summary health_status does not match health_report")

    return errors
