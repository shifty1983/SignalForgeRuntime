from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from os import PathLike
from typing import Any

from src.strategy_selection.evaluator import (
    StrategySelectionEvaluationReport,
    evaluate_strategy_candidates,
)
from src.strategy_selection.operation_audit import (
    StrategySelectionOperationAuditReport,
    audit_strategy_selection_operation_record,
)
from src.strategy_selection.operation_health import (
    StrategySelectionOperationHealth,
    enforce_strategy_selection_operation_health,
    evaluate_strategy_selection_operation_health,
)
from src.strategy_selection.operation_log import (
    append_strategy_selection_operation_record,
)
from src.strategy_selection.operation_record import (
    StrategySelectionOperationRecord,
    build_strategy_selection_operation_record,
)
from src.strategy_selection.research_adapter import (
    adapt_research_backtest_to_strategy_candidates,
)
from src.strategy_selection.selection_report import (
    StrategySelectionReport,
    build_strategy_selection_report,
)
from src.strategy_selection.option_behavior_adapter import (
    attach_option_behavior_to_strategy_handoff,
)


@dataclass(frozen=True)
class StrategySelectionOperationRunResult:
    operation_id: str
    candidate_rows: tuple[Mapping[str, Any], ...]
    evaluation_report: StrategySelectionEvaluationReport
    selection_report: StrategySelectionReport
    operation_record: StrategySelectionOperationRecord
    audit_report: StrategySelectionOperationAuditReport
    health: StrategySelectionOperationHealth
    log_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "candidate_rows": [
                dict(row)
                for row in self.candidate_rows
            ],
            "evaluation_report": self.evaluation_report.to_dict(),
            "selection_report": self.selection_report.to_dict(),
            "operation_record": self.operation_record.to_dict(),
            "audit_report": self.audit_report.to_dict(),
            "health": self.health.to_dict(),
            "log_path": self.log_path,
        }


def run_strategy_selection_operation(
    handoff_result: Any,
    *,
    operation_id: str,
    max_selected_candidates: int = 1,
    metadata: Mapping[str, Any] | None = None,
    option_behavior_handoffs: Any | None = None,
    require_option_behavior: bool = False,
    log_path: str | PathLike[str] | None = None,
    enforce_health_gate: bool = True,
) -> StrategySelectionOperationRunResult:
    """
    Run the full strategy-selection operation lifecycle.

    This composes the existing contracts only:

    accepted handoff
    -> optional option behavior enrichment
    -> strategy candidate rows
    -> candidate evaluation
    -> selection report
    -> operation record
    -> optional JSONL persistence
    -> audit
    -> health gate

    It does not optimize weights, construct portfolios, generate orders, or
    execute trades.
    """

    strategy_handoff = attach_option_behavior_to_strategy_handoff(
        handoff_result=handoff_result,
        option_behavior_handoffs=option_behavior_handoffs,
        require_option_behavior=require_option_behavior,
    )

    candidate_rows = tuple(
        adapt_research_backtest_to_strategy_candidates(strategy_handoff)
    )

    evaluation_report = evaluate_strategy_candidates(candidate_rows)

    selection_report = build_strategy_selection_report(
        evaluation_report,
        max_selected_candidates=max_selected_candidates,
    )

    operation_metadata = _operation_metadata(
        handoff_result=strategy_handoff,
        metadata=metadata,
    )

    operation_record = build_strategy_selection_operation_record(
        selection_report,
        operation_id=operation_id,
        metadata=operation_metadata,
    )

    persisted_log_path = None

    if log_path is not None:
        persisted_path = append_strategy_selection_operation_record(
            operation_record,
            log_path,
        )
        persisted_log_path = str(persisted_path)

    audit_report = audit_strategy_selection_operation_record(operation_record)
    health = evaluate_strategy_selection_operation_health(operation_record)

    if enforce_health_gate:
        enforce_strategy_selection_operation_health(operation_record)

    return StrategySelectionOperationRunResult(
        operation_id=operation_id,
        candidate_rows=candidate_rows,
        evaluation_report=evaluation_report,
        selection_report=selection_report,
        operation_record=operation_record,
        audit_report=audit_report,
        health=health,
        log_path=persisted_log_path,
    )


def _operation_metadata(
    *,
    handoff_result: Any,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_metadata = _metadata_from_handoff(handoff_result)
    return {
        **source_metadata,
        **dict(metadata or {}),
    }


def _metadata_from_handoff(handoff_result: Any) -> dict[str, Any]:
    payload = _to_plain_object(handoff_result)

    if not isinstance(payload, Mapping):
        return {}

    for field_name in ("handoff_metadata", "metadata"):
        value = payload.get(field_name)
        if isinstance(value, Mapping):
            return dict(value)

    return {}


def _to_plain_object(source: Any) -> Any:
    if is_dataclass(source):
        return asdict(source)

    return source
