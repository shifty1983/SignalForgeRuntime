from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


OPERATION_TYPE = "historical_strategy_evaluation"
SCHEMA_VERSION = "1.0"

VALID_EVALUATION_STATUSES = {"completed", "blocked"}

REQUIRED_EVALUATION_REPORT_FIELDS = {
    "evaluation_status",
    "is_blocked",
    "validation_errors",
    "evaluated_rows",
    "accepted_vs_rejected",
    "by_regime",
    "by_asset_behavior",
    "by_direction",
    "summary",
}


def build_historical_strategy_evaluation_record(
    evaluation_report: Mapping[str, Any],
    *,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report = dict(evaluation_report)
    metadata_dict = dict(metadata or {})

    record_validation_errors = _validate_evaluation_report_shape(report)

    raw_report_validation_errors = report.get("validation_errors", [])
    if isinstance(raw_report_validation_errors, list):
        report_validation_errors = [
            str(error) for error in raw_report_validation_errors
        ]
    else:
        report_validation_errors = []

    combined_validation_errors = [
        *record_validation_errors,
        *report_validation_errors,
    ]

    evaluation_status = report.get("evaluation_status")

    is_blocked = (
        bool(report.get("is_blocked"))
        or evaluation_status == "blocked"
        or evaluation_status not in VALID_EVALUATION_STATUSES
        or bool(record_validation_errors)
    )

    operation_status = "blocked" if is_blocked else "completed"

    return {
        "schema_version": SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "operation_id": _stable_operation_id(
            operation_name=operation_name,
            evaluation_report=report,
            metadata=metadata_dict,
        ),
        "operation_status": operation_status,
        "is_blocked": is_blocked,
        "validation_errors": combined_validation_errors,
        "summary": dict(report.get("summary", {})),
        "accepted_vs_rejected": dict(report.get("accepted_vs_rejected", {})),
        "by_regime": dict(report.get("by_regime", {})),
        "by_asset_behavior": dict(report.get("by_asset_behavior", {})),
        "by_direction": dict(report.get("by_direction", {})),
        "by_option_behavior": dict(report.get("by_option_behavior", {})),
        "by_regime_asset_behavior_direction": dict(
            report.get("by_regime_asset_behavior_direction", {})
        ),
        "by_option_behavior_asset_behavior_direction": dict(
            report.get("by_option_behavior_asset_behavior_direction", {})
        ),
        "evaluated_rows": list(report.get("evaluated_rows", [])),"metadata": metadata_dict,
    }


def _validate_evaluation_report_shape(
    evaluation_report: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_EVALUATION_REPORT_FIELDS - set(evaluation_report.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"evaluation_report missing required fields: {missing_fields}"
        )

    evaluation_status = evaluation_report.get("evaluation_status")
    if (
        evaluation_status is not None
        and evaluation_status not in VALID_EVALUATION_STATUSES
    ):
        validation_errors.append(
            f"evaluation_report invalid evaluation_status: {evaluation_status}"
        )

    if "is_blocked" in evaluation_report and not isinstance(
        evaluation_report["is_blocked"],
        bool,
    ):
        validation_errors.append("evaluation_report is_blocked must be a boolean")

    if "validation_errors" in evaluation_report and not isinstance(
        evaluation_report["validation_errors"],
        list,
    ):
        validation_errors.append("evaluation_report validation_errors must be a list")

    if "evaluated_rows" in evaluation_report and not isinstance(
        evaluation_report["evaluated_rows"],
        list,
    ):
        validation_errors.append("evaluation_report evaluated_rows must be a list")

    for dict_field in [
        "summary",
        "accepted_vs_rejected",
        "by_regime",
        "by_asset_behavior",
        "by_direction",
    ]:
        if dict_field in evaluation_report and not isinstance(
            evaluation_report[dict_field],
            Mapping,
        ):
            validation_errors.append(
                f"evaluation_report {dict_field} must be a mapping"
            )

    return validation_errors


def _stable_operation_id(
    *,
    operation_name: str,
    evaluation_report: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    payload = {
        "operation_name": operation_name,
        "evaluation_report": evaluation_report,
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

