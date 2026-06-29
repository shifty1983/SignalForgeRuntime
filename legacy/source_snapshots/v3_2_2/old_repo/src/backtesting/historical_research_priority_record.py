# src/backtesting/historical_research_priority_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_research_priority"
SCHEMA_VERSION = "1.0"

REQUIRED_PRIORITY_REPORT_FIELDS = {
    "report_status",
    "is_ready",
    "is_blocked",
    "report_type",
    "report_name",
    "validation_errors",
    "priority_candidates",
    "needs_review_candidates",
    "blocked_candidates",
    "priority_summary",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}

VALID_REPORT_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_research_priority_record(
    priority_report: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report = dict(priority_report)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_priority_report_shape(report)
    report_validation_errors = [
        str(error)
        for error in report.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *report_validation_errors,
    ]

    report_status = report.get("report_status")

    is_blocked = (
        bool(report.get("is_blocked"))
        or report_status == "blocked"
        or report_status not in VALID_REPORT_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            priority_report=report,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "report_status": report_status,
        "is_ready": bool(report.get("is_ready")),
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "priority_candidates": list(report.get("priority_candidates", [])),
        "needs_review_candidates": list(report.get("needs_review_candidates", [])),
        "blocked_candidates": list(report.get("blocked_candidates", [])),
        "priority_summary": dict(report.get("priority_summary", {})),
        "warnings": list(report.get("warnings", [])),
        "blocked_reasons": list(report.get("blocked_reasons", [])),
        "explicit_exclusions": list(report.get("explicit_exclusions", [])),
        "source_summary": dict(report.get("source_summary", {})),
        "report_metadata": dict(report.get("metadata", {})),
        "metadata": metadata_dict,
    }


def _validate_priority_report_shape(
    priority_report: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_PRIORITY_REPORT_FIELDS - set(priority_report.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"priority_report missing required fields: {missing_fields}"
        )

    report_status = priority_report.get("report_status")
    if report_status is not None and report_status not in VALID_REPORT_STATUSES:
        validation_errors.append(
            f"priority_report invalid report_status: {report_status}"
        )

    if "is_ready" in priority_report and not isinstance(
        priority_report["is_ready"],
        bool,
    ):
        validation_errors.append("priority_report is_ready must be a boolean")

    if "is_blocked" in priority_report and not isinstance(
        priority_report["is_blocked"],
        bool,
    ):
        validation_errors.append("priority_report is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "priority_candidates",
        "needs_review_candidates",
        "blocked_candidates",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in priority_report and not isinstance(
            priority_report[list_field],
            list,
        ):
            validation_errors.append(f"priority_report {list_field} must be a list")

    for mapping_field in [
        "priority_summary",
        "source_summary",
        "metadata",
    ]:
        if mapping_field in priority_report and not isinstance(
            priority_report[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"priority_report {mapping_field} must be a mapping"
            )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    priority_report: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "priority_report": priority_report,
        "metadata": metadata,
    }

    encoded_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    digest = hashlib.sha256(encoded_payload).hexdigest()[:16]

    return f"{OPERATION_TYPE}:{digest}"
