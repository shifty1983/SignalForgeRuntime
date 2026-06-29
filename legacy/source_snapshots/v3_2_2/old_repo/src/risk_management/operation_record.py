from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.risk_management.risk_report import RiskManagementReport


RISK_MANAGEMENT_OPERATION_TYPE = "risk_management"
RISK_MANAGEMENT_OPERATION_RECORD_SCHEMA_VERSION = (
    "risk_management_operation_record_v1"
)


@dataclass(frozen=True)
class RiskManagementOperationRecord:
    operation_id: str
    operation_type: str
    schema_version: str
    status: str
    passed: bool
    risk_status: str
    candidate_count: int
    eligible_count: int
    rejected_count: int
    approved_count: int
    approved_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    total_risk_exposure: float
    long_exposure: float
    short_exposure: float
    net_exposure: float
    blocking_reasons: tuple[str, ...]
    metadata: Mapping[str, Any]
    risk_report: RiskManagementReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "schema_version": self.schema_version,
            "status": self.status,
            "passed": self.passed,
            "risk_status": self.risk_status,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "approved_count": self.approved_count,
            "approved_candidate_ids": list(self.approved_candidate_ids),
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "total_risk_exposure": self.total_risk_exposure,
            "long_exposure": self.long_exposure,
            "short_exposure": self.short_exposure,
            "net_exposure": self.net_exposure,
            "blocking_reasons": list(self.blocking_reasons),
            "metadata": dict(self.metadata),
            "risk_report": self.risk_report.to_dict(),
        }


def build_risk_management_operation_record(
    risk_report: RiskManagementReport,
    *,
    operation_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> RiskManagementOperationRecord:
    """
    Build a JSON-safe operation record for a completed risk management report.

    This does not persist logs, audit records, enforce health gates, apply risk
    limits, resize positions, generate orders, or execute trades.
    """
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError("operation_id must be a non-empty string")

    return RiskManagementOperationRecord(
        operation_id=operation_id,
        operation_type=RISK_MANAGEMENT_OPERATION_TYPE,
        schema_version=RISK_MANAGEMENT_OPERATION_RECORD_SCHEMA_VERSION,
        status=_operation_status(risk_report),
        passed=risk_report.passed,
        risk_status=risk_report.risk_status,
        candidate_count=risk_report.candidate_count,
        eligible_count=risk_report.eligible_count,
        rejected_count=risk_report.rejected_count,
        approved_count=risk_report.approved_count,
        approved_candidate_ids=risk_report.approved_candidate_ids,
        rejected_candidate_ids=risk_report.rejected_candidate_ids,
        total_risk_exposure=risk_report.total_risk_exposure,
        long_exposure=risk_report.long_exposure,
        short_exposure=risk_report.short_exposure,
        net_exposure=risk_report.net_exposure,
        blocking_reasons=risk_report.blocking_reasons,
        metadata=dict(metadata or {}),
        risk_report=risk_report,
    )


def _operation_status(risk_report: RiskManagementReport) -> str:
    if risk_report.passed:
        return "completed"

    return "blocked"
