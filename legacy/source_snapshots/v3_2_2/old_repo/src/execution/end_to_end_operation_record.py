from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


REQUIRED_DRY_RUN_KEYS = {
    "dry_run_id",
    "status",
    "is_blocked",
    "summary",
    "execution_intent_rows",
    "planned_order_instructions",
    "dispatch_intent_rows",
}


def build_execution_end_to_end_operation_record(
    dry_run_result: Mapping[str, Any],
    *,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """
    Build a deterministic operation record for the broker-neutral
    portfolio / strategy / execution end-to-end dry run.

    This records dry-run results only. It must not route, submit, fill,
    or simulate broker execution.
    """

    record_validation_errors = _validate_dry_run_result(dry_run_result)

    dry_run_payload = _json_safe(dict(dry_run_result))
    dry_run_summary = dry_run_payload.get("summary", {})

    resolved_operation_id = operation_id or (
        "execution_end_to_end_operation_"
        f"{_stable_digest(dry_run_payload)[:12]}"
    )

    dry_run_status = str(dry_run_payload.get("status", "blocked"))
    is_blocked = bool(
        dry_run_payload.get("is_blocked", True)
        or record_validation_errors
        or dry_run_status == "blocked"
    )

    status = "blocked" if is_blocked else dry_run_status

    validation_errors = [
        *record_validation_errors,
        *list(dry_run_payload.get("validation_errors", [])),
    ]

    summary = {
        "operation_id": resolved_operation_id,
        "operation_type": "portfolio_strategy_execution_dry_run",
        "dry_run_id": dry_run_payload.get("dry_run_id"),
        "status": status,
        "is_blocked": is_blocked,
        "blocked_stage": dry_run_payload.get("blocked_stage"),
        "candidate_count": dry_run_summary.get("candidate_count", 0),
        "execution_intent_count": dry_run_summary.get(
            "execution_intent_count",
            0,
        ),
        "planned_instruction_count": dry_run_summary.get(
            "planned_instruction_count",
            0,
        ),
        "dispatch_intent_count": dry_run_summary.get(
            "dispatch_intent_count",
            0,
        ),
        "validation_error_count": len(validation_errors),
        "record_validation_error_count": len(record_validation_errors),
    }

    return {
        "operation_id": resolved_operation_id,
        "operation_type": "portfolio_strategy_execution_dry_run",
        "status": status,
        "is_blocked": is_blocked,
        "blocked_stage": dry_run_payload.get("blocked_stage"),
        "validation_errors": validation_errors,
        "record_validation_errors": record_validation_errors,
        "summary": summary,
        "dry_run_result": dry_run_payload,
    }


def _validate_dry_run_result(dry_run_result: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    if not isinstance(dry_run_result, Mapping):
        return ["dry_run_result must be a mapping"]

    for key in sorted(REQUIRED_DRY_RUN_KEYS):
        if key not in dry_run_result:
            errors.append(f"dry_run_result missing required field: {key}")

    summary = dry_run_result.get("summary")
    if summary is not None and not isinstance(summary, Mapping):
        errors.append("dry_run_result.summary must be a mapping")

    return errors


def _stable_digest(value: Any) -> str:
    payload = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(value[key])
            for key in sorted(value.keys(), key=str)
        }

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)
