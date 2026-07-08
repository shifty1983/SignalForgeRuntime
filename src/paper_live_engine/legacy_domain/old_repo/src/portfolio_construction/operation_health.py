from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.portfolio_construction.operation_audit import (
    audit_portfolio_construction_operation_record,
)
from src.portfolio_construction.operation_record import (
    PortfolioConstructionOperationRecord,
)


class PortfolioConstructionHealthGateError(RuntimeError):
    """Raised when portfolio construction operation health gate fails."""


@dataclass(frozen=True)
class PortfolioConstructionOperationHealth:
    passed: bool
    health_status: str
    operation_id: str | None
    accepted_count: int
    total_target_exposure: float
    net_exposure: float
    blocking_reasons: tuple[str, ...]
    audit_issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "health_status": self.health_status,
            "operation_id": self.operation_id,
            "accepted_count": self.accepted_count,
            "total_target_exposure": self.total_target_exposure,
            "net_exposure": self.net_exposure,
            "blocking_reasons": list(self.blocking_reasons),
            "audit_issues": list(self.audit_issues),
        }


def evaluate_portfolio_construction_operation_health(
    record: PortfolioConstructionOperationRecord | Mapping[str, Any],
) -> PortfolioConstructionOperationHealth:
    payload = _record_to_dict(record)
    audit_report = audit_portfolio_construction_operation_record(payload)

    operation_id = payload.get("operation_id")
    accepted_count = payload.get("accepted_count", 0)
    total_target_exposure = payload.get("total_target_exposure", 0.0)
    net_exposure = payload.get("net_exposure", 0.0)

    if not audit_report.passed:
        return PortfolioConstructionOperationHealth(
            passed=False,
            health_status="failed",
            operation_id=operation_id if isinstance(operation_id, str) else None,
            accepted_count=accepted_count if isinstance(accepted_count, int) else 0,
            total_target_exposure=(
                float(total_target_exposure)
                if isinstance(total_target_exposure, (int, float))
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
            "portfolio construction operation blocked",
        )

        return PortfolioConstructionOperationHealth(
            passed=False,
            health_status="blocked",
            operation_id=operation_id if isinstance(operation_id, str) else None,
            accepted_count=accepted_count,
            total_target_exposure=float(total_target_exposure),
            net_exposure=float(net_exposure),
            blocking_reasons=tuple(blocking_reasons),
            audit_issues=(),
        )

    return PortfolioConstructionOperationHealth(
        passed=True,
        health_status="healthy",
        operation_id=operation_id if isinstance(operation_id, str) else None,
        accepted_count=accepted_count,
        total_target_exposure=float(total_target_exposure),
        net_exposure=float(net_exposure),
        blocking_reasons=(),
        audit_issues=(),
    )


def enforce_portfolio_construction_operation_health(
    record: PortfolioConstructionOperationRecord | Mapping[str, Any],
) -> PortfolioConstructionOperationHealth:
    health = evaluate_portfolio_construction_operation_health(record)

    if not health.passed:
        reasons = health.audit_issues or health.blocking_reasons
        raise PortfolioConstructionHealthGateError(
            "portfolio construction health gate failed: " + "; ".join(reasons)
        )

    return health


def _record_to_dict(
    record: PortfolioConstructionOperationRecord | Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()

    if isinstance(record, Mapping):
        return dict(record)

    raise TypeError(
        "record must be a PortfolioConstructionOperationRecord or mapping"
    )
