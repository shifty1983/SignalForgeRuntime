from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.decision.operation_audit import audit_decision_operation_record
from src.decision.operation_record import DecisionOperationRecord


@dataclass(frozen=True)
class DecisionOperationHealth:
    passed: bool
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": list(self.failures),
        }


def evaluate_decision_operation_health(
    record: DecisionOperationRecord,
) -> DecisionOperationHealth:
    failures: list[str] = []

    if record.status != "completed":
        failures.append("operation_not_completed")

    audit = audit_decision_operation_record(record)
    failures.extend(audit.failures)

    return DecisionOperationHealth(
        passed=not failures,
        failures=tuple(failures),
    )
