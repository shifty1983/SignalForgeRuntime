# src/backtesting/historical_review_queue_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_review_queue"
SCHEMA_VERSION = "1.0"

REQUIRED_QUEUE_RESULT_FIELDS = {
    "queue_status",
    "is_blocked",
    "queue_type",
    "queue_name",
    "validation_errors",
    "promoted_review",
    "needs_review",
    "blocked_review",
    "review_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "metadata",
}

VALID_QUEUE_STATUSES = {"completed", "blocked"}


def build_historical_review_queue_record(
    queue_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(queue_result)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_queue_result_shape(result)
    queue_validation_errors = [
        str(error)
        for error in result.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *queue_validation_errors,
    ]

    queue_status = result.get("queue_status")

    is_blocked = (
        bool(result.get("is_blocked"))
        or queue_status == "blocked"
        or queue_status not in VALID_QUEUE_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    review_counts = dict(result.get("review_counts", {}))

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            queue_result=result,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "queue_status": queue_status,
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "promoted_review": list(result.get("promoted_review", [])),
        "needs_review": list(result.get("needs_review", [])),
        "blocked_review": list(result.get("blocked_review", [])),
        "review_counts": review_counts,
        "warnings": list(result.get("warnings", [])),
        "blocked_reasons": list(result.get("blocked_reasons", [])),
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
        "queue_metadata": dict(result.get("metadata", {})),
        "metadata": metadata_dict,
    }


def _validate_queue_result_shape(queue_result: Mapping[str, Any]) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_QUEUE_RESULT_FIELDS - set(queue_result.keys()))
    if missing_fields:
        validation_errors.append(
            f"queue_result missing required fields: {missing_fields}"
        )

    queue_status = queue_result.get("queue_status")
    if queue_status is not None and queue_status not in VALID_QUEUE_STATUSES:
        validation_errors.append(f"queue_result invalid queue_status: {queue_status}")

    if "is_blocked" in queue_result and not isinstance(
        queue_result["is_blocked"],
        bool,
    ):
        validation_errors.append("queue_result is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "promoted_review",
        "needs_review",
        "blocked_review",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in queue_result and not isinstance(
            queue_result[list_field],
            list,
        ):
            validation_errors.append(f"queue_result {list_field} must be a list")

    for mapping_field in ["review_counts", "metadata"]:
        if mapping_field in queue_result and not isinstance(
            queue_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(f"queue_result {mapping_field} must be a mapping")

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    queue_result: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "queue_result": queue_result,
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
