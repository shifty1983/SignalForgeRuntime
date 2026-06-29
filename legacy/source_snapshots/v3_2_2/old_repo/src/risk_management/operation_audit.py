from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from src.risk_management.operation_record import (
    RISK_MANAGEMENT_OPERATION_RECORD_SCHEMA_VERSION,
    RISK_MANAGEMENT_OPERATION_TYPE,
    RiskManagementOperationRecord,
)


REQUIRED_OPERATION_RECORD_FIELDS = (
    "operation_id",
    "operation_type",
    "schema_version",
    "status",
    "passed",
    "risk_status",
    "candidate_count",
    "eligible_count",
    "rejected_count",
    "approved_count",
    "approved_candidate_ids",
    "rejected_candidate_ids",
    "total_risk_exposure",
    "long_exposure",
    "short_exposure",
    "net_exposure",
    "blocking_reasons",
    "metadata",
    "risk_report",
)


@dataclass(frozen=True)
class RiskManagementOperationAuditReport:
    passed: bool
    operation_id: str | None
    operation_type: str | None
    issue_count: int
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "issue_count": self.issue_count,
            "issues": list(self.issues),
        }


def audit_risk_management_operation_record(
    record: RiskManagementOperationRecord | Mapping[str, Any],
) -> RiskManagementOperationAuditReport:
    payload = _record_to_dict(record)
    issues: list[str] = []

    for field in REQUIRED_OPERATION_RECORD_FIELDS:
        if field not in payload:
            issues.append(f"missing required field: {field}")

    operation_id = payload.get("operation_id")
    operation_type = payload.get("operation_type")

    if operation_type != RISK_MANAGEMENT_OPERATION_TYPE:
        issues.append(f"invalid operation_type: {operation_type!r}")

    schema_version = payload.get("schema_version")
    if schema_version != RISK_MANAGEMENT_OPERATION_RECORD_SCHEMA_VERSION:
        issues.append(f"invalid schema_version: {schema_version!r}")

    _audit_counts(payload, issues)
    _audit_exposures(payload, issues)
    _audit_status_consistency(payload, issues)
    _audit_risk_report(payload, issues)

    return RiskManagementOperationAuditReport(
        passed=not issues,
        operation_id=operation_id if isinstance(operation_id, str) else None,
        operation_type=operation_type if isinstance(operation_type, str) else None,
        issue_count=len(issues),
        issues=tuple(issues),
    )


def _audit_counts(
    payload: Mapping[str, Any],
    issues: list[str],
) -> None:
    count_fields = (
        "candidate_count",
        "eligible_count",
        "rejected_count",
        "approved_count",
    )

    for field in count_fields:
        if field in payload and not _non_negative_int(payload[field]):
            issues.append(f"invalid count field: {field}")

    candidate_count = payload.get("candidate_count")
    eligible_count = payload.get("eligible_count")
    rejected_count = payload.get("rejected_count")
    approved_count = payload.get("approved_count")

    if all(
        _non_negative_int(value)
        for value in (candidate_count, eligible_count, rejected_count)
    ):
        if candidate_count != eligible_count + rejected_count:
            issues.append(
                "candidate_count must equal eligible_count + rejected_count"
            )

    if _non_negative_int(approved_count) and _non_negative_int(eligible_count):
        if approved_count > eligible_count:
            issues.append("approved_count must not exceed eligible_count")

    approved_candidate_ids = payload.get("approved_candidate_ids")
    rejected_candidate_ids = payload.get("rejected_candidate_ids")

    if isinstance(approved_candidate_ids, list) and _non_negative_int(approved_count):
        if approved_count != len(approved_candidate_ids):
            issues.append(
                "approved_count must equal len(approved_candidate_ids)"
            )

    if isinstance(approved_candidate_ids, list) and isinstance(
        rejected_candidate_ids,
        list,
    ):
        overlap = set(approved_candidate_ids).intersection(rejected_candidate_ids)
        if overlap:
            issues.append(
                "approved_candidate_ids must not overlap rejected_candidate_ids"
            )


def _audit_exposures(
    payload: Mapping[str, Any],
    issues: list[str],
) -> None:
    exposure_fields = (
        "total_risk_exposure",
        "long_exposure",
        "short_exposure",
        "net_exposure",
    )

    for field in exposure_fields:
        if field in payload and not _valid_number(payload[field]):
            issues.append(f"invalid exposure field: {field}")

    total_risk_exposure = payload.get("total_risk_exposure")
    long_exposure = payload.get("long_exposure")
    short_exposure = payload.get("short_exposure")
    net_exposure = payload.get("net_exposure")

    if all(
        _valid_number(value)
        for value in (
            total_risk_exposure,
            long_exposure,
            short_exposure,
            net_exposure,
        )
    ):
        if round(long_exposure + short_exposure, 10) != total_risk_exposure:
            issues.append(
                "total_risk_exposure must equal long_exposure + short_exposure"
            )

        if round(long_exposure - short_exposure, 10) != net_exposure:
            issues.append(
                "net_exposure must equal long_exposure - short_exposure"
            )


def _audit_status_consistency(
    payload: Mapping[str, Any],
    issues: list[str],
) -> None:
    passed = payload.get("passed")
    status = payload.get("status")
    risk_status = payload.get("risk_status")
    approved_count = payload.get("approved_count")
    blocking_reasons = payload.get("blocking_reasons")

    if not isinstance(passed, bool):
        issues.append("passed must be a boolean")
        return

    if passed:
        if status != "completed":
            issues.append("passed operation must have status completed")

        if risk_status != "approved":
            issues.append("passed operation must have risk_status approved")

        if approved_count == 0:
            issues.append(
                "passed operation must have at least one approved candidate"
            )

        if blocking_reasons:
            issues.append("passed operation must not have blocking_reasons")

    else:
        if status not in {"blocked", "failed"}:
            issues.append("failed operation must have status blocked or failed")

        if approved_count != 0:
            issues.append("failed operation must not have approved candidates")


def _audit_risk_report(
    payload: Mapping[str, Any],
    issues: list[str],
) -> None:
    risk_report = payload.get("risk_report")

    if not isinstance(risk_report, Mapping):
        issues.append("risk_report must be a mapping")
        return

    for field in (
        "passed",
        "risk_status",
        "candidate_count",
        "eligible_count",
        "rejected_count",
        "approved_count",
        "approved_candidate_ids",
        "rejected_candidate_ids",
        "total_risk_exposure",
        "long_exposure",
        "short_exposure",
        "net_exposure",
        "candidate_summaries",
        "blocking_reasons",
    ):
        if field not in risk_report:
            issues.append(f"risk_report missing required field: {field}")


def _record_to_dict(
    record: RiskManagementOperationRecord | Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()

    if isinstance(record, Mapping):
        return dict(record)

    raise TypeError("record must be a RiskManagementOperationRecord or mapping")


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )
