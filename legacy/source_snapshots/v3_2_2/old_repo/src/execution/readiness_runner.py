from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from src.execution.readiness_snapshot import build_execution_readiness_snapshot

READINESS_RUNNER_ID = "execution_readiness_snapshot_runner_v1"

BROKER_LIVE_EXECUTION_FIELD_NAMES: tuple[str, ...] = (
    "broker_api_call",
    "broker_api_calls",
    "broker_order_id",
    "broker_response",
    "routing_destination",
    "order_routing",
    "order_submission",
    "submission_id",
    "fill",
    "fills",
    "fill_id",
    "live_execution",
    "live_order",
    "slippage",
    "slippage_modeling",
)


def run_execution_readiness_snapshot(
    *,
    dry_run_result: Mapping[str, Any] | None = None,
    invalid_downstream_result: Mapping[str, Any] | None = None,
    component_results: Mapping[str, Any] | None = None,
    dry_run_runner: Callable[[], Mapping[str, Any]] | None = None,
    invalid_downstream_runner: Callable[[], Mapping[str, Any]] | None = None,
    runner_id: str = READINESS_RUNNER_ID,
) -> dict[str, Any]:
    """Run a deterministic broker-neutral execution readiness snapshot.

    This runner only evaluates whether the non-broker execution pipeline is
    ready for broker adapter design. It does not call broker APIs, route orders,
    submit orders, process fills, run live execution, or model slippage.
    """

    validation_errors = _validate_runner_inputs(
        dry_run_result=dry_run_result,
        invalid_downstream_result=invalid_downstream_result,
        dry_run_runner=dry_run_runner,
        invalid_downstream_runner=invalid_downstream_runner,
    )
    if validation_errors:
        return _blocked_runner_result(
            runner_id=runner_id,
            blocked_reasons=validation_errors,
        )

    resolved_dry_run_result = _resolve_result(
        provided_result=dry_run_result,
        result_runner=dry_run_runner,
        result_name="dry_run_result",
    )
    if resolved_dry_run_result["is_blocked"]:
        return _blocked_runner_result(
            runner_id=runner_id,
            blocked_reasons=resolved_dry_run_result["blocked_reasons"],
        )

    resolved_invalid_downstream_result = _resolve_result(
        provided_result=invalid_downstream_result,
        result_runner=invalid_downstream_runner,
        result_name="invalid_downstream_result",
    )
    if resolved_invalid_downstream_result["is_blocked"]:
        return _blocked_runner_result(
            runner_id=runner_id,
            blocked_reasons=resolved_invalid_downstream_result["blocked_reasons"],
        )

    broker_live_field_errors = _collect_broker_live_field_errors(
        {
            "dry_run_result": resolved_dry_run_result["result"],
            "invalid_downstream_result": resolved_invalid_downstream_result["result"],
            "component_results": component_results,
        }
    )
    if broker_live_field_errors:
        return _blocked_runner_result(
            runner_id=runner_id,
            blocked_reasons=broker_live_field_errors,
        )

    readiness_snapshot = build_execution_readiness_snapshot(
        component_results=component_results,
        dry_run_result=resolved_dry_run_result["result"],
        invalid_downstream_result=resolved_invalid_downstream_result["result"],
    )

    is_ready = bool(readiness_snapshot["is_ready"])
    blocked_reasons = list(readiness_snapshot["blocked_reasons"])

    return {
        "runner_id": runner_id,
        "operation_name": "execution_readiness_snapshot",
        "operation_type": "broker_neutral_readiness_check",
        "status": "completed" if is_ready else "blocked",
        "is_blocked": not is_ready,
        "readiness_snapshot": readiness_snapshot,
        "blocked_reasons": blocked_reasons,
        "summary": {
            "readiness_status": readiness_snapshot["readiness_status"],
            "is_ready": readiness_snapshot["is_ready"],
            "ready_component_count": readiness_snapshot["summary"][
                "ready_component_count"
            ],
            "not_ready_component_count": readiness_snapshot["summary"][
                "not_ready_component_count"
            ],
            "explicit_exclusions": readiness_snapshot["explicit_exclusions"],
        },
    }


def _validate_runner_inputs(
    *,
    dry_run_result: Mapping[str, Any] | None,
    invalid_downstream_result: Mapping[str, Any] | None,
    dry_run_runner: Callable[[], Mapping[str, Any]] | None,
    invalid_downstream_runner: Callable[[], Mapping[str, Any]] | None,
) -> list[str]:
    errors: list[str] = []

    if dry_run_result is not None and dry_run_runner is not None:
        errors.append("provide either dry_run_result or dry_run_runner, not both")

    if invalid_downstream_result is not None and invalid_downstream_runner is not None:
        errors.append(
            "provide either invalid_downstream_result or invalid_downstream_runner, "
            "not both"
        )

    if dry_run_result is None and dry_run_runner is None:
        errors.append("dry_run_result or dry_run_runner is required")

    if invalid_downstream_result is None and invalid_downstream_runner is None:
        errors.append(
            "invalid_downstream_result or invalid_downstream_runner is required"
        )

    return errors


def _resolve_result(
    *,
    provided_result: Mapping[str, Any] | None,
    result_runner: Callable[[], Mapping[str, Any]] | None,
    result_name: str,
) -> dict[str, Any]:
    if provided_result is not None:
        return {
            "is_blocked": False,
            "result": dict(provided_result),
            "blocked_reasons": [],
        }

    if result_runner is None:
        return {
            "is_blocked": True,
            "result": {},
            "blocked_reasons": [f"{result_name} runner is missing"],
        }

    try:
        result = result_runner()
    except Exception as exc:  # pragma: no cover - defensive runner boundary
        return {
            "is_blocked": True,
            "result": {},
            "blocked_reasons": [f"{result_name} runner failed: {exc!r}"],
        }

    if not isinstance(result, Mapping):
        return {
            "is_blocked": True,
            "result": {},
            "blocked_reasons": [f"{result_name} runner must return a mapping"],
        }

    return {
        "is_blocked": False,
        "result": dict(result),
        "blocked_reasons": [],
    }


def _collect_broker_live_field_errors(payloads: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    for payload_name, payload in payloads.items():
        if payload is None:
            continue

        discovered_fields = _find_broker_live_fields(payload)
        for field_path in discovered_fields:
            errors.append(
                f"{payload_name} contains broker/live execution field: {field_path}"
            )

    return errors


def _find_broker_live_fields(value: Any, *, prefix: str = "") -> list[str]:
    discovered: list[str] = []

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_as_string = str(key)
            current_path = f"{prefix}.{key_as_string}" if prefix else key_as_string

            if key_as_string in BROKER_LIVE_EXECUTION_FIELD_NAMES:
                discovered.append(current_path)

            discovered.extend(
                _find_broker_live_fields(nested_value, prefix=current_path)
            )

    elif isinstance(value, list | tuple):
        for index, nested_value in enumerate(value):
            current_path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            discovered.extend(
                _find_broker_live_fields(nested_value, prefix=current_path)
            )

    return discovered


def _blocked_runner_result(
    *,
    runner_id: str,
    blocked_reasons: list[str],
) -> dict[str, Any]:
    return {
        "runner_id": runner_id,
        "operation_name": "execution_readiness_snapshot",
        "operation_type": "broker_neutral_readiness_check",
        "status": "blocked",
        "is_blocked": True,
        "readiness_snapshot": None,
        "blocked_reasons": blocked_reasons,
        "summary": {
            "readiness_status": "not_ready",
            "is_ready": False,
            "ready_component_count": 0,
            "not_ready_component_count": None,
            "explicit_exclusions": [
                "broker_api_calls",
                "order_routing",
                "order_submission",
                "fills",
                "live_execution",
                "slippage_modeling",
            ],
        },
    }


__all__ = [
    "BROKER_LIVE_EXECUTION_FIELD_NAMES",
    "READINESS_RUNNER_ID",
    "run_execution_readiness_snapshot",
]
