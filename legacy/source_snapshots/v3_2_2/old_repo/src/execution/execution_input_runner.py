from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from src.execution.risk_to_execution_adapter import (
    CONTRACT_VERSION,
    ExecutionInputContractError,
    build_execution_input_contract,
    validate_execution_intent_rows,
)


RUNNER_NAME = "execution_input_contract_runner"


@dataclass(frozen=True)
class ExecutionInputRunnerResult:
    operation_name: str
    status: str
    contract_version: str
    contract: dict[str, Any] | None
    summary: dict[str, Any]
    errors: list[str]


def run_execution_input_contract(
    risk_management_output: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and validate the execution input contract.

    This runner intentionally stops at execution intent. It does not route orders,
    simulate fills, call broker APIs, or perform live execution.
    """

    try:
        contract = build_execution_input_contract(risk_management_output)
        validate_execution_intent_rows(contract["rows"])

        result = ExecutionInputRunnerResult(
            operation_name=RUNNER_NAME,
            status="passed",
            contract_version=CONTRACT_VERSION,
            contract=contract,
            summary=_build_execution_input_summary(contract),
            errors=[],
        )

        return asdict(result)

    except ExecutionInputContractError as exc:
        result = ExecutionInputRunnerResult(
            operation_name=RUNNER_NAME,
            status="failed",
            contract_version=CONTRACT_VERSION,
            contract=None,
            summary=_empty_execution_input_summary(),
            errors=[str(exc)],
        )

        return asdict(result)


def snapshot_execution_input_runner_result(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    summary = result.get("summary", {})

    return {
        "operation_name": result.get("operation_name"),
        "status": result.get("status"),
        "contract_version": result.get("contract_version"),
        "row_count": summary.get("row_count"),
        "symbols": summary.get("symbols"),
        "sides": summary.get("sides"),
        "long_count": summary.get("long_count"),
        "short_count": summary.get("short_count"),
        "neutral_count": summary.get("neutral_count"),
        "net_target_weight": summary.get("net_target_weight"),
        "total_abs_target_weight": summary.get("total_abs_target_weight"),
        "errors": result.get("errors", []),
    }


def _build_execution_input_summary(contract: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(contract.get("rows", []))

    target_weights = [float(row["target_weight"]) for row in rows]

    return {
        "contract_type": contract.get("contract_type"),
        "contract_version": contract.get("contract_version"),
        "row_count": len(rows),
        "execution_intent_ids": [row["execution_intent_id"] for row in rows],
        "source_candidate_ids": [row["source_candidate_id"] for row in rows],
        "symbols": [row["symbol"] for row in rows],
        "directions": [row["direction"] for row in rows],
        "sides": [row["side"] for row in rows],
        "long_count": sum(1 for row in rows if row["direction"] == "long"),
        "short_count": sum(1 for row in rows if row["direction"] == "short"),
        "neutral_count": sum(1 for row in rows if row["direction"] == "neutral"),
        "net_target_weight": round(sum(target_weights), 10),
        "total_abs_target_weight": round(sum(abs(weight) for weight in target_weights), 10),
        "max_abs_target_weight": round(
            max((abs(weight) for weight in target_weights), default=0.0),
            10,
        ),
    }


def _empty_execution_input_summary() -> dict[str, Any]:
    return {
        "contract_type": "execution_input_contract",
        "contract_version": CONTRACT_VERSION,
        "row_count": 0,
        "execution_intent_ids": [],
        "source_candidate_ids": [],
        "symbols": [],
        "directions": [],
        "sides": [],
        "long_count": 0,
        "short_count": 0,
        "neutral_count": 0,
        "net_target_weight": 0.0,
        "total_abs_target_weight": 0.0,
        "max_abs_target_weight": 0.0,
    }
