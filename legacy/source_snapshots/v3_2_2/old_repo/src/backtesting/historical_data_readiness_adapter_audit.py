# src/backtesting/historical_data_readiness_adapter_audit.py

from __future__ import annotations

from typing import Any, Mapping

from src.backtesting.historical_data_readiness_adapter import EXPLICIT_EXCLUSIONS


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "adapter_status",
    "source_adapter_type",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "warnings",
    "blocked_reasons",
    "candidate_rows",
    "price_rows",
    "readiness_summary",
    "explicit_exclusions",
    "adapter_metadata",
    "metadata",
}


def audit_historical_data_readiness_adapter_record(
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
    if operation_type != "historical_data_readiness_adapter_operation":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    source_adapter_type = operation_record.get("source_adapter_type")
    if source_adapter_type != "historical_data_readiness_adapter":
        audit_errors.append(
            f"operation_record invalid source_adapter_type: {source_adapter_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    adapter_status = operation_record.get("adapter_status")
    if adapter_status not in {"ready", "needs_review", "blocked"}:
        audit_errors.append(f"operation_record invalid adapter_status: {adapter_status}")

    if not isinstance(operation_record.get("is_ready"), bool):
        audit_errors.append("operation_record is_ready must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])
    candidate_rows = operation_record.get("candidate_rows", [])
    price_rows = operation_record.get("price_rows", [])
    explicit_exclusions = operation_record.get("explicit_exclusions", [])

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
        ("candidate_rows", candidate_rows),
        ("price_rows", price_rows),
        ("explicit_exclusions", explicit_exclusions),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    if isinstance(explicit_exclusions, list) and explicit_exclusions != EXPLICIT_EXCLUSIONS:
        audit_errors.append(
            "operation_record explicit_exclusions do not match required exclusions"
        )

    readiness_summary = operation_record.get("readiness_summary", {})
    if not isinstance(readiness_summary, Mapping):
        audit_errors.append("operation_record readiness_summary must be a mapping")
        readiness_summary = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if adapter_status == "ready" and operation_record.get("is_ready") is not True:
        audit_errors.append(
            "operation_record ready adapter conflicts with is_ready=False"
        )

    if adapter_status != "ready" and operation_record.get("is_ready") is True:
        audit_errors.append(
            "operation_record non-ready adapter conflicts with is_ready=True"
        )

    if adapter_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked adapter_status must have blocked operation_status"
        )

    candidate_count = len(candidate_rows) if isinstance(candidate_rows, list) else 0
    price_row_count = len(price_rows) if isinstance(price_rows, list) else 0
    accepted_candidate_count = (
        sum(1 for row in candidate_rows if row.get("candidate_status") == "accepted")
        if isinstance(candidate_rows, list)
        else 0
    )
    rejected_candidate_count = (
        sum(1 for row in candidate_rows if row.get("candidate_status") == "rejected")
        if isinstance(candidate_rows, list)
        else 0
    )
    symbol_count = (
        len({row.get("symbol") for row in price_rows if row.get("symbol")})
        if isinstance(price_rows, list)
        else 0
    )
    candidate_symbol_count = (
        len({row.get("symbol") for row in candidate_rows if row.get("symbol")})
        if isinstance(candidate_rows, list)
        else 0
    )

    expected_summary = {
        "candidate_count": candidate_count,
        "price_row_count": price_row_count,
        "accepted_candidate_count": accepted_candidate_count,
        "rejected_candidate_count": rejected_candidate_count,
        "symbol_count": symbol_count,
        "candidate_symbol_count": candidate_symbol_count,
    }

    for key, expected_value in expected_summary.items():
        if readiness_summary.get(key) != expected_value:
            audit_errors.append(
                f"operation_record readiness_summary {key} does not match rows"
            )

    if readiness_summary.get("validation_error_count") != (
        len(validation_errors) if isinstance(validation_errors, list) else 0
    ):
        audit_errors.append(
            "operation_record readiness_summary validation_error_count does not match validation_errors"
        )

    if readiness_summary.get("warning_count") != (
        len(warnings) if isinstance(warnings, list) else 0
    ):
        audit_errors.append(
            "operation_record readiness_summary warning_count does not match warnings"
        )

    if readiness_summary.get("blocked_reason_count") != (
        len(blocked_reasons) if isinstance(blocked_reasons, list) else 0
    ):
        audit_errors.append(
            "operation_record readiness_summary blocked_reason_count does not match blocked_reasons"
        )

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    if adapter_status == "ready" and candidate_count <= 0:
        audit_warnings.append("operation_record ready adapter has no candidate rows")

    if adapter_status == "ready" and price_row_count <= 0:
        audit_warnings.append("operation_record ready adapter has no price rows")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "adapter_status": adapter_status,
            "source_adapter_type": source_adapter_type,
            "is_ready": operation_record.get("is_ready"),
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors)
            if isinstance(validation_errors, list)
            else 0,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "blocked_reason_count": len(blocked_reasons)
            if isinstance(blocked_reasons, list)
            else 0,
            "candidate_count": candidate_count,
            "price_row_count": price_row_count,
            "accepted_candidate_count": accepted_candidate_count,
            "rejected_candidate_count": rejected_candidate_count,
            "symbol_count": symbol_count,
            "candidate_symbol_count": candidate_symbol_count,
        },
    }
