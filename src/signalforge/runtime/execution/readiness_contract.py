from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from pkgutil import iter_modules
from typing import Any


RUNTIME_EXECUTION_READINESS_CONTRACT: dict[str, Any] = {
    "adapter_type": "runtime_execution_readiness_contract",
    "artifact_type": "signalforge_runtime_execution_readiness_contract",
    "candidate_id": "signalforge_v3_2_2_paper_candidate",
    "paper_trade_supported": True,
    "live_trade_supported": False,
    "requires_manual_approval": True,
    "supported_execution_modes": ["paper"],
    "blocked_execution_modes": ["live"],
    "live_blockers": [
        "broker_native_order_lifecycle_not_validated",
        "broker_native_fill_reconciliation_not_validated",
        "broker_native_close_and_defense_orders_not_validated",
        "broker_native_commission_and_fee_reconciliation_not_validated",
        "paper_trade_forward_validation_not_complete",
    ],
    "paper_execution_requirements": [
        "locked_v3_2_2_ruleset_available",
        "quote_aware_rows_available",
        "pruned_trade_rows_available",
        "paper_order_intent_translation_available",
        "manual_review_required_before_order_submission",
    ],
}


def discover_execution_modules() -> list[str]:
    package = import_module("signalforge.runtime.execution")
    package_paths = getattr(package, "__path__", [])

    modules: list[str] = []
    for module_info in iter_modules(package_paths):
        name = module_info.name
        if name.startswith("_"):
            continue
        if name in {"readiness_contract"}:
            continue
        modules.append(name)

    return sorted(modules)


def build_runtime_execution_readiness_contract() -> dict[str, Any]:
    contract = deepcopy(RUNTIME_EXECUTION_READINESS_CONTRACT)
    contract["migrated_execution_modules"] = discover_execution_modules()
    contract["migrated_execution_module_count"] = len(
        contract["migrated_execution_modules"]
    )
    contract["is_ready_for_paper"] = (
        contract["paper_trade_supported"]
        and not contract["live_trade_supported"]
        and contract["migrated_execution_module_count"] > 0
    )
    contract["is_ready_for_live"] = False
    return contract


def validate_runtime_execution_readiness_contract(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = contract or build_runtime_execution_readiness_contract()

    blockers: list[str] = []

    if not contract.get("paper_trade_supported"):
        blockers.append("paper_trade_not_supported")

    if contract.get("live_trade_supported"):
        blockers.append("live_trade_should_remain_blocked_until_validated")

    if contract.get("migrated_execution_module_count", 0) <= 0:
        blockers.append("no_migrated_execution_translation_module_found")

    if not contract.get("requires_manual_approval"):
        blockers.append("manual_approval_requirement_missing")

    return {
        "adapter_type": "runtime_execution_readiness_contract_validator",
        "artifact_type": "signalforge_runtime_execution_readiness_validation",
        "candidate_id": contract.get("candidate_id"),
        "is_ready_for_paper": len(blockers) == 0,
        "is_ready_for_live": False,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "live_blockers": contract.get("live_blockers", []),
        "migrated_execution_modules": contract.get(
            "migrated_execution_modules", []
        ),
    }


if __name__ == "__main__":
    import json

    result = validate_runtime_execution_readiness_contract()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["is_ready_for_paper"] else 1)

