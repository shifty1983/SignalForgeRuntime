from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from src.execution.execution_input_runner import (
    RUNNER_NAME,
    run_execution_input_contract,
)


OPERATION_TYPE = "execution_input_operation"
HEALTH_GATE_NAME = "execution_input_health_gate"

_FORBIDDEN_BROKER_FIELDS = {
    "broker",
    "broker_account_id",
    "broker_order_id",
    "order_id",
    "fill_id",
    "filled_quantity",
    "avg_fill_price",
    "average_fill_price",
    "commission",
    "slippage",
    "route",
    "venue",
    "live_order",
}


@dataclass(frozen=True)
class ExecutionInputOperationRecord:
    operation_id: str
    operation_type: str
    operation_name: str
    status: str
    contract_version: str
    summary: dict[str, Any]
    attachments: dict[str, Any]
    errors: list[str]


def run_execution_input_operation(
    risk_management_output: Mapping[str, Any],
    *,
    operation_id: str = "execution_input_operation",
) -> dict[str, Any]:
    runner_result = run_execution_input_contract(risk_management_output)

    record = ExecutionInputOperationRecord(
        operation_id=operation_id,
        operation_type=OPERATION_TYPE,
        operation_name=RUNNER_NAME,
        status=runner_result["status"],
        contract_version=runner_result["contract_version"],
        summary=runner_result["summary"],
        attachments={
            "execution_input_contract": runner_result["contract"],
            "execution_input_runner_result": runner_result,
        },
        errors=runner_result["errors"],
    )

    return _json_safe(asdict(record))


def build_execution_input_operation_log_entry(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    return _json_safe(
        {
            "operation_id": operation_record.get("operation_id"),
            "operation_type": operation_record.get("operation_type"),
            "operation_name": operation_record.get("operation_name"),
            "status": operation_record.get("status"),
            "contract_version": operation_record.get("contract_version"),
            "summary": operation_record.get("summary", {}),
            "errors": operation_record.get("errors", []),
        }
    )


def append_execution_input_operation_log(
    operation_record: Mapping[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = build_execution_input_operation_log_entry(operation_record)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, sort_keys=True) + "\n")

    return entry


def evaluate_execution_input_operation_health(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    status = operation_record.get("status")
    summary = operation_record.get("summary", {})
    attachments = operation_record.get("attachments", {})
    errors = operation_record.get("errors", [])

    contract = attachments.get("execution_input_contract")
    runner_result = attachments.get("execution_input_runner_result")

    _add_check(
        checks,
        "operation_passed",
        status == "passed",
        f"operation status is {status!r}",
    )

    _add_check(
        checks,
        "no_operation_errors",
        not errors,
        f"operation errors: {errors}",
    )

    _add_check(
        checks,
        "contract_attached",
        isinstance(contract, Mapping),
        "execution input contract must be attached",
    )

    _add_check(
        checks,
        "runner_result_attached",
        isinstance(runner_result, Mapping),
        "execution input runner result must be attached",
    )

    if isinstance(contract, Mapping):
        contract_rows = list(contract.get("rows", []))
        contract_row_count = contract.get("row_count")

        _add_check(
            checks,
            "contract_has_rows",
            bool(contract_rows),
            f"contract row count is {contract_row_count}",
        )

        _add_check(
            checks,
            "summary_row_count_matches_contract",
            summary.get("row_count") == contract_row_count,
            (
                f"summary row count {summary.get('row_count')} does not match "
                f"contract row count {contract_row_count}"
            ),
        )

        _add_check(
            checks,
            "contract_has_no_broker_execution_fields",
            not _contains_forbidden_broker_fields(contract),
            "execution input contract must not contain broker/fill/routing fields",
        )
    else:
        _add_check(
            checks,
            "contract_has_rows",
            False,
            "execution input contract is missing",
        )
        _add_check(
            checks,
            "summary_row_count_matches_contract",
            False,
            "execution input contract is missing",
        )
        _add_check(
            checks,
            "contract_has_no_broker_execution_fields",
            False,
            "execution input contract is missing",
        )

    passed = all(check["passed"] for check in checks)

    return {
        "health_gate": HEALTH_GATE_NAME,
        "status": "passed" if passed else "failed",
        "is_healthy": passed,
        "checks": checks,
        "failed_checks": [
            check["name"]
            for check in checks
            if not check["passed"]
        ],
    }


def snapshot_execution_input_operation_record(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    summary = operation_record.get("summary", {})

    return {
        "operation_id": operation_record.get("operation_id"),
        "operation_type": operation_record.get("operation_type"),
        "operation_name": operation_record.get("operation_name"),
        "status": operation_record.get("status"),
        "contract_version": operation_record.get("contract_version"),
        "row_count": summary.get("row_count"),
        "symbols": summary.get("symbols"),
        "sides": summary.get("sides"),
        "long_count": summary.get("long_count"),
        "short_count": summary.get("short_count"),
        "neutral_count": summary.get("neutral_count"),
        "net_target_weight": summary.get("net_target_weight"),
        "total_abs_target_weight": summary.get("total_abs_target_weight"),
        "errors": operation_record.get("errors", []),
        "attachment_keys": sorted(operation_record.get("attachments", {}).keys()),
    }


def _add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    message: str,
) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "message": message,
        }
    )


def _contains_forbidden_broker_fields(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, inner_value in value.items():
            if str(key) in _FORBIDDEN_BROKER_FIELDS:
                return True
            if _contains_forbidden_broker_fields(inner_value):
                return True

    if isinstance(value, list | tuple):
        return any(_contains_forbidden_broker_fields(item) for item in value)

    return False


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(inner_value)
            for key, inner_value in sorted(value.items(), key=lambda item: str(item[0]))
        }

    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
