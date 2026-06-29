from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

from src.execution.operation_audit import audit_execution_planning_operation_record
from src.execution.operation_health import evaluate_execution_planning_operation_health
from src.execution.operation_log import (
    append_execution_planning_log_event,
    build_execution_planning_log_event,
)
from src.execution.operation_record import build_execution_planning_operation_record
from src.execution.planning import _build_planned_order_instruction


ExecutionPlanner = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class ExecutionPlanningOperationRunResult:
    operation_id: str
    status: str
    is_healthy: bool
    record: dict[str, Any]
    log_event: dict[str, Any]
    audit: dict[str, Any]
    health: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_execution_planning_operation(
    *,
    execution_intent_rows: Sequence[Mapping[str, Any]],
    operation_id: str = "execution_planning_runner_operation",
    created_at: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | None = None,
    planner: ExecutionPlanner | None = None,
) -> ExecutionPlanningOperationRunResult:
    """
    Run the execution planning operation.

    This intentionally stops before:
    - broker routing
    - order submission
    - fills
    - fill simulation
    - slippage modeling
    - live execution
    """

    intent_rows = [dict(row) for row in execution_intent_rows]
    planner_fn = planner or _build_planned_order_instruction

    planned_order_instructions, planning_errors = _build_planned_order_instructions(
        execution_intent_rows=intent_rows,
        planner=planner_fn,
    )

    record = build_execution_planning_operation_record(
        execution_intent_rows=intent_rows,
        planned_order_instructions=planned_order_instructions,
        operation_id=operation_id,
        created_at=created_at,
        metadata=metadata or {},
        additional_validation_errors=planning_errors,
    )

    if log_path:
        log_event = append_execution_planning_log_event(
            record=record,
            log_path=log_path,
        )
    else:
        log_event = build_execution_planning_log_event(record)

    audit = audit_execution_planning_operation_record(record)
    health = evaluate_execution_planning_operation_health(record)

    return ExecutionPlanningOperationRunResult(
        operation_id=record.operation_id,
        status=record.status,
        is_healthy=health.is_healthy,
        record=record.to_dict(),
        log_event=log_event,
        audit=audit.to_dict(),
        health=health.to_dict(),
        metadata=dict(metadata or {}),
    )


def _build_planned_order_instructions(
    *,
    execution_intent_rows: Sequence[Mapping[str, Any]],
    planner: ExecutionPlanner,
) -> tuple[list[Any], list[str]]:
    planned_order_instructions: list[Any] = []
    planning_errors: list[str] = []

    for index, row in enumerate(execution_intent_rows):
        try:
            planned_order_instructions.append(planner(row))
        except Exception as error:
            planning_errors.append(
                "execution_intent_rows"
                f"[{index}] planning failed: {type(error).__name__}: {error}"
            )

    return planned_order_instructions, planning_errors
