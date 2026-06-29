from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.decision.decision_report import DecisionReport


@dataclass
class DecisionOperationRecord:
    operation_id: str
    operation_type: str = "decision_dry_run"
    status: str = "completed"
    attachments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "attachments": self.attachments,
            "metadata": self.metadata,
        }


def attach_decision_report(
    record: DecisionOperationRecord,
    report: DecisionReport,
) -> DecisionOperationRecord:
    record.attachments["decision_report"] = report.to_dict()
    return record
