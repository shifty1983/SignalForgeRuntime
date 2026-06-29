from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


BROKER_OR_LIVE_EXECUTION_FIELDS = {
    "broker",
    "broker_account_id",
    "broker_order_id",
    "broker_payload",
    "broker_route",
    "broker_route_id",
    "route_id",
    "routing_destination",
    "submitted",
    "submitted_at",
    "submission_id",
    "order_submission_id",
    "live_order_id",
    "external_order_id",
    "fill_id",
    "filled",
    "filled_at",
    "fill_price",
    "average_fill_price",
    "execution_price",
    "slippage",
    "slippage_bps",
}

DRY_RUN_DISPATCH_STATUSES = {
    "dry_run_ready",
    "dry_run_validated",
    "dry_run_recorded",
    "dry_run_blocked",
    "dry_run_no_action",
    "dry_run_only",
    "not_applicable",
    "blocked",
}


def build_execution_end_to_end_operation_audit_report(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Audit the end-to-end dry-run operation record for deterministic structure
    and dry-run-only execution safety.
    """

    findings: list[dict[str, Any]] = []

    findings.extend(_audit_required_record_fields(operation_record))
    findings.extend(_audit_broker_live_field_leakage(operation_record))
    findings.extend(_audit_dispatch_dry_run_only(operation_record))

    audit_status = "failed" if findings else "passed"

    return {
        "audit_type": "execution_end_to_end_operation_audit",
        "operation_id": operation_record.get("operation_id"),
        "dry_run_id": operation_record.get("summary", {}).get("dry_run_id"),
        "audit_status": audit_status,
        "is_audit_passed": audit_status == "passed",
        "finding_count": len(findings),
        "findings": findings,
        "summary": {
            "status": operation_record.get("status"),
            "is_blocked": operation_record.get("is_blocked"),
            "blocked_stage": operation_record.get("blocked_stage"),
            "operation_validation_error_count": len(
                operation_record.get("validation_errors", [])
            ),
            "finding_count": len(findings),
        },
    }


def _audit_required_record_fields(
    operation_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    required_fields = {
        "operation_id",
        "operation_type",
        "status",
        "is_blocked",
        "summary",
        "dry_run_result",
    }

    for field_name in sorted(required_fields):
        if field_name not in operation_record:
            findings.append(
                {
                    "severity": "error",
                    "code": "missing_operation_record_field",
                    "message": (
                        f"operation_record missing required field: "
                        f"{field_name}"
                    ),
                    "field": field_name,
                }
            )

    if operation_record.get("operation_type") not in (
        None,
        "portfolio_strategy_execution_dry_run",
    ):
        findings.append(
            {
                "severity": "error",
                "code": "unexpected_operation_type",
                "message": (
                    "operation_record has unexpected operation_type: "
                    f"{operation_record.get('operation_type')}"
                ),
                "field": "operation_type",
            }
        )

    return findings


def _audit_broker_live_field_leakage(
    operation_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for path, field_name, value in _walk_disallowed_fields(operation_record):
        if _has_value(value):
            findings.append(
                {
                    "severity": "error",
                    "code": "broker_or_live_execution_field_detected",
                    "message": (
                        f"broker/live execution field detected at "
                        f"{path}: {field_name}"
                    ),
                    "path": path,
                    "field": field_name,
                }
            )

    return findings


def _audit_dispatch_dry_run_only(
    operation_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    dry_run_result = operation_record.get("dry_run_result", {})
    dispatch_rows = dry_run_result.get("dispatch_intent_rows", [])

    if not isinstance(dispatch_rows, Sequence) or isinstance(
        dispatch_rows,
        (str, bytes),
    ):
        return [
            {
                "severity": "error",
                "code": "invalid_dispatch_intent_rows",
                "message": "dispatch_intent_rows must be a sequence",
                "path": "dry_run_result.dispatch_intent_rows",
            }
        ]

    for index, row in enumerate(dispatch_rows):
        if not isinstance(row, Mapping):
            findings.append(
                {
                    "severity": "error",
                    "code": "invalid_dispatch_intent_row",
                    "message": (
                        f"dispatch_intent_rows[{index}] must be a mapping"
                    ),
                    "path": f"dry_run_result.dispatch_intent_rows[{index}]",
                }
            )
            continue

        if row.get("dry_run_only") is False:
            findings.append(
                {
                    "severity": "error",
                    "code": "dispatch_not_dry_run_only",
                    "message": (
                        f"dispatch_intent_rows[{index}] has "
                        "dry_run_only=False"
                    ),
                    "path": f"dry_run_result.dispatch_intent_rows[{index}]",
                    "field": "dry_run_only",
                }
            )

        dispatch_status = row.get("dispatch_status")
        if dispatch_status is not None:
            normalized_status = str(dispatch_status).lower()
            if (
                normalized_status not in DRY_RUN_DISPATCH_STATUSES
                and not normalized_status.startswith("dry_run")
            ):
                findings.append(
                    {
                        "severity": "error",
                        "code": "non_dry_run_dispatch_status",
                        "message": (
                            f"dispatch_intent_rows[{index}] has "
                            f"non-dry-run dispatch_status: {dispatch_status}"
                        ),
                        "path": (
                            f"dry_run_result.dispatch_intent_rows[{index}]"
                        ),
                        "field": "dispatch_status",
                    }
                )

    return findings


def _walk_disallowed_fields(
    value: Any,
    *,
    path: str = "operation_record",
) -> list[tuple[str, str, Any]]:
    matches: list[tuple[str, str, Any]] = []

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_string = str(key)
            nested_path = f"{path}.{key_string}"

            if key_string in BROKER_OR_LIVE_EXECUTION_FIELDS:
                matches.append((nested_path, key_string, nested_value))

            matches.extend(
                _walk_disallowed_fields(nested_value, path=nested_path)
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(
                _walk_disallowed_fields(item, path=f"{path}[{index}]")
            )

    return matches


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {}, ())
