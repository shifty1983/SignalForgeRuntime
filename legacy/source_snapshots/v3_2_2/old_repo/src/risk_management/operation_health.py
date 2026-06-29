from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.risk_management.operation_audit import (
    audit_risk_management_operation_record,
)
from src.risk_management.operation_record import RiskManagementOperationRecord


class RiskManagementHealthGateError(RuntimeError):
    """Raised when risk management operation health gate fails."""


@dataclass(frozen=True)
class RiskManagementOperationHealth:
    passed: bool
    health_status: str
    operation_id: str | None
    approved_count: int
    total_risk_exposure: float
    net_exposure: float
    blocking_reasons: tuple[str, ...]
    audit_issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "health_status": self.health_status,
            "operation_id": self.operation_id,
            "approved_count": self.approved_count,
            "total_risk_exposure": self.total_risk_exposure,
            "net_exposure": self.net_exposure,
            "blocking_reasons": list(self.blocking_reasons),
            "audit_issues": list(self.audit_issues),
        }


def evaluate_risk_management_operation_health(
    record: RiskManagementOperationRecord | Mapping[str, Any],
) -> RiskManagementOperationHealth:
    payload = _record_to_dict(record)
    audit_report = audit_risk_management_operation_record(payload)

    operation_id = payload.get("operation_id")
    approved_count = payload.get("approved_count", 0)
    total_risk_exposure = payload.get("total_risk_exposure", 0.0)
    net_exposure = payload.get("net_exposure", 0.0)

    if not audit_report.passed:
        return RiskManagementOperationHealth(
            passed=False,
            health_status="failed",
            operation_id=operation_id if isinstance(operation_id, str) else None,
            approved_count=approved_count if isinstance(approved_count, int) else 0,
            total_risk_exposure=(
                float(total_risk_exposure)
                if isinstance(total_risk_exposure, (int, float))
                else 0.0
            ),
            net_exposure=(
                float(net_exposure)
                if isinstance(net_exposure, (int, float))
                else 0.0
            ),
            blocking_reasons=(),
            audit_issues=audit_report.issues,
        )

    if payload.get("passed") is not True:
        blocking_reasons = payload.get("blocking_reasons") or (
            "risk management operation blocked",
        )

        return RiskManagementOperationHealth(
            passed=False,
            health_status="blocked",
            operation_id=operation_id if isinstance(operation_id, str) else None,
            approved_count=approved_count,
            total_risk_exposure=float(total_risk_exposure),
            net_exposure=float(net_exposure),
            blocking_reasons=tuple(blocking_reasons),
            audit_issues=(),
        )

    return RiskManagementOperationHealth(
        passed=True,
        health_status="healthy",
        operation_id=operation_id if isinstance(operation_id, str) else None,
        approved_count=approved_count,
        total_risk_exposure=float(total_risk_exposure),
        net_exposure=float(net_exposure),
        blocking_reasons=(),
        audit_issues=(),
    )


def enforce_risk_management_operation_health(
    record: RiskManagementOperationRecord | Mapping[str, Any],
) -> RiskManagementOperationHealth:
    health = evaluate_risk_management_operation_health(record)

    if not health.passed:
        reasons = health.audit_issues or health.blocking_reasons
        raise RiskManagementHealthGateError(
            "risk management health gate failed: " + "; ".join(reasons)
        )

    return health


def _record_to_dict(
    record: RiskManagementOperationRecord | Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()

    if isinstance(record, Mapping):
        return dict(record)

    raise TypeError("record must be a RiskManagementOperationRecord or mapping")
