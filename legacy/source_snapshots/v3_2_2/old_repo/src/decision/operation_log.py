from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.decision.operation_record import DecisionOperationRecord


@dataclass(frozen=True)
class DecisionOperationLogEntry:
    operation_id: str
    operation_type: str
    status: str
    decision_id: str | None
    selected_symbols: tuple[str, ...]
    selected_count: int
    selection_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "decision_id": self.decision_id,
            "selected_symbols": list(self.selected_symbols),
            "selected_count": self.selected_count,
            "selection_score": self.selection_score,
        }


def build_decision_operation_log_entry(
    record: DecisionOperationRecord,
) -> DecisionOperationLogEntry:
    report = record.attachments.get("decision_report", {})

    return DecisionOperationLogEntry(
        operation_id=record.operation_id,
        operation_type=record.operation_type,
        status=record.status,
        decision_id=report.get("decision_id"),
        selected_symbols=tuple(report.get("selected_symbols", [])),
        selected_count=int(report.get("selected_count", 0)),
        selection_score=report.get("selection_score"),
    )


def append_decision_operation_log(
    *,
    entry: DecisionOperationLogEntry,
    log_path: str | Path,
) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
