# src/backtesting/historical_research_final_review_summary_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_research_final_review_summary"
SCHEMA_VERSION = "1.0"

REQUIRED_SUMMARY_FIELDS = {
    "summary_status",
    "is_ready",
    "is_blocked",
    "summary_type",
    "summary_name",
    "validation_errors",
    "ready_items",
    "needs_review_items",
    "blocked_items",
    "final_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}

VALID_SUMMARY_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_research_final_review_summary_record(
    final_review_summary: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary = dict(final_review_summary)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_summary_shape(summary)
    summary_validation_errors = [
        str(error)
        for error in summary.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *summary_validation_errors,
    ]

    summary_status = summary.get("summary_status")

    is_blocked = (
        bool(summary.get("is_blocked"))
        or summary_status == "blocked"
        or summary_status not in VALID_SUMMARY_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            final_review_summary=summary,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "summary_status": summary_status,
        "is_ready": bool(summary.get("is_ready")),
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "ready_items": list(summary.get("ready_items", [])),
        "needs_review_items": list(summary.get("needs_review_items", [])),
        "blocked_items": list(summary.get("blocked_items", [])),
        "final_counts": dict(summary.get("final_counts", {})),
        "warnings": list(summary.get("warnings", [])),
        "blocked_reasons": list(summary.get("blocked_reasons", [])),
        "explicit_exclusions": list(summary.get("explicit_exclusions", [])),
        "source_summary": dict(summary.get("source_summary", {})),
        "summary_metadata": dict(summary.get("metadata", {})),
        "matrix_metadata_summary": dict(summary.get("matrix_metadata_summary", {})),
        "exact_matrix_cell_ready_record_count": int(
            summary.get("exact_matrix_cell_ready_record_count", 0)
        ),
        "matrix_metadata_needs_review_record_count": int(
            summary.get("matrix_metadata_needs_review_record_count", 0)
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            summary.get("ready_to_build_exact_matrix_edge_summary", False)
        ),
        "recommended_next_step": summary.get("recommended_next_step"),
        "metadata": metadata_dict,
    }


def _validate_summary_shape(final_review_summary: Mapping[str, Any]) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_SUMMARY_FIELDS - set(final_review_summary.keys()))
    if missing_fields:
        validation_errors.append(
            f"final_review_summary missing required fields: {missing_fields}"
        )

    summary_status = final_review_summary.get("summary_status")
    if (
        summary_status is not None
        and summary_status not in VALID_SUMMARY_STATUSES
    ):
        validation_errors.append(
            f"final_review_summary invalid summary_status: {summary_status}"
        )

    if "is_ready" in final_review_summary and not isinstance(
        final_review_summary["is_ready"],
        bool,
    ):
        validation_errors.append("final_review_summary is_ready must be a boolean")

    if "is_blocked" in final_review_summary and not isinstance(
        final_review_summary["is_blocked"],
        bool,
    ):
        validation_errors.append("final_review_summary is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "ready_items",
        "needs_review_items",
        "blocked_items",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in final_review_summary and not isinstance(
            final_review_summary[list_field],
            list,
        ):
            validation_errors.append(
                f"final_review_summary {list_field} must be a list"
            )

    for mapping_field in ["final_counts", "source_summary", "metadata"]:
        if mapping_field in final_review_summary and not isinstance(
            final_review_summary[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"final_review_summary {mapping_field} must be a mapping"
            )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    final_review_summary: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "final_review_summary": final_review_summary,
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
