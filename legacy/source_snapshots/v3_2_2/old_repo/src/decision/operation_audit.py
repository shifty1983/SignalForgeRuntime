from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.decision.operation_record import DecisionOperationRecord


@dataclass(frozen=True)
class DecisionOperationAuditResult:
    passed: bool
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": list(self.failures),
        }


def audit_decision_operation_record(
    record: DecisionOperationRecord,
) -> DecisionOperationAuditResult:
    failures: list[str] = []

    if not record.operation_id:
        failures.append("operation_id_missing")

    if record.operation_type != "decision_dry_run":
        failures.append("invalid_operation_type")

    report = record.attachments.get("decision_report")
    if not report:
        failures.append("decision_report_missing")
    else:
        if not report.get("decision_id"):
            failures.append("decision_id_missing")

        if report.get("candidate_count", 0) <= 0:
            failures.append("candidate_count_invalid")

        if report.get("selected_count", 0) <= 0:
            failures.append("selected_count_invalid")

        if not report.get("selected_symbols"):
            failures.append("selected_symbols_missing")

        if report.get("selection_score") is None:
            failures.append("selection_score_missing")

        if report.get("ranking_available") is not True:
            failures.append("ranking_missing")

    return DecisionOperationAuditResult(
        passed=not failures,
        failures=tuple(failures),
    )
