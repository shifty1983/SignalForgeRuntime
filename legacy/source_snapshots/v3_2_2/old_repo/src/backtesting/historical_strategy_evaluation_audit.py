# src/backtesting/historical_strategy_evaluation_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "is_blocked",
    "validation_errors",
    "summary",
    "accepted_vs_rejected",
    "by_regime",
    "by_asset_behavior",
    "by_direction",
    "evaluated_rows",
    "metadata",
}


def audit_historical_strategy_evaluation_record(
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
    if operation_type != "historical_strategy_evaluation":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    is_blocked = operation_record.get("is_blocked")
    if not isinstance(is_blocked, bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    if not isinstance(validation_errors, list):
        audit_errors.append("operation_record validation_errors must be a list")

    evaluated_rows = operation_record.get("evaluated_rows", [])
    if not isinstance(evaluated_rows, list):
        audit_errors.append("operation_record evaluated_rows must be a list")

    summary = operation_record.get("summary", {})
    if not isinstance(summary, Mapping):
        audit_errors.append("operation_record summary must be a mapping")
        summary = {}

    accepted_vs_rejected = operation_record.get("accepted_vs_rejected", {})
    if not isinstance(accepted_vs_rejected, Mapping):
        audit_errors.append(
            "operation_record accepted_vs_rejected must be a mapping"
        )
        accepted_vs_rejected = {}

    if operation_status == "completed" and is_blocked is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and is_blocked is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if operation_status == "completed" and validation_errors:
        audit_errors.append(
            "operation_record completed status conflicts with validation_errors"
        )

    if operation_status == "completed" and not evaluated_rows:
        audit_warnings.append(
            "operation_record completed with no evaluated rows"
        )

    expected_evaluated_count = summary.get("evaluated_candidate_count")
    if (
        isinstance(expected_evaluated_count, int)
        and isinstance(evaluated_rows, list)
        and expected_evaluated_count != len(evaluated_rows)
    ):
        audit_errors.append(
            "operation_record summary evaluated_candidate_count does not match evaluated_rows"
        )

    accepted_summary = accepted_vs_rejected.get("accepted", {})
    rejected_summary = accepted_vs_rejected.get("rejected", {})

    if operation_status == "completed" and not accepted_summary:
        audit_warnings.append("operation_record missing accepted comparison summary")

    if operation_status == "completed" and not rejected_summary:
        audit_warnings.append("operation_record missing rejected comparison summary")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "is_blocked": is_blocked,
            "validation_error_count": (
                len(validation_errors)
                if isinstance(validation_errors, list)
                else 0
            ),
            "evaluated_candidate_count": (
                len(evaluated_rows)
                if isinstance(evaluated_rows, list)
                else 0
            ),
        },
    }
