# src/backtesting/historical_research_final_review_pipeline_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_research_final_review_pipeline_operation"
SOURCE_PIPELINE_TYPE = "historical_research_final_review_pipeline"
SCHEMA_VERSION = "1.0"

REQUIRED_PIPELINE_FIELDS = {
    "operation_type",
    "operation_name",
    "pipeline_id",
    "runner_status",
    "is_blocked",
    "final_review_summary_operation",
    "final_review_export_operation",
    "warnings",
    "blocked_reasons",
    "summary",
    "metadata",
}

VALID_RUNNER_STATUSES = {"completed", "blocked"}
VALID_PIPELINE_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_research_final_review_pipeline_record(
    final_review_pipeline_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    pipeline_result = dict(final_review_pipeline_result)
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_pipeline_result_shape(pipeline_result)
    pipeline_status = _derive_pipeline_status(pipeline_result)

    is_blocked = (
        bool(pipeline_result.get("is_blocked"))
        or pipeline_result.get("runner_status") == "blocked"
        or pipeline_status == "blocked"
        or bool(validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            final_review_pipeline_result=pipeline_result,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "pipeline_status": pipeline_status,
        "source_pipeline_type": pipeline_result.get("operation_type"),
        "source_pipeline_id": pipeline_result.get("pipeline_id"),
        "source_pipeline_name": pipeline_result.get("operation_name"),
        "pipeline_runner_status": pipeline_result.get("runner_status"),
        "is_ready": pipeline_status == "ready",
        "is_blocked": is_blocked,
        "validation_errors": validation_errors,
        "warnings": list(pipeline_result.get("warnings", [])),
        "blocked_reasons": list(pipeline_result.get("blocked_reasons", [])),
        "pipeline_summary": dict(pipeline_result.get("summary", {})),
        "final_review_pipeline": pipeline_result,
        "pipeline_metadata": dict(pipeline_result.get("metadata", {})),
        "metadata": metadata_dict,
    }


def _validate_pipeline_result_shape(
    final_review_pipeline_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_PIPELINE_FIELDS - set(final_review_pipeline_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"final_review_pipeline_result missing required fields: {missing_fields}"
        )

    operation_type = final_review_pipeline_result.get("operation_type")
    if operation_type is not None and operation_type != SOURCE_PIPELINE_TYPE:
        validation_errors.append(
            f"final_review_pipeline_result invalid operation_type: {operation_type}"
        )

    runner_status = final_review_pipeline_result.get("runner_status")
    if runner_status is not None and runner_status not in VALID_RUNNER_STATUSES:
        validation_errors.append(
            f"final_review_pipeline_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in final_review_pipeline_result and not isinstance(
        final_review_pipeline_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "final_review_pipeline_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "final_review_summary_operation",
        "final_review_export_operation",
        "summary",
        "metadata",
    ]:
        if mapping_field in final_review_pipeline_result and not isinstance(
            final_review_pipeline_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"final_review_pipeline_result {mapping_field} must be a mapping"
            )

    for list_field in ["warnings", "blocked_reasons"]:
        if list_field in final_review_pipeline_result and not isinstance(
            final_review_pipeline_result[list_field],
            list,
        ):
            validation_errors.append(
                f"final_review_pipeline_result {list_field} must be a list"
            )

    summary = final_review_pipeline_result.get("summary", {})
    if isinstance(summary, Mapping):
        summary_status = summary.get("summary_status")
        export_status = summary.get("export_status")

        if summary_status is not None and summary_status not in {
            "ready",
            "needs_review",
            "blocked",
        }:
            validation_errors.append(
                f"final_review_pipeline_result invalid summary_status: {summary_status}"
            )

        if export_status is not None and export_status not in {
            "ready",
            "needs_review",
            "blocked",
        }:
            validation_errors.append(
                f"final_review_pipeline_result invalid export_status: {export_status}"
            )

    return validation_errors


def _derive_pipeline_status(
    final_review_pipeline_result: Mapping[str, Any],
) -> str:
    summary = final_review_pipeline_result.get("summary", {})
    if not isinstance(summary, Mapping):
        return "blocked"

    summary_status = summary.get("summary_status")
    export_status = summary.get("export_status")

    if (
        final_review_pipeline_result.get("is_blocked") is True
        or final_review_pipeline_result.get("runner_status") == "blocked"
        or summary_status == "blocked"
        or export_status == "blocked"
    ):
        return "blocked"

    if (
        summary_status == "needs_review"
        or export_status == "needs_review"
        or bool(final_review_pipeline_result.get("warnings"))
    ):
        return "needs_review"

    return "ready"


def _stable_operation_id(
    *,
    operation_name: str,
    final_review_pipeline_result: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "final_review_pipeline_result": final_review_pipeline_result,
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
