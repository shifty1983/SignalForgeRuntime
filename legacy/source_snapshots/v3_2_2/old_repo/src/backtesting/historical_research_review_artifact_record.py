# src/backtesting/historical_research_review_artifact_record.py

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_research_review_artifact"
SCHEMA_VERSION = "1.0"

REQUIRED_ARTIFACT_FIELDS = {
    "artifact_status",
    "is_ready",
    "is_blocked",
    "artifact_type",
    "artifact_name",
    "validation_errors",
    "ready_review",
    "needs_review",
    "blocked_review",
    "artifact_summary",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}

VALID_ARTIFACT_STATUSES = {"ready", "needs_review", "blocked"}


def build_historical_research_review_artifact_record(
    review_artifact: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = dict(review_artifact)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_artifact_shape(artifact)
    artifact_validation_errors = [
        str(error)
        for error in artifact.get("validation_errors", [])
        if error is not None
    ]

    combined_validation_errors = [
        *record_validation_errors,
        *artifact_validation_errors,
    ]

    artifact_status = artifact.get("artifact_status")

    is_blocked = (
        bool(artifact.get("is_blocked"))
        or artifact_status == "blocked"
        or artifact_status not in VALID_ARTIFACT_STATUSES
        or bool(combined_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            review_artifact=artifact,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "artifact_status": artifact_status,
        "is_ready": bool(artifact.get("is_ready")),
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "ready_review": list(artifact.get("ready_review", [])),
        "needs_review": list(artifact.get("needs_review", [])),
        "blocked_review": list(artifact.get("blocked_review", [])),
        "artifact_summary": dict(artifact.get("artifact_summary", {})),
        "warnings": list(artifact.get("warnings", [])),
        "blocked_reasons": list(artifact.get("blocked_reasons", [])),
        "explicit_exclusions": list(artifact.get("explicit_exclusions", [])),
        "source_summary": dict(artifact.get("source_summary", {})),
        "artifact_metadata": dict(artifact.get("metadata", {})),
        "metadata": metadata_dict,
    }


def _validate_artifact_shape(review_artifact: Mapping[str, Any]) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_ARTIFACT_FIELDS - set(review_artifact.keys()))
    if missing_fields:
        validation_errors.append(
            f"review_artifact missing required fields: {missing_fields}"
        )

    artifact_status = review_artifact.get("artifact_status")
    if (
        artifact_status is not None
        and artifact_status not in VALID_ARTIFACT_STATUSES
    ):
        validation_errors.append(
            f"review_artifact invalid artifact_status: {artifact_status}"
        )

    if "is_ready" in review_artifact and not isinstance(
        review_artifact["is_ready"],
        bool,
    ):
        validation_errors.append("review_artifact is_ready must be a boolean")

    if "is_blocked" in review_artifact and not isinstance(
        review_artifact["is_blocked"],
        bool,
    ):
        validation_errors.append("review_artifact is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "ready_review",
        "needs_review",
        "blocked_review",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in review_artifact and not isinstance(
            review_artifact[list_field],
            list,
        ):
            validation_errors.append(f"review_artifact {list_field} must be a list")

    for mapping_field in ["artifact_summary", "source_summary", "metadata"]:
        if mapping_field in review_artifact and not isinstance(
            review_artifact[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"review_artifact {mapping_field} must be a mapping"
            )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    review_artifact: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "review_artifact": review_artifact,
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
