from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.strategy_selection.selection_report import StrategySelectionReport


STRATEGY_SELECTION_OPERATION_TYPE = "strategy_selection"
STRATEGY_SELECTION_OPERATION_RECORD_SCHEMA_VERSION = (
    "strategy_selection_operation_record_v1"
)


@dataclass(frozen=True)
class StrategySelectionOperationRecord:
    operation_id: str
    operation_type: str
    schema_version: str
    status: str
    passed: bool
    selection_status: str
    candidate_count: int
    eligible_count: int
    rejected_count: int
    selected_count: int
    selected_candidate_ids: tuple[str, ...]
    ranked_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    metadata: Mapping[str, Any]
    selection_report: StrategySelectionReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "schema_version": self.schema_version,
            "status": self.status,
            "passed": self.passed,
            "selection_status": self.selection_status,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "selected_count": self.selected_count,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "ranked_candidate_ids": list(self.ranked_candidate_ids),
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "blocking_reasons": list(self.blocking_reasons),
            "metadata": dict(self.metadata),
            "selection_report": self.selection_report.to_dict(),
        }


def build_strategy_selection_operation_record(
    selection_report: StrategySelectionReport,
    *,
    operation_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> StrategySelectionOperationRecord:
    """
    Build a JSON-safe operation record for a completed strategy-selection report.

    This does not persist logs, audit records, trigger health gates, optimize
    weights, or generate orders.
    """
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError("operation_id must be a non-empty string")

    return StrategySelectionOperationRecord(
        operation_id=operation_id,
        operation_type=STRATEGY_SELECTION_OPERATION_TYPE,
        schema_version=STRATEGY_SELECTION_OPERATION_RECORD_SCHEMA_VERSION,
        status=_operation_status(selection_report),
        passed=selection_report.passed,
        selection_status=selection_report.selection_status,
        candidate_count=selection_report.candidate_count,
        eligible_count=selection_report.eligible_count,
        rejected_count=selection_report.rejected_count,
        selected_count=selection_report.selected_count,
        selected_candidate_ids=selection_report.selected_candidate_ids,
        ranked_candidate_ids=selection_report.ranked_candidate_ids,
        rejected_candidate_ids=selection_report.rejected_candidate_ids,
        blocking_reasons=selection_report.blocking_reasons,
        metadata=dict(metadata or {}),
        selection_report=selection_report,
    )


def _operation_status(selection_report: StrategySelectionReport) -> str:
    if selection_report.passed:
        return "completed"

    return "blocked"
