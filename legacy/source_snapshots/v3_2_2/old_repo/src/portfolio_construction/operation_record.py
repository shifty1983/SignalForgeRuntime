from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.portfolio_construction.construction_report import (
    PortfolioConstructionReport,
)


PORTFOLIO_CONSTRUCTION_OPERATION_TYPE = "portfolio_construction"
PORTFOLIO_CONSTRUCTION_OPERATION_RECORD_SCHEMA_VERSION = (
    "portfolio_construction_operation_record_v1"
)


@dataclass(frozen=True)
class PortfolioConstructionOperationRecord:
    operation_id: str
    operation_type: str
    schema_version: str
    status: str
    passed: bool
    construction_status: str
    candidate_count: int
    eligible_count: int
    rejected_count: int
    accepted_count: int
    accepted_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    total_target_exposure: float
    long_exposure: float
    short_exposure: float
    net_exposure: float
    blocking_reasons: tuple[str, ...]
    metadata: Mapping[str, Any]
    construction_report: PortfolioConstructionReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "schema_version": self.schema_version,
            "status": self.status,
            "passed": self.passed,
            "construction_status": self.construction_status,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "accepted_count": self.accepted_count,
            "accepted_candidate_ids": list(self.accepted_candidate_ids),
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "total_target_exposure": self.total_target_exposure,
            "long_exposure": self.long_exposure,
            "short_exposure": self.short_exposure,
            "net_exposure": self.net_exposure,
            "blocking_reasons": list(self.blocking_reasons),
            "metadata": dict(self.metadata),
            "construction_report": self.construction_report.to_dict(),
        }


def build_portfolio_construction_operation_record(
    construction_report: PortfolioConstructionReport,
    *,
    operation_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> PortfolioConstructionOperationRecord:
    """
    Build a JSON-safe operation record for a completed portfolio construction report.

    This does not persist logs, audit records, enforce health gates, optimize
    weights, rebalance portfolios, generate orders, or execute trades.
    """
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError("operation_id must be a non-empty string")

    return PortfolioConstructionOperationRecord(
        operation_id=operation_id,
        operation_type=PORTFOLIO_CONSTRUCTION_OPERATION_TYPE,
        schema_version=PORTFOLIO_CONSTRUCTION_OPERATION_RECORD_SCHEMA_VERSION,
        status=_operation_status(construction_report),
        passed=construction_report.passed,
        construction_status=construction_report.construction_status,
        candidate_count=construction_report.candidate_count,
        eligible_count=construction_report.eligible_count,
        rejected_count=construction_report.rejected_count,
        accepted_count=construction_report.accepted_count,
        accepted_candidate_ids=construction_report.accepted_candidate_ids,
        rejected_candidate_ids=construction_report.rejected_candidate_ids,
        total_target_exposure=construction_report.total_target_exposure,
        long_exposure=construction_report.long_exposure,
        short_exposure=construction_report.short_exposure,
        net_exposure=construction_report.net_exposure,
        blocking_reasons=construction_report.blocking_reasons,
        metadata=dict(metadata or {}),
        construction_report=construction_report,
    )


def _operation_status(
    construction_report: PortfolioConstructionReport,
) -> str:
    if construction_report.passed:
        return "completed"

    return "blocked"
