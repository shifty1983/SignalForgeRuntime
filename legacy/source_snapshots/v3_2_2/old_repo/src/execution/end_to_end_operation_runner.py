from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from src.execution.end_to_end_dry_run import (
    run_portfolio_strategy_execution_dry_run,
)
from src.execution.end_to_end_operation_audit import (
    build_execution_end_to_end_operation_audit_report,
)
from src.execution.end_to_end_operation_health import (
    evaluate_execution_end_to_end_operation_health,
)
from src.execution.end_to_end_operation_log import (
    build_execution_end_to_end_operation_log_event,
    write_execution_end_to_end_operation_log_event,
)
from src.execution.end_to_end_operation_record import (
    build_execution_end_to_end_operation_record,
)


ExecutionStageRunner = Callable[[Sequence[Mapping[str, Any]]], Any]


def run_execution_end_to_end_operation(
    strategy_risk_managed_candidates: Sequence[Mapping[str, Any]],
    *,
    dry_run_id: str | None = None,
    operation_id: str | None = None,
    log_path: str | Path | None = None,
    output_dir: str | None = None,
    execution_input_runner: ExecutionStageRunner | None = None,
    execution_planning_runner: ExecutionStageRunner | None = None,
    dispatch_runner: ExecutionStageRunner | None = None,
    use_existing_runners: bool = True,
) -> dict[str, Any]:
    """
    Run the complete broker-neutral portfolio / strategy / execution
    end-to-end operation path.

    Flow:
        strategy/risk-managed candidates
        -> dry-run orchestrator
        -> operation record
        -> JSONL log event
        -> audit
        -> health gate
        -> deterministic runner result

    Explicitly excluded:
        broker APIs, routing, order submission, fills, live execution,
        and slippage modeling.
    """

    dry_run_result = run_portfolio_strategy_execution_dry_run(
        strategy_risk_managed_candidates,
        dry_run_id=dry_run_id,
        execution_input_runner=execution_input_runner,
        execution_planning_runner=execution_planning_runner,
        dispatch_runner=dispatch_runner,
        use_existing_runners=use_existing_runners,
        output_dir=output_dir,
    )

    operation_record = build_execution_end_to_end_operation_record(
        dry_run_result,
        operation_id=operation_id,
    )

    if log_path is None:
        log_event = build_execution_end_to_end_operation_log_event(
            operation_record
        )
        log_event_written = False
        resolved_log_path = None
    else:
        resolved_log_path = str(Path(log_path))
        log_event = write_execution_end_to_end_operation_log_event(
            operation_record,
            log_path,
        )
        log_event_written = True

    audit_report = build_execution_end_to_end_operation_audit_report(
        operation_record
    )

    health_report = evaluate_execution_end_to_end_operation_health(
        operation_record,
        audit_report=audit_report,
    )

    is_blocked = bool(
        dry_run_result.get("is_blocked", True)
        or operation_record.get("is_blocked", True)
        or not health_report.get("is_healthy", False)
    )

    status = "blocked" if is_blocked else "completed"

    blocked_stage = (
        dry_run_result.get("blocked_stage")
        or operation_record.get("blocked_stage")
        or ("health" if not health_report.get("is_healthy", False) else None)
    )

    summary = _build_runner_summary(
        status=status,
        is_blocked=is_blocked,
        blocked_stage=blocked_stage,
        dry_run_result=dry_run_result,
        operation_record=operation_record,
        log_event_written=log_event_written,
        log_path=resolved_log_path,
        audit_report=audit_report,
        health_report=health_report,
    )

    return {
        "status": status,
        "is_blocked": is_blocked,
        "blocked_stage": blocked_stage,
        "dry_run_result": dry_run_result,
        "operation_record": operation_record,
        "log_event": log_event,
        "audit_report": audit_report,
        "health_report": health_report,
        "summary": summary,
    }


def _build_runner_summary(
    *,
    status: str,
    is_blocked: bool,
    blocked_stage: str | None,
    dry_run_result: Mapping[str, Any],
    operation_record: Mapping[str, Any],
    log_event_written: bool,
    log_path: str | None,
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
) -> dict[str, Any]:
    dry_run_summary = dry_run_result.get("summary", {})
    operation_summary = operation_record.get("summary", {})

    return {
        "status": status,
        "is_blocked": is_blocked,
        "blocked_stage": blocked_stage,
        "dry_run_id": dry_run_result.get("dry_run_id"),
        "operation_id": operation_record.get("operation_id"),
        "operation_type": operation_record.get("operation_type"),
        "candidate_count": operation_summary.get(
            "candidate_count",
            dry_run_summary.get("candidate_count", 0),
        ),
        "execution_intent_count": operation_summary.get(
            "execution_intent_count",
            dry_run_summary.get("execution_intent_count", 0),
        ),
        "planned_instruction_count": operation_summary.get(
            "planned_instruction_count",
            dry_run_summary.get("planned_instruction_count", 0),
        ),
        "dispatch_intent_count": operation_summary.get(
            "dispatch_intent_count",
            dry_run_summary.get("dispatch_intent_count", 0),
        ),
        "dry_run_status": dry_run_result.get("status"),
        "operation_status": operation_record.get("status"),
        "audit_status": audit_report.get("audit_status"),
        "audit_finding_count": audit_report.get("finding_count", 0),
        "health_status": health_report.get("health_status"),
        "health_failed_check_count": health_report.get(
            "failed_check_count",
            0,
        ),
        "validation_error_count": len(
            operation_record.get("validation_errors", [])
        ),
        "log_event_written": log_event_written,
        "log_path": log_path,
    }
