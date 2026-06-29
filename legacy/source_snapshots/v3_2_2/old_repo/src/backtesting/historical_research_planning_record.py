# src/backtesting/historical_research_planning_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_research_planning"
SCHEMA_VERSION = "1.0"

REQUIRED_PLANNING_QUEUE_FIELDS = {
    "planning_queue_status",
    "is_ready",
    "is_blocked",
    "planning_queue_type",
    "planning_queue_name",
    "validation_errors",
    "priority_planning",
    "needs_review_planning",
    "blocked_planning",
    "planning_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}

VALID_PLANNING_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_research_planning_record(
    planning_queue: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    queue = dict(planning_queue)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_planning_queue_shape(queue)
    queue_validation_errors = [
        str(error)
        for error in queue.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *queue_validation_errors,
    ]

    planning_queue_status = queue.get("planning_queue_status")

    is_blocked = (
        bool(queue.get("is_blocked"))
        or planning_queue_status == "blocked"
        or planning_queue_status not in VALID_PLANNING_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            planning_queue=queue,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "planning_queue_status": planning_queue_status,
        "is_ready": bool(queue.get("is_ready")),
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "priority_planning": list(queue.get("priority_planning", [])),
        "needs_review_planning": list(queue.get("needs_review_planning", [])),
        "blocked_planning": list(queue.get("blocked_planning", [])),
        "planning_counts": dict(queue.get("planning_counts", {})),
        "warnings": list(queue.get("warnings", [])),
        "blocked_reasons": list(queue.get("blocked_reasons", [])),
        "explicit_exclusions": list(queue.get("explicit_exclusions", [])),
        "source_summary": dict(queue.get("source_summary", {})),
        "queue_metadata": dict(queue.get("metadata", {})),
        "metadata": metadata_dict,
    }


def _validate_planning_queue_shape(
    planning_queue: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_PLANNING_QUEUE_FIELDS - set(planning_queue.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"planning_queue missing required fields: {missing_fields}"
        )

    planning_queue_status = planning_queue.get("planning_queue_status")
    if (
        planning_queue_status is not None
        and planning_queue_status not in VALID_PLANNING_STATUSES
    ):
        validation_errors.append(
            f"planning_queue invalid planning_queue_status: {planning_queue_status}"
        )

    if "is_ready" in planning_queue and not isinstance(
        planning_queue["is_ready"],
        bool,
    ):
        validation_errors.append("planning_queue is_ready must be a boolean")

    if "is_blocked" in planning_queue and not isinstance(
        planning_queue["is_blocked"],
        bool,
    ):
        validation_errors.append("planning_queue is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "priority_planning",
        "needs_review_planning",
        "blocked_planning",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in planning_queue and not isinstance(
            planning_queue[list_field],
            list,
        ):
            validation_errors.append(f"planning_queue {list_field} must be a list")

    for mapping_field in ["planning_counts", "source_summary", "metadata"]:
        if mapping_field in planning_queue and not isinstance(
            planning_queue[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"planning_queue {mapping_field} must be a mapping"
            )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    planning_queue: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "planning_queue": planning_queue,
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
