# src/backtesting/historical_data_readiness_adapter_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from src.backtesting.historical_data_readiness_adapter import EXPLICIT_EXCLUSIONS


OPERATION_TYPE = "historical_data_readiness_adapter_operation"
SOURCE_ADAPTER_TYPE = "historical_data_readiness_adapter"
SCHEMA_VERSION = "1.0"

REQUIRED_ADAPTER_FIELDS = {
    "adapter_type",
    "adapter_status",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "warnings",
    "blocked_reasons",
    "candidate_rows",
    "price_rows",
    "readiness_summary",
    "explicit_exclusions",
    "metadata",
}

VALID_ADAPTER_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_data_readiness_adapter_record(
    adapter_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    adapter = dict(adapter_result)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_adapter_shape(adapter)
    adapter_validation_errors = [
        str(error)
        for error in adapter.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *adapter_validation_errors,
    ]

    adapter_status = adapter.get("adapter_status")

    is_blocked = (
        bool(adapter.get("is_blocked"))
        or adapter_status == "blocked"
        or adapter_status not in VALID_ADAPTER_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            adapter_result=adapter,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "adapter_status": adapter_status,
        "source_adapter_type": adapter.get("adapter_type"),
        "is_ready": adapter_status == "ready",
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "warnings": list(adapter.get("warnings", [])),
        "blocked_reasons": list(adapter.get("blocked_reasons", [])),
        "candidate_rows": list(adapter.get("candidate_rows", [])),
        "price_rows": list(adapter.get("price_rows", [])),
        "readiness_summary": dict(adapter.get("readiness_summary", {})),
        "explicit_exclusions": list(adapter.get("explicit_exclusions", [])),
        "adapter_metadata": dict(adapter.get("metadata", {})),
        "metadata": metadata_dict,
    }


def _validate_adapter_shape(adapter_result: Mapping[str, Any]) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_ADAPTER_FIELDS - set(adapter_result.keys()))
    if missing_fields:
        validation_errors.append(
            f"adapter_result missing required fields: {missing_fields}"
        )

    adapter_type = adapter_result.get("adapter_type")
    if adapter_type is not None and adapter_type != SOURCE_ADAPTER_TYPE:
        validation_errors.append(f"adapter_result invalid adapter_type: {adapter_type}")

    adapter_status = adapter_result.get("adapter_status")
    if adapter_status is not None and adapter_status not in VALID_ADAPTER_STATUSES:
        validation_errors.append(
            f"adapter_result invalid adapter_status: {adapter_status}"
        )

    if "is_ready" in adapter_result and not isinstance(
        adapter_result["is_ready"],
        bool,
    ):
        validation_errors.append("adapter_result is_ready must be a boolean")

    if "is_blocked" in adapter_result and not isinstance(
        adapter_result["is_blocked"],
        bool,
    ):
        validation_errors.append("adapter_result is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "warnings",
        "blocked_reasons",
        "candidate_rows",
        "price_rows",
        "explicit_exclusions",
    ]:
        if list_field in adapter_result and not isinstance(
            adapter_result[list_field],
            list,
        ):
            validation_errors.append(f"adapter_result {list_field} must be a list")

    for mapping_field in ["readiness_summary", "metadata"]:
        if mapping_field in adapter_result and not isinstance(
            adapter_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(f"adapter_result {mapping_field} must be a mapping")

    explicit_exclusions = adapter_result.get("explicit_exclusions")
    if explicit_exclusions is not None and list(explicit_exclusions) != EXPLICIT_EXCLUSIONS:
        validation_errors.append(
            "adapter_result explicit_exclusions do not match required exclusions"
        )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    adapter_result: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "adapter_result": adapter_result,
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
