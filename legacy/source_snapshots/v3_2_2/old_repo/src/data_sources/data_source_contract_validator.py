from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_contracts import DATA_SOURCE_CONTRACTS
from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


VALIDATION_SCHEMA_VERSION = "signalforge_data_source_contract_validation.v1"

CONTRACTS_BY_NAME = {
    str(contract["contract"]): dict(contract) for contract in DATA_SOURCE_CONTRACTS
}


def validate_signalforge_data_source_contract_payload(
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a normalized data-source payload against a SignalForge contract.

    This validator checks local payload shape only. It does not call brokers,
    route orders, submit orders, model fills, perform live execution, model
    slippage, create automatic close/roll/defense orders, change strategies
    automatically, update parameters automatically, or pause strategies
    automatically.
    """

    if source is not None and not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    source = source or {}

    contract_name = _string_or_none(source.get("contract"))
    if contract_name is None:
        return _blocked_result("missing_contract")

    contract = CONTRACTS_BY_NAME.get(contract_name)
    if contract is None:
        return _blocked_result(
            "unknown_contract",
            blocked_items=[
                {
                    "reason": "unknown_contract",
                    "contract": contract_name,
                }
            ],
        )

    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return _blocked_result(
            "payload must be a mapping",
            contract=contract,
            contract_name=contract_name,
        )

    required_fields = _as_list(contract.get("required_fields"))
    preferred_fields = _as_list(contract.get("preferred_fields"))
    optional_fields = _as_list(contract.get("optional_fields"))

    missing_required_fields = _missing_fields(payload, required_fields)
    missing_preferred_fields = _missing_fields(payload, preferred_fields)
    present_optional_fields = _present_fields(payload, optional_fields)

    nested_checks = _nested_checks(contract=contract, payload=payload)

    blocker_items = [
        {
            "reason": "missing_required_field",
            "field": field,
        }
        for field in missing_required_fields
    ]
    blocker_items.extend(nested_checks["blocker_items"])

    warning_items = [
        {
            "reason": "missing_preferred_field",
            "field": field,
        }
        for field in missing_preferred_fields
    ]
    warning_items.extend(nested_checks["warning_items"])

    status = "blocked" if blocker_items else "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_data_source_contract_validation",
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "contract": contract_name,
        "data_category": contract.get("data_category"),
        "adapter_type": contract.get("adapter_type"),
        "required_field_count": len(required_fields),
        "preferred_field_count": len(preferred_fields),
        "optional_field_count": len(optional_fields),
        "present_required_field_count": len(required_fields) - len(missing_required_fields),
        "present_preferred_field_count": len(preferred_fields) - len(missing_preferred_fields),
        "present_optional_field_count": len(present_optional_fields),
        "missing_required_fields": missing_required_fields,
        "missing_preferred_fields": missing_preferred_fields,
        "present_optional_fields": present_optional_fields,
        "blocker_items": blocker_items,
        "warning_items": warning_items,
        "nested_validation": nested_checks["summary"],
        "payload_summary": _payload_summary(payload),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _nested_checks(
    *,
    contract: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    contract_name = str(contract.get("contract", ""))

    if contract_name != "account_snapshot":
        return {
            "summary": {
                "nested_check_count": 0,
                "nested_blocker_count": 0,
                "nested_warning_count": 0,
            },
            "blocker_items": [],
            "warning_items": [],
        }

    open_positions = payload.get("open_positions")
    position_required_fields = _as_list(contract.get("position_required_fields"))
    position_preferred_fields = _as_list(contract.get("position_preferred_fields"))

    # If open_positions is missing, the top-level required-field validator
    # already reports it. Do not add a duplicate nested-shape blocker.
    if open_positions is None:
        return {
            "summary": {
                "nested_check_count": 0,
                "nested_blocker_count": 0,
                "nested_warning_count": 0,
                "position_count": 0,
            },
            "blocker_items": [],
            "warning_items": [],
        }

    if not isinstance(open_positions, Sequence) or isinstance(
        open_positions, (str, bytes, bytearray)
    ):
        return {
            "summary": {
                "nested_check_count": 1,
                "nested_blocker_count": 1,
                "nested_warning_count": 0,
                "position_count": 0,
            },
            "blocker_items": [
                {
                    "reason": "open_positions must be a list",
                    "field": "open_positions",
                }
            ],
            "warning_items": [],
        }

    blocker_items = []
    warning_items = []

    for index, position in enumerate(open_positions):
        if not isinstance(position, Mapping):
            blocker_items.append(
                {
                    "reason": "position must be a mapping",
                    "position_index": index,
                }
            )
            continue

        for field in _missing_fields(position, position_required_fields):
            blocker_items.append(
                {
                    "reason": "missing_position_required_field",
                    "position_index": index,
                    "field": field,
                }
            )

        for field in _missing_fields(position, position_preferred_fields):
            warning_items.append(
                {
                    "reason": "missing_position_preferred_field",
                    "position_index": index,
                    "field": field,
                }
            )

    return {
        "summary": {
            "nested_check_count": 1,
            "nested_blocker_count": len(blocker_items),
            "nested_warning_count": len(warning_items),
            "position_count": len(open_positions),
        },
        "blocker_items": blocker_items,
        "warning_items": warning_items,
    }


def _payload_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "field_count": len(payload),
        "top_level_fields": sorted(str(key) for key in payload.keys()),
        "has_source": "source" in payload and payload.get("source") is not None,
    }


def _missing_fields(payload: Mapping[str, Any], fields: Sequence[Any]) -> list[str]:
    missing = []
    for field in fields:
        field_name = str(field)
        if field_name not in payload or payload.get(field_name) is None:
            missing.append(field_name)
    return missing


def _present_fields(payload: Mapping[str, Any], fields: Sequence[Any]) -> list[str]:
    present = []
    for field in fields:
        field_name = str(field)
        if field_name in payload and payload.get(field_name) is not None:
            present.append(field_name)
    return present


def _blocked_result(
    reason: str,
    *,
    contract: Mapping[str, Any] | None = None,
    contract_name: str | None = None,
    blocked_items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_data_source_contract_validation",
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "contract": contract_name,
        "data_category": contract.get("data_category") if contract else None,
        "adapter_type": contract.get("adapter_type") if contract else None,
        "blocker_items": [dict(item) for item in blocked_items]
        if blocked_items is not None
        else [{"reason": reason}],
        "warning_items": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

