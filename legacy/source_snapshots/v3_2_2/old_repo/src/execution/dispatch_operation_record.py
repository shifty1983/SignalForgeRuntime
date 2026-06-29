from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from src.execution.dispatch_contract import (
    DISPATCH_STATUS_DRY_RUN_ONLY,
    build_execution_dispatch_contract,
    validate_dispatch_intent_rows,
)


DISPATCH_OPERATION_TYPE = "execution_dispatch_intent"
DISPATCH_OPERATION_STATUS_COMPLETED = "completed"
DISPATCH_OPERATION_STATUS_BLOCKED = "blocked"


REQUIRED_OPERATION_RECORD_FIELDS = (
    "operation_id",
    "operation_type",
    "run_id",
    "status",
    "is_blocked",
    "dispatch_intent_rows",
    "dispatch_intent_count",
    "validation_errors",
    "validation_error_count",
    "summary",
    "metadata",
)


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _copy_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []

    copied_rows: list[dict[str, Any]] = []
    for row in rows:
        copied_rows.append(dict(row) if isinstance(row, Mapping) else {})
    return copied_rows


def _build_contract_result(
    *,
    dispatch_contract_result: Mapping[str, Any] | None = None,
    planned_order_instructions: Sequence[Any] | None = None,
) -> dict[str, Any]:
    if dispatch_contract_result is not None:
        return deepcopy(dict(dispatch_contract_result))

    if planned_order_instructions is None:
        raise ValueError(
            "Either dispatch_contract_result or planned_order_instructions is required"
        )

    return build_execution_dispatch_contract(planned_order_instructions)


def build_execution_dispatch_operation_record(
    dispatch_contract_result: Mapping[str, Any] | None = None,
    *,
    planned_order_instructions: Sequence[Any] | None = None,
    operation_id: str = "execution_dispatch_operation",
    run_id: str = "execution_dispatch_run",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract_result = _build_contract_result(
        dispatch_contract_result=dispatch_contract_result,
        planned_order_instructions=planned_order_instructions,
    )

    dispatch_intent_rows = _copy_rows(contract_result.get("dispatch_intent_rows", []))
    validation_errors = list(contract_result.get("validation_errors", []))
    is_blocked = bool(contract_result.get("is_blocked", validation_errors))

    status = (
        DISPATCH_OPERATION_STATUS_BLOCKED
        if is_blocked
        else DISPATCH_OPERATION_STATUS_COMPLETED
    )

    summary = _copy_mapping(contract_result.get("summary"))
    operation_metadata = _copy_mapping(metadata)

    return {
        "operation_id": operation_id,
        "operation_type": DISPATCH_OPERATION_TYPE,
        "run_id": run_id,
        "status": status,
        "is_blocked": is_blocked,
        "dispatch_intent_rows": dispatch_intent_rows,
        "dispatch_intent_count": len(dispatch_intent_rows),
        "validation_errors": validation_errors,
        "validation_error_count": len(validation_errors),
        "summary": summary,
        "metadata": operation_metadata,
    }


def build_execution_dispatch_operation_record_from_planned_order_instructions(
    planned_order_instructions: Sequence[Any],
    *,
    operation_id: str = "execution_dispatch_operation",
    run_id: str = "execution_dispatch_run",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return build_execution_dispatch_operation_record(
        planned_order_instructions=planned_order_instructions,
        operation_id=operation_id,
        run_id=run_id,
        metadata=metadata,
    )


def validate_execution_dispatch_operation_record(
    operation_record: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []

    for field_name in REQUIRED_OPERATION_RECORD_FIELDS:
        if field_name not in operation_record:
            errors.append(f"operation_record missing required field: {field_name}")

    operation_type = operation_record.get("operation_type")
    if operation_type != DISPATCH_OPERATION_TYPE:
        errors.append(
            f"operation_record operation_type must be {DISPATCH_OPERATION_TYPE}"
        )

    status = operation_record.get("status")
    is_blocked = bool(operation_record.get("is_blocked"))

    if is_blocked and status != DISPATCH_OPERATION_STATUS_BLOCKED:
        errors.append("operation_record blocked records must have status blocked")

    if not is_blocked and status != DISPATCH_OPERATION_STATUS_COMPLETED:
        errors.append("operation_record unblocked records must have status completed")

    dispatch_intent_rows = operation_record.get("dispatch_intent_rows")
    if not isinstance(dispatch_intent_rows, Sequence) or isinstance(
        dispatch_intent_rows, (str, bytes)
    ):
        errors.append("operation_record dispatch_intent_rows must be a sequence")
        dispatch_intent_rows = []

    dispatch_intent_rows = _copy_rows(dispatch_intent_rows)

    expected_dispatch_count = len(dispatch_intent_rows)
    if operation_record.get("dispatch_intent_count") != expected_dispatch_count:
        errors.append(
            "operation_record dispatch_intent_count does not match "
            "dispatch_intent_rows"
        )

    validation_errors = operation_record.get("validation_errors")
    if not isinstance(validation_errors, Sequence) or isinstance(
        validation_errors, (str, bytes)
    ):
        errors.append("operation_record validation_errors must be a sequence")
        validation_errors = []

    if operation_record.get("validation_error_count") != len(validation_errors):
        errors.append(
            "operation_record validation_error_count does not match "
            "validation_errors"
        )

    dispatch_validation_errors = validate_dispatch_intent_rows(dispatch_intent_rows)
    for dispatch_error in dispatch_validation_errors:
        if dispatch_error not in validation_errors:
            errors.append(
                "operation_record dispatch validation error missing from record: "
                f"{dispatch_error}"
            )

    for index, row in enumerate(dispatch_intent_rows):
        if row.get("dispatch_status") != DISPATCH_STATUS_DRY_RUN_ONLY:
            errors.append(
                "operation_record dispatch_intent_rows"
                f"[{index}] must remain dry_run_only"
            )

    summary = operation_record.get("summary")
    if not isinstance(summary, Mapping):
        errors.append("operation_record summary must be a mapping")
    else:
        if summary.get("dispatch_count") != expected_dispatch_count:
            errors.append(
                "operation_record summary dispatch_count does not match "
                "dispatch_intent_rows"
            )

        if bool(summary.get("is_blocked")) != is_blocked:
            errors.append(
                "operation_record summary is_blocked does not match operation record"
            )

    metadata = operation_record.get("metadata")
    if not isinstance(metadata, Mapping):
        errors.append("operation_record metadata must be a mapping")

    return errors
