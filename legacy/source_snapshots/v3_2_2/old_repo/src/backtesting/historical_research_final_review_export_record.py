# src/backtesting/historical_research_final_review_export_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_research_final_review_export"
SCHEMA_VERSION = "1.0"

REQUIRED_EXPORT_FIELDS = {
    "export_status",
    "is_ready",
    "is_blocked",
    "export_type",
    "export_name",
    "validation_errors",
    "ready_final_review",
    "needs_review_final_review",
    "blocked_final_review",
    "export_summary",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}

VALID_EXPORT_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_research_final_review_export_record(
    final_review_export: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    export = dict(final_review_export)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_export_shape(export)
    export_validation_errors = [
        str(error)
        for error in export.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *export_validation_errors,
    ]

    export_status = export.get("export_status")

    is_blocked = (
        bool(export.get("is_blocked"))
        or export_status == "blocked"
        or export_status not in VALID_EXPORT_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            final_review_export=export,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "export_status": export_status,
        "is_ready": bool(export.get("is_ready")),
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "ready_final_review": list(export.get("ready_final_review", [])),
        "needs_review_final_review": list(
            export.get("needs_review_final_review", [])
        ),
        "blocked_final_review": list(export.get("blocked_final_review", [])),
        "export_summary": dict(export.get("export_summary", {})),
        "warnings": list(export.get("warnings", [])),
        "blocked_reasons": list(export.get("blocked_reasons", [])),
        "explicit_exclusions": list(export.get("explicit_exclusions", [])),
        "source_summary": dict(export.get("source_summary", {})),
        "export_metadata": dict(export.get("metadata", {})),
        "matrix_metadata_summary": dict(export.get("matrix_metadata_summary", {})),
        "exact_matrix_cell_ready_record_count": int(
            export.get("exact_matrix_cell_ready_record_count", 0)
        ),
        "matrix_metadata_needs_review_record_count": int(
            export.get("matrix_metadata_needs_review_record_count", 0)
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            export.get("ready_to_build_exact_matrix_edge_summary", False)
        ),
        "recommended_next_step": export.get("recommended_next_step"),
        "metadata": metadata_dict,
    }


def _validate_export_shape(final_review_export: Mapping[str, Any]) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_EXPORT_FIELDS - set(final_review_export.keys()))
    if missing_fields:
        validation_errors.append(
            f"final_review_export missing required fields: {missing_fields}"
        )

    export_status = final_review_export.get("export_status")
    if export_status is not None and export_status not in VALID_EXPORT_STATUSES:
        validation_errors.append(
            f"final_review_export invalid export_status: {export_status}"
        )

    if "is_ready" in final_review_export and not isinstance(
        final_review_export["is_ready"],
        bool,
    ):
        validation_errors.append("final_review_export is_ready must be a boolean")

    if "is_blocked" in final_review_export and not isinstance(
        final_review_export["is_blocked"],
        bool,
    ):
        validation_errors.append("final_review_export is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "ready_final_review",
        "needs_review_final_review",
        "blocked_final_review",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in final_review_export and not isinstance(
            final_review_export[list_field],
            list,
        ):
            validation_errors.append(
                f"final_review_export {list_field} must be a list"
            )

    for mapping_field in ["export_summary", "source_summary", "metadata"]:
        if mapping_field in final_review_export and not isinstance(
            final_review_export[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"final_review_export {mapping_field} must be a mapping"
            )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    final_review_export: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "final_review_export": final_review_export,
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
