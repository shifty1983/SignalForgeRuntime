from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_contracts import build_signalforge_data_source_contracts
from src.data_sources.data_source_inventory import (
    EXPLICIT_EXCLUSIONS,
    build_signalforge_data_source_inventory,
)


PLAN_SCHEMA_VERSION = "signalforge_data_source_adapter_plan.v1"

ADAPTER_PRIORITY = {
    "backtest_evidence": 1,
    "account_snapshot": 2,
    "market_price_history": 3,
    "option_chain_snapshot": 4,
    "manual_decision": 5,
    "universe_config": 6,
}


def build_signalforge_data_source_adapter_plan(
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a prioritized adapter plan from inventory and contract artifacts.

    This plan decides what normalized data-source adapters need to exist before
    downstream strategy evidence, account, market-price, options-chain, and
    manual-decision artifacts can be populated with real data.

    It does not call brokers, route orders, submit orders, model fills, perform
    live execution, model slippage, create automatic close/roll/defense orders,
    change strategies automatically, update parameters automatically, or pause
    strategies automatically.
    """

    if source is not None and not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    source = source or {}

    inventory_source = _as_mapping(source.get("inventory_source"))
    contracts_source = _as_mapping(source.get("contracts_source"))

    inventory = build_signalforge_data_source_inventory(inventory_source)
    contracts = build_signalforge_data_source_contracts(contracts_source)

    if inventory.get("status") == "blocked":
        return _blocked_result(
            "inventory_blocked",
            inventory=inventory,
            contracts=contracts,
            blocked_items=_blocked_items_from(inventory, fallback_reason="inventory_blocked"),
        )

    if contracts.get("status") == "blocked":
        return _blocked_result(
            "contracts_blocked",
            inventory=inventory,
            contracts=contracts,
            blocked_items=_blocked_items_from(contracts, fallback_reason="contracts_blocked"),
        )

    adapter_plan = _adapter_plan_entries(contracts)
    open_adapter_source_count = sum(
        1 for item in adapter_plan if item.get("source_status") != "resolved"
    )
    resolved_adapter_source_count = len(adapter_plan) - open_adapter_source_count
    open_inventory_decision_count = _safe_int(inventory.get("open_decision_count"))

    status = (
        "ready"
        if open_adapter_source_count == 0 and open_inventory_decision_count == 0 and adapter_plan
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_data_source_adapter_plan",
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "design_rule": (
            "Build adapters at the data-source boundary. Core SignalForge modules "
            "consume normalized local artifacts only."
        ),
        "inventory_status": inventory.get("status"),
        "contracts_status": contracts.get("status"),
        "inventory_summary": {
            "module_summary": inventory.get("module_summary", {}),
            "open_decision_count": inventory.get("open_decision_count", 0),
            "adapter_backlog_count": inventory.get("adapter_backlog_count", 0),
        },
        "contracts_summary": {
            "contract_summary": contracts.get("contract_summary", {}),
            "open_source_count": contracts.get("open_source_count", 0),
            "resolved_source_count": contracts.get("resolved_source_count", 0),
        },
        "adapter_plan": adapter_plan,
        "adapter_plan_summary": _adapter_plan_summary(adapter_plan),
        "open_inventory_decision_count": open_inventory_decision_count,
        "open_adapter_source_count": open_adapter_source_count,
        "resolved_adapter_source_count": resolved_adapter_source_count,
        "recommended_next_adapter": _recommended_next_adapter(adapter_plan),
        "source_decisions": list(_as_list(inventory.get("open_decisions"))),
        "inventory_artifact": inventory,
        "contracts_artifact": contracts,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _adapter_plan_entries(contracts_artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries = []

    for contract in _as_list(contracts_artifact.get("contracts")):
        contract_map = _as_mapping(contract)
        contract_name = str(contract_map.get("contract", ""))
        priority = ADAPTER_PRIORITY.get(contract_name, 999)

        entries.append(
            {
                "adapter": _adapter_name(contract_map),
                "priority": priority,
                "contract": contract_name,
                "data_category": contract_map.get("data_category"),
                "adapter_type": contract_map.get("adapter_type"),
                "expected_source": contract_map.get("expected_source"),
                "selected_source": contract_map.get("selected_source"),
                "source_status": contract_map.get("source_status", "open"),
                "required_input_artifact": contract_name,
                "required_field_count": _safe_int(contract_map.get("required_field_count")),
                "preferred_field_count": _safe_int(contract_map.get("preferred_field_count")),
                "optional_field_count": _safe_int(contract_map.get("optional_field_count")),
                "consumed_by_modules": list(_as_list(contract_map.get("consumed_by_modules"))),
                "consumed_by_module_count": _safe_int(
                    contract_map.get("consumed_by_module_count")
                ),
                "requires_normalization": contract_map.get("requires_normalization") is True,
                "external_source_boundary": contract_map.get("external_source_boundary") is True,
            }
        )

    return sorted(entries, key=lambda item: (item["priority"], str(item["adapter"])))


def _adapter_name(contract: Mapping[str, Any]) -> str:
    contract_name = str(contract.get("contract", "")).strip()
    adapter_type = str(contract.get("adapter_type", "")).strip()

    if contract_name:
        return f"{contract_name}_adapter"

    if adapter_type:
        return f"{adapter_type}_adapter"

    return "unknown_data_source_adapter"


def _adapter_plan_summary(adapter_plan: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    category_counter: Counter[str] = Counter()
    adapter_type_counter: Counter[str] = Counter()

    for item in adapter_plan:
        category_counter[str(item.get("data_category", ""))] += 1
        adapter_type_counter[str(item.get("adapter_type", ""))] += 1

    return {
        "adapter_count": len(adapter_plan),
        "open_source_count": sum(
            1 for item in adapter_plan if item.get("source_status") != "resolved"
        ),
        "resolved_source_count": sum(
            1 for item in adapter_plan if item.get("source_status") == "resolved"
        ),
        "category_count": len(category_counter),
        "adapter_type_count": len(adapter_type_counter),
        "usage_by_category": dict(sorted(category_counter.items())),
        "usage_by_adapter_type": dict(sorted(adapter_type_counter.items())),
    }


def _recommended_next_adapter(adapter_plan: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for item in adapter_plan:
        if item.get("source_status") != "resolved":
            return dict(item)

    return dict(adapter_plan[0]) if adapter_plan else None


def _blocked_result(
    reason: str,
    *,
    inventory: Mapping[str, Any] | None = None,
    contracts: Mapping[str, Any] | None = None,
    blocked_items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_data_source_adapter_plan",
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "blocked_items": [dict(item) for item in blocked_items]
        if blocked_items is not None
        else [{"reason": reason}],
        "inventory_artifact": dict(inventory or {}),
        "contracts_artifact": dict(contracts or {}),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_items_from(
    artifact: Mapping[str, Any],
    *,
    fallback_reason: str,
) -> list[dict[str, Any]]:
    blocked_items = _as_list(artifact.get("blocked_items"))
    if blocked_items:
        return [dict(_as_mapping(item)) for item in blocked_items]
    return [{"reason": fallback_reason}]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

