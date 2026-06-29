# src/backtesting/historical_research_final_review_pipeline_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "pipeline_status",
    "source_pipeline_type",
    "source_pipeline_id",
    "source_pipeline_name",
    "pipeline_runner_status",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "warnings",
    "blocked_reasons",
    "pipeline_summary",
    "final_review_pipeline",
    "pipeline_metadata",
    "metadata",
}


def audit_historical_research_final_review_pipeline_record(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    audit_errors: list[str] = []
    audit_warnings: list[str] = []

    missing_fields = sorted(
        REQUIRED_OPERATION_RECORD_FIELDS - set(operation_record.keys())
    )
    if missing_fields:
        audit_errors.append(
            f"operation_record missing required fields: {missing_fields}"
        )

    operation_type = operation_record.get("operation_type")
    if operation_type != "historical_research_final_review_pipeline_operation":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    source_pipeline_type = operation_record.get("source_pipeline_type")
    if source_pipeline_type != "historical_research_final_review_pipeline":
        audit_errors.append(
            f"operation_record invalid source_pipeline_type: {source_pipeline_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    pipeline_status = operation_record.get("pipeline_status")
    if pipeline_status not in {"ready", "needs_review", "blocked"}:
        audit_errors.append(
            f"operation_record invalid pipeline_status: {pipeline_status}"
        )

    pipeline_runner_status = operation_record.get("pipeline_runner_status")
    if pipeline_runner_status not in {"completed", "blocked"}:
        audit_errors.append(
            "operation_record invalid pipeline_runner_status: "
            f"{pipeline_runner_status}"
        )

    if not isinstance(operation_record.get("is_ready"), bool):
        audit_errors.append("operation_record is_ready must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    pipeline_summary = operation_record.get("pipeline_summary", {})
    if not isinstance(pipeline_summary, Mapping):
        audit_errors.append("operation_record pipeline_summary must be a mapping")
        pipeline_summary = {}

    final_review_pipeline = operation_record.get("final_review_pipeline", {})
    if not isinstance(final_review_pipeline, Mapping):
        audit_errors.append("operation_record final_review_pipeline must be a mapping")
        final_review_pipeline = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if pipeline_status == "ready" and operation_record.get("is_ready") is not True:
        audit_errors.append(
            "operation_record ready pipeline conflicts with is_ready=False"
        )

    if pipeline_status != "ready" and operation_record.get("is_ready") is True:
        audit_errors.append(
            "operation_record non-ready pipeline conflicts with is_ready=True"
        )

    if pipeline_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked pipeline_status must have blocked operation_status"
        )

    ready_count = int(pipeline_summary.get("ready_count", 0))
    needs_review_count = int(pipeline_summary.get("needs_review_count", 0))
    blocked_count = int(pipeline_summary.get("blocked_count", 0))
    total_count = int(pipeline_summary.get("total_count", 0))

    if total_count != ready_count + needs_review_count + blocked_count:
        audit_errors.append(
            "operation_record pipeline_summary total_count does not match component counts"
        )

    if pipeline_status == "ready" and ready_count <= 0:
        audit_warnings.append("operation_record ready pipeline has no ready payloads")

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    if operation_status == "completed" and blocked_count > 0:
        audit_warnings.append("operation_record completed with blocked payloads")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "pipeline_status": pipeline_status,
            "source_pipeline_type": source_pipeline_type,
            "pipeline_runner_status": pipeline_runner_status,
            "is_ready": operation_record.get("is_ready"),
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors)
            if isinstance(validation_errors, list)
            else 0,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "blocked_reason_count": len(blocked_reasons)
            if isinstance(blocked_reasons, list)
            else 0,
            "ready_count": ready_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
    }
