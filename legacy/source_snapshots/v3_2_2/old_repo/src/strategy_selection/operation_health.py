from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.signalforge.engines.strategy_selection.operation_audit import (
    audit_strategy_selection_operation_record,
)
from src.signalforge.engines.strategy_selection.operation_record import StrategySelectionOperationRecord


class StrategySelectionHealthGateError(RuntimeError):
    """Raised when strategy-selection operation health gate fails."""


@dataclass(frozen=True)
class StrategySelectionOperationHealth:
    passed: bool
    health_status: str
    operation_id: str | None
    selected_count: int
    blocking_reasons: tuple[str, ...]
    audit_issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "health_status": self.health_status,
            "operation_id": self.operation_id,
            "selected_count": self.selected_count,
            "blocking_reasons": list(self.blocking_reasons),
            "audit_issues": list(self.audit_issues),
        }


def evaluate_strategy_selection_operation_health(
    record: StrategySelectionOperationRecord | Mapping[str, Any],
) -> StrategySelectionOperationHealth:
    payload = _record_to_dict(record)
    audit_report = audit_strategy_selection_operation_record(payload)

    operation_id = payload.get("operation_id")
    selected_count = payload.get("selected_count", 0)

    if not audit_report.passed:
        return StrategySelectionOperationHealth(
            passed=False,
            health_status="failed",
            operation_id=operation_id if isinstance(operation_id, str) else None,
            selected_count=selected_count if isinstance(selected_count, int) else 0,
            blocking_reasons=(),
            audit_issues=audit_report.issues,
        )

    if payload.get("passed") is not True:
        blocking_reasons = payload.get("blocking_reasons") or (
            "strategy selection operation blocked",
        )

        return StrategySelectionOperationHealth(
            passed=False,
            health_status="blocked",
            operation_id=operation_id if isinstance(operation_id, str) else None,
            selected_count=selected_count,
            blocking_reasons=tuple(blocking_reasons),
            audit_issues=(),
        )

    return StrategySelectionOperationHealth(
        passed=True,
        health_status="healthy",
        operation_id=operation_id if isinstance(operation_id, str) else None,
        selected_count=selected_count,
        blocking_reasons=(),
        audit_issues=(),
    )


def enforce_strategy_selection_operation_health(
    record: StrategySelectionOperationRecord | Mapping[str, Any],
) -> StrategySelectionOperationHealth:
    health = evaluate_strategy_selection_operation_health(record)

    if not health.passed:
        reasons = health.audit_issues or health.blocking_reasons
        raise StrategySelectionHealthGateError(
            "strategy selection health gate failed: " + "; ".join(reasons)
        )

    return health


def _record_to_dict(
    record: StrategySelectionOperationRecord | Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()

    if isinstance(record, Mapping):
        return dict(record)

    raise TypeError("record must be a StrategySelectionOperationRecord or mapping")
