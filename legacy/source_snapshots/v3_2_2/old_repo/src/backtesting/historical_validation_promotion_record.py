# src/backtesting/historical_validation_promotion_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_validation_promotion"
SCHEMA_VERSION = "1.0"

REQUIRED_PROMOTION_RESULT_FIELDS = {
    "promotion_status",
    "is_promoted",
    "is_blocked",
    "validation_errors",
    "blocked_reasons",
    "warnings",
    "promotion_metrics",
    "summary",
}

VALID_PROMOTION_STATUSES = {"promoted", "needs_review", "blocked"}


def build_historical_validation_promotion_record(
    promotion_result: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(promotion_result)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_promotion_result_shape(result)
    promotion_validation_errors = [
        str(error)
        for error in result.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *promotion_validation_errors,
    ]

    promotion_status = result.get("promotion_status")

    is_blocked = (
        bool(result.get("is_blocked"))
        or promotion_status == "blocked"
        or promotion_status not in VALID_PROMOTION_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            promotion_result=result,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "promotion_status": promotion_status,
        "is_promoted": bool(result.get("is_promoted")),
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "blocked_reasons": list(result.get("blocked_reasons", [])),
        "warnings": list(result.get("warnings", [])),
        "promotion_metrics": dict(result.get("promotion_metrics", {})),
        "summary": dict(result.get("summary", {})),
        "metadata": metadata_dict,
    }


def _validate_promotion_result_shape(
    promotion_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_PROMOTION_RESULT_FIELDS - set(promotion_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"promotion_result missing required fields: {missing_fields}"
        )

    promotion_status = promotion_result.get("promotion_status")
    if (
        promotion_status is not None
        and promotion_status not in VALID_PROMOTION_STATUSES
    ):
        validation_errors.append(
            f"promotion_result invalid promotion_status: {promotion_status}"
        )

    if "is_promoted" in promotion_result and not isinstance(
        promotion_result["is_promoted"],
        bool,
    ):
        validation_errors.append("promotion_result is_promoted must be a boolean")

    if "is_blocked" in promotion_result and not isinstance(
        promotion_result["is_blocked"],
        bool,
    ):
        validation_errors.append("promotion_result is_blocked must be a boolean")

    if "validation_errors" in promotion_result and not isinstance(
        promotion_result["validation_errors"],
        list,
    ):
        validation_errors.append("promotion_result validation_errors must be a list")

    if "blocked_reasons" in promotion_result and not isinstance(
        promotion_result["blocked_reasons"],
        list,
    ):
        validation_errors.append("promotion_result blocked_reasons must be a list")

    if "warnings" in promotion_result and not isinstance(
        promotion_result["warnings"],
        list,
    ):
        validation_errors.append("promotion_result warnings must be a list")

    if "promotion_metrics" in promotion_result and not isinstance(
        promotion_result["promotion_metrics"],
        Mapping,
    ):
        validation_errors.append(
            "promotion_result promotion_metrics must be a mapping"
        )

    if "summary" in promotion_result and not isinstance(
        promotion_result["summary"],
        Mapping,
    ):
        validation_errors.append("promotion_result summary must be a mapping")

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    promotion_result: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "promotion_result": promotion_result,
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
