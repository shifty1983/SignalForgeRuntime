from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.execution.operation_audit import audit_execution_planning_operation_record


HEALTHY_STATUS = "healthy"
UNHEALTHY_STATUS = "unhealthy"


@dataclass(frozen=True)
class ExecutionPlanningOperationHealth:
    operation_id: str | None
    health_status: str
    is_healthy: bool
    failed_check_count: int
    failed_checks: list[dict[str, Any]]
    warning_check_count: int
    warning_checks: list[dict[str, Any]]
    audit: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_execution_planning_operation_health(
    record: Any,
) -> ExecutionPlanningOperationHealth:
    audit = audit_execution_planning_operation_record(record)
    audit_dict = audit.to_dict()

    failed_checks = [
        finding
        for finding in audit.findings
        if finding.get("severity") == "error"
    ]

    warning_checks = [
        finding
        for finding in audit.findings
        if finding.get("severity") == "warning"
    ]

    is_healthy = audit.passed and not failed_checks

    return ExecutionPlanningOperationHealth(
        operation_id=audit.operation_id,
        health_status=HEALTHY_STATUS if is_healthy else UNHEALTHY_STATUS,
        is_healthy=is_healthy,
        failed_check_count=len(failed_checks),
        failed_checks=failed_checks,
        warning_check_count=len(warning_checks),
        warning_checks=warning_checks,
        audit=audit_dict,
    )
