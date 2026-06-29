from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from os import PathLike
from typing import Any

from src.risk_management.evaluator import (
    RiskManagementEvaluationReport,
    evaluate_risk_management_candidates,
)
from src.risk_management.operation_audit import (
    RiskManagementOperationAuditReport,
    audit_risk_management_operation_record,
)
from src.risk_management.operation_health import (
    RiskManagementOperationHealth,
    enforce_risk_management_operation_health,
    evaluate_risk_management_operation_health,
)
from src.risk_management.operation_log import append_risk_management_operation_record
from src.risk_management.operation_record import (
    RiskManagementOperationRecord,
    build_risk_management_operation_record,
)
from src.risk_management.portfolio_adapter import (
    adapt_portfolio_construction_to_risk_inputs,
)
from src.risk_management.risk_report import (
    RiskManagementReport,
    build_risk_management_report,
)


@dataclass(frozen=True)
class RiskManagementOperationRunResult:
    operation_id: str
    risk_input_rows: tuple[Mapping[str, Any], ...]
    evaluation_report: RiskManagementEvaluationReport
    risk_report: RiskManagementReport
    operation_record: RiskManagementOperationRecord
    audit_report: RiskManagementOperationAuditReport
    health: RiskManagementOperationHealth
    log_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "risk_input_rows": [
                dict(row)
                for row in self.risk_input_rows
            ],
            "evaluation_report": self.evaluation_report.to_dict(),
            "risk_report": self.risk_report.to_dict(),
            "operation_record": self.operation_record.to_dict(),
            "audit_report": self.audit_report.to_dict(),
            "health": self.health.to_dict(),
            "log_path": self.log_path,
        }


def run_risk_management_operation(
    portfolio_construction_result: Any,
    *,
    operation_id: str,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | PathLike[str] | None = None,
    enforce_health_gate: bool = True,
) -> RiskManagementOperationRunResult:
    """
    Run the full risk-management operation lifecycle.

    This composes existing contracts only:

    portfolio construction result
    -> risk management input rows
    -> risk candidate evaluation
    -> risk report
    -> operation record
    -> optional JSONL persistence
    -> audit
    -> health gate

    It does not apply portfolio-level risk limits, concentration limits,
    position resizing, stop rules, order generation, or execution.
    """
    risk_input_rows = tuple(
        adapt_portfolio_construction_to_risk_inputs(
            portfolio_construction_result
        )
    )

    evaluation_report = evaluate_risk_management_candidates(risk_input_rows)

    risk_report = build_risk_management_report(evaluation_report)

    operation_metadata = _operation_metadata(
        portfolio_construction_result=portfolio_construction_result,
        metadata=metadata,
    )

    operation_record = build_risk_management_operation_record(
        risk_report,
        operation_id=operation_id,
        metadata=operation_metadata,
    )

    persisted_log_path = None

    if log_path is not None:
        persisted_path = append_risk_management_operation_record(
            operation_record,
            log_path,
        )
        persisted_log_path = str(persisted_path)

    audit_report = audit_risk_management_operation_record(operation_record)
    health = evaluate_risk_management_operation_health(operation_record)

    if enforce_health_gate:
        enforce_risk_management_operation_health(operation_record)

    return RiskManagementOperationRunResult(
        operation_id=operation_id,
        risk_input_rows=risk_input_rows,
        evaluation_report=evaluation_report,
        risk_report=risk_report,
        operation_record=operation_record,
        audit_report=audit_report,
        health=health,
        log_path=persisted_log_path,
    )


def _operation_metadata(
    *,
    portfolio_construction_result: Any,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_metadata = _metadata_from_portfolio_construction_result(
        portfolio_construction_result
    )

    return {
        **source_metadata,
        **dict(metadata or {}),
    }


def _metadata_from_portfolio_construction_result(
    portfolio_construction_result: Any,
) -> dict[str, Any]:
    payload = _to_plain_object(portfolio_construction_result)

    if not isinstance(payload, Mapping):
        return {}

    operation_record = payload.get("operation_record")

    metadata: dict[str, Any] = {}

    portfolio_construction_operation_id = payload.get("operation_id")
    if isinstance(operation_record, Mapping):
        portfolio_construction_operation_id = operation_record.get(
            "operation_id",
            portfolio_construction_operation_id,
        )

        record_metadata = operation_record.get("metadata")
        if isinstance(record_metadata, Mapping):
            metadata.update(dict(record_metadata))

    if isinstance(portfolio_construction_operation_id, str):
        metadata["portfolio_construction_operation_id"] = (
            portfolio_construction_operation_id
        )

    return metadata


def _to_plain_object(source: Any) -> Any:
    if hasattr(source, "to_dict"):
        return source.to_dict()

    if is_dataclass(source):
        return asdict(source)

    return source
