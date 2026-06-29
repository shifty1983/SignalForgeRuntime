# src/backtesting/historical_research_handoff_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_research_handoff"
SCHEMA_VERSION = "1.0"

REQUIRED_HANDOFF_BUNDLE_FIELDS = {
    "bundle_status",
    "is_ready",
    "is_blocked",
    "bundle_type",
    "bundle_name",
    "validation_errors",
    "priority_research",
    "needs_review_research",
    "blocked_research",
    "handoff_summary",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}

VALID_BUNDLE_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_research_handoff_record(
    handoff_bundle: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bundle = dict(handoff_bundle)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_handoff_bundle_shape(bundle)
    bundle_validation_errors = [
        str(error)
        for error in bundle.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *bundle_validation_errors,
    ]

    bundle_status = bundle.get("bundle_status")

    is_blocked = (
        bool(bundle.get("is_blocked"))
        or bundle_status == "blocked"
        or bundle_status not in VALID_BUNDLE_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            handoff_bundle=bundle,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "bundle_status": bundle_status,
        "is_ready": bool(bundle.get("is_ready")),
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "priority_research": list(bundle.get("priority_research", [])),
        "needs_review_research": list(bundle.get("needs_review_research", [])),
        "blocked_research": list(bundle.get("blocked_research", [])),
        "handoff_summary": dict(bundle.get("handoff_summary", {})),
        "warnings": list(bundle.get("warnings", [])),
        "blocked_reasons": list(bundle.get("blocked_reasons", [])),
        "explicit_exclusions": list(bundle.get("explicit_exclusions", [])),
        "source_summary": dict(bundle.get("source_summary", {})),
        "bundle_metadata": dict(bundle.get("metadata", {})),
        "metadata": metadata_dict,
    }


def _validate_handoff_bundle_shape(
    handoff_bundle: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_HANDOFF_BUNDLE_FIELDS - set(handoff_bundle.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"handoff_bundle missing required fields: {missing_fields}"
        )

    bundle_status = handoff_bundle.get("bundle_status")
    if bundle_status is not None and bundle_status not in VALID_BUNDLE_STATUSES:
        validation_errors.append(
            f"handoff_bundle invalid bundle_status: {bundle_status}"
        )

    if "is_ready" in handoff_bundle and not isinstance(
        handoff_bundle["is_ready"],
        bool,
    ):
        validation_errors.append("handoff_bundle is_ready must be a boolean")

    if "is_blocked" in handoff_bundle and not isinstance(
        handoff_bundle["is_blocked"],
        bool,
    ):
        validation_errors.append("handoff_bundle is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "priority_research",
        "needs_review_research",
        "blocked_research",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in handoff_bundle and not isinstance(
            handoff_bundle[list_field],
            list,
        ):
            validation_errors.append(f"handoff_bundle {list_field} must be a list")

    for mapping_field in ["handoff_summary", "source_summary", "metadata"]:
        if mapping_field in handoff_bundle and not isinstance(
            handoff_bundle[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"handoff_bundle {mapping_field} must be a mapping"
            )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    handoff_bundle: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "handoff_bundle": handoff_bundle,
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
