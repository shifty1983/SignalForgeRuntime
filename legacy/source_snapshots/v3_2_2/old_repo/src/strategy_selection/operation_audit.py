from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.signalforge.engines.strategy_selection.operation_record import (
    STRATEGY_SELECTION_OPERATION_RECORD_SCHEMA_VERSION,
    STRATEGY_SELECTION_OPERATION_TYPE,
    StrategySelectionOperationRecord,
)


REQUIRED_OPERATION_RECORD_FIELDS = (
    "operation_id",
    "operation_type",
    "schema_version",
    "status",
    "passed",
    "selection_status",
    "candidate_count",
    "eligible_count",
    "rejected_count",
    "selected_count",
    "selected_candidate_ids",
    "ranked_candidate_ids",
    "rejected_candidate_ids",
    "blocking_reasons",
    "metadata",
    "selection_report",
)


@dataclass(frozen=True)
class StrategySelectionOperationAuditReport:
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


def audit_strategy_selection_operation_record(
    record: StrategySelectionOperationRecord | Mapping[str, Any],
) -> StrategySelectionOperationAuditReport:
    payload = _record_to_dict(record)
    issues: list[str] = []

    for field in REQUIRED_OPERATION_RECORD_FIELDS:
        if field not in payload:
            issues.append(f"missing required field: {field}")

    operation_id = payload.get("operation_id")
    operation_type = payload.get("operation_type")

    if operation_type != STRATEGY_SELECTION_OPERATION_TYPE:
        issues.append(f"invalid operation_type: {operation_type!r}")

    schema_version = payload.get("schema_version")
    if schema_version != STRATEGY_SELECTION_OPERATION_RECORD_SCHEMA_VERSION:
        issues.append(f"invalid schema_version: {schema_version!r}")

    _audit_counts(payload, issues)
    _audit_status_consistency(payload, issues)
    _audit_selection_report(payload, issues)

    return StrategySelectionOperationAuditReport(
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
        "selected_count",
    )

    for field in count_fields:
        if field in payload and not _non_negative_int(payload[field]):
            issues.append(f"invalid count field: {field}")

    candidate_count = payload.get("candidate_count")
    eligible_count = payload.get("eligible_count")
    rejected_count = payload.get("rejected_count")
    selected_count = payload.get("selected_count")

    if all(
        _non_negative_int(value)
        for value in (candidate_count, eligible_count, rejected_count)
    ):
        if candidate_count != eligible_count + rejected_count:
            issues.append(
                "candidate_count must equal eligible_count + rejected_count"
            )

    selected_candidate_ids = payload.get("selected_candidate_ids")
    ranked_candidate_ids = payload.get("ranked_candidate_ids")
    rejected_candidate_ids = payload.get("rejected_candidate_ids")

    if isinstance(selected_candidate_ids, list) and _non_negative_int(selected_count):
        if selected_count != len(selected_candidate_ids):
            issues.append(
                "selected_count must equal len(selected_candidate_ids)"
            )

    if isinstance(selected_candidate_ids, list) and isinstance(ranked_candidate_ids, list):
        missing_ranked = [
            candidate_id
            for candidate_id in selected_candidate_ids
            if candidate_id not in ranked_candidate_ids
        ]
        if missing_ranked:
            issues.append(
                "selected_candidate_ids must be contained in ranked_candidate_ids"
            )

    if isinstance(rejected_candidate_ids, list) and isinstance(ranked_candidate_ids, list):
        overlap = set(rejected_candidate_ids).intersection(ranked_candidate_ids)
        if overlap:
            issues.append(
                "rejected_candidate_ids must not overlap ranked_candidate_ids"
            )


def _audit_status_consistency(
    payload: Mapping[str, Any],
    issues: list[str],
) -> None:
    passed = payload.get("passed")
    status = payload.get("status")
    selection_status = payload.get("selection_status")
    selected_count = payload.get("selected_count")
    blocking_reasons = payload.get("blocking_reasons")

    if not isinstance(passed, bool):
        issues.append("passed must be a boolean")
        return

    if passed:
        if status != "completed":
            issues.append("passed operation must have status completed")

        if selection_status != "selected":
            issues.append("passed operation must have selection_status selected")

        if selected_count == 0:
            issues.append("passed operation must have at least one selected candidate")

        if blocking_reasons:
            issues.append("passed operation must not have blocking_reasons")

    else:
        if status not in {"blocked", "failed"}:
            issues.append("failed operation must have status blocked or failed")

        if selected_count != 0:
            issues.append("failed operation must not have selected candidates")


def _audit_selection_report(
    payload: Mapping[str, Any],
    issues: list[str],
) -> None:
    selection_report = payload.get("selection_report")

    if not isinstance(selection_report, Mapping):
        issues.append("selection_report must be a mapping")
        return

    for field in (
        "passed",
        "selection_status",
        "candidate_count",
        "eligible_count",
        "rejected_count",
        "selected_count",
        "selected_candidate_ids",
        "ranked_candidate_ids",
        "rejected_candidate_ids",
        "candidate_summaries",
        "blocking_reasons",
    ):
        if field not in selection_report:
            issues.append(f"selection_report missing required field: {field}")


def _record_to_dict(
    record: StrategySelectionOperationRecord | Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()

    if isinstance(record, Mapping):
        return dict(record)

    raise TypeError("record must be a StrategySelectionOperationRecord or mapping")


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
