from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from os import PathLike
from typing import Any

from src.portfolio_construction.construction_report import (
    PortfolioConstructionReport,
    build_portfolio_construction_report,
)
from src.portfolio_construction.evaluator import (
    PortfolioConstructionEvaluationReport,
    evaluate_portfolio_construction_candidates,
)
from src.portfolio_construction.operation_audit import (
    PortfolioConstructionOperationAuditReport,
    audit_portfolio_construction_operation_record,
)
from src.portfolio_construction.operation_health import (
    PortfolioConstructionOperationHealth,
    enforce_portfolio_construction_operation_health,
    evaluate_portfolio_construction_operation_health,
)
from src.portfolio_construction.operation_log import (
    append_portfolio_construction_operation_record,
)
from src.portfolio_construction.operation_record import (
    PortfolioConstructionOperationRecord,
    build_portfolio_construction_operation_record,
)
from src.portfolio_construction.strategy_adapter import (
    adapt_strategy_selection_to_portfolio_inputs,
)


@dataclass(frozen=True)
class PortfolioConstructionOperationRunResult:
    operation_id: str
    portfolio_input_rows: tuple[Mapping[str, Any], ...]
    evaluation_report: PortfolioConstructionEvaluationReport
    construction_report: PortfolioConstructionReport
    operation_record: PortfolioConstructionOperationRecord
    audit_report: PortfolioConstructionOperationAuditReport
    health: PortfolioConstructionOperationHealth
    log_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "portfolio_input_rows": [
                dict(row)
                for row in self.portfolio_input_rows
            ],
            "evaluation_report": self.evaluation_report.to_dict(),
            "construction_report": self.construction_report.to_dict(),
            "operation_record": self.operation_record.to_dict(),
            "audit_report": self.audit_report.to_dict(),
            "health": self.health.to_dict(),
            "log_path": self.log_path,
        }


def run_portfolio_construction_operation(
    strategy_selection_result: Any,
    *,
    operation_id: str,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | PathLike[str] | None = None,
    enforce_health_gate: bool = True,
) -> PortfolioConstructionOperationRunResult:
    """
    Run the full portfolio-construction operation lifecycle.

    This composes existing contracts only:

    strategy selection result
    -> portfolio construction input rows
    -> portfolio candidate evaluation
    -> construction report
    -> operation record
    -> optional JSONL persistence
    -> audit
    -> health gate

    It does not optimize, resize, rebalance, generate orders, or execute trades.
    """
    portfolio_input_rows = tuple(
        adapt_strategy_selection_to_portfolio_inputs(
            strategy_selection_result
        )
    )

    evaluation_report = evaluate_portfolio_construction_candidates(
        portfolio_input_rows
    )

    construction_report = build_portfolio_construction_report(
        evaluation_report
    )

    operation_metadata = _operation_metadata(
        strategy_selection_result=strategy_selection_result,
        metadata=metadata,
    )

    operation_record = build_portfolio_construction_operation_record(
        construction_report,
        operation_id=operation_id,
        metadata=operation_metadata,
    )

    persisted_log_path = None

    if log_path is not None:
        persisted_path = append_portfolio_construction_operation_record(
            operation_record,
            log_path,
        )
        persisted_log_path = str(persisted_path)

    audit_report = audit_portfolio_construction_operation_record(
        operation_record
    )
    health = evaluate_portfolio_construction_operation_health(
        operation_record
    )

    if enforce_health_gate:
        enforce_portfolio_construction_operation_health(operation_record)

    return PortfolioConstructionOperationRunResult(
        operation_id=operation_id,
        portfolio_input_rows=portfolio_input_rows,
        evaluation_report=evaluation_report,
        construction_report=construction_report,
        operation_record=operation_record,
        audit_report=audit_report,
        health=health,
        log_path=persisted_log_path,
    )


def _operation_metadata(
    *,
    strategy_selection_result: Any,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_metadata = _metadata_from_strategy_selection_result(
        strategy_selection_result
    )

    return {
        **source_metadata,
        **dict(metadata or {}),
    }


def _metadata_from_strategy_selection_result(
    strategy_selection_result: Any,
) -> dict[str, Any]:
    payload = _to_plain_object(strategy_selection_result)

    if not isinstance(payload, Mapping):
        return {}

    operation_record = payload.get("operation_record")

    metadata: dict[str, Any] = {}

    strategy_selection_operation_id = payload.get("operation_id")
    if isinstance(operation_record, Mapping):
        strategy_selection_operation_id = operation_record.get(
            "operation_id",
            strategy_selection_operation_id,
        )

        record_metadata = operation_record.get("metadata")
        if isinstance(record_metadata, Mapping):
            metadata.update(dict(record_metadata))

    if isinstance(strategy_selection_operation_id, str):
        metadata["strategy_selection_operation_id"] = (
            strategy_selection_operation_id
        )

    return metadata


def _to_plain_object(source: Any) -> Any:
    if hasattr(source, "to_dict"):
        return source.to_dict()

    if is_dataclass(source):
        return asdict(source)

    return source
