from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_contract_validator import (
    validate_signalforge_data_source_contract_payload,
)
from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


IMPORT_SCHEMA_VERSION = "signalforge_ibkr_account_snapshot_import.v1"

CONTRACT_NAME = "account_snapshot"


FIELD_ALIASES = {
    "snapshot_timestamp": [
        "snapshot_timestamp",
        "as_of",
        "as_of_timestamp",
        "statement_timestamp",
        "report_timestamp",
        "timestamp",
        "date",
    ],
    "net_liquidation_value": [
        "net_liquidation_value",
        "net_liquidation",
        "net_liq",
        "account_value",
        "net_asset_value",
    ],
    "open_positions": [
        "open_positions",
        "positions",
        "holdings",
        "portfolio_positions",
    ],
    "source": [
        "source",
        "source_name",
        "provider",
        "broker",
        "statement_source",
    ],
    "account_id_alias": [
        "account_id_alias",
        "account_alias",
        "account_id",
        "account",
    ],
    "cash": [
        "cash",
        "cash_balance",
        "settled_cash",
    ],
    "buying_power": [
        "buying_power",
        "available_funds",
        "available_buying_power",
    ],
    "unrealized_pnl": [
        "unrealized_pnl",
        "unrealized_pl",
        "unrealized_profit_loss",
    ],
    "realized_pnl": [
        "realized_pnl",
        "realized_pl",
        "realized_profit_loss",
    ],
    "currency": [
        "currency",
        "base_currency",
    ],
    "warnings": [
        "warnings",
        "import_warnings",
        "notes",
    ],
    "maintenance_margin": [
        "maintenance_margin",
        "maint_margin",
    ],
    "initial_margin": [
        "initial_margin",
        "init_margin",
    ],
    "excess_liquidity": [
        "excess_liquidity",
        "excess_liq",
    ],
    "day_trades_remaining": [
        "day_trades_remaining",
        "pdt_remaining",
    ],
}


POSITION_FIELD_ALIASES = {
    "symbol": [
        "symbol",
        "underlying",
        "ticker",
        "contract_symbol",
    ],
    "asset_type": [
        "asset_type",
        "security_type",
        "sec_type",
        "instrument_type",
    ],
    "quantity": [
        "quantity",
        "qty",
        "position",
        "position_qty",
    ],
    "source": [
        "source",
        "source_name",
        "provider",
        "broker",
    ],
    "average_cost": [
        "average_cost",
        "avg_cost",
        "cost_basis",
        "average_price",
    ],
    "market_price": [
        "market_price",
        "mark_price",
        "last_price",
        "price",
    ],
    "market_value": [
        "market_value",
        "value",
        "position_value",
    ],
    "unrealized_pnl": [
        "unrealized_pnl",
        "unrealized_pl",
        "unrealized_profit_loss",
    ],
    "expiration": [
        "expiration",
        "expiry",
        "expiration_date",
    ],
    "strike": [
        "strike",
        "strike_price",
    ],
    "option_type": [
        "option_type",
        "right",
        "put_call",
    ],
    "multiplier": [
        "multiplier",
        "contract_multiplier",
    ],
}


NUMERIC_FIELDS = {
    "net_liquidation_value",
    "cash",
    "buying_power",
    "unrealized_pnl",
    "realized_pnl",
    "maintenance_margin",
    "initial_margin",
    "excess_liquidity",
}

POSITION_NUMERIC_FIELDS = {
    "quantity",
    "average_cost",
    "market_price",
    "market_value",
    "unrealized_pnl",
    "strike",
    "multiplier",
}


def build_signalforge_ibkr_account_snapshot_import(
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a local IBKR/account export into SignalForge account_snapshot shape.

    This adapter only transforms local JSON provided by the user. It does not call
    IBKR, call brokers, route orders, submit orders, model fills, perform live
    execution, model slippage, create automatic close/roll/defense orders, change
    strategies automatically, update parameters automatically, or pause strategies
    automatically.
    """

    if source is not None and not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    source = source or {}
    raw_payload = _raw_payload(source)

    if raw_payload is not None and not isinstance(raw_payload, Mapping):
        return _blocked_result("raw account payload must be a mapping")

    raw_payload = raw_payload or source
    normalized_payload = _normalize_account_snapshot(raw_payload)

    validation = validate_signalforge_data_source_contract_payload(
        {
            "contract": CONTRACT_NAME,
            "payload": normalized_payload,
        }
    )

    status = str(validation.get("status", "needs_review"))

    return {
        "artifact_type": "signalforge_ibkr_account_snapshot_import",
        "schema_version": IMPORT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "contract": CONTRACT_NAME,
        "adapter_type": "broker_account_import",
        "source_kind": _source_kind(source),
        "normalized_payload": normalized_payload,
        "normalized_payload_summary": _normalized_payload_summary(normalized_payload),
        "validation_artifact": validation,
        "blocker_items": list(_as_list(validation.get("blocker_items"))),
        "warning_items": list(_as_list(validation.get("warning_items"))),
        "missing_required_fields": list(_as_list(validation.get("missing_required_fields"))),
        "missing_preferred_fields": list(_as_list(validation.get("missing_preferred_fields"))),
        "account_summary": _account_summary(normalized_payload),
        "position_summary": _position_summary(normalized_payload),
        "raw_payload_summary": _raw_payload_summary(raw_payload),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _raw_payload(source: Mapping[str, Any]) -> Any:
    if "ibkr_statement" in source:
        return source.get("ibkr_statement")
    if "account_snapshot" in source:
        return source.get("account_snapshot")
    if "payload" in source:
        return source.get("payload")
    return None


def _source_kind(source: Mapping[str, Any]) -> str:
    if "ibkr_statement" in source:
        return "ibkr_statement_export"
    if "account_snapshot" in source:
        return "manual_account_snapshot"
    if "payload" in source:
        return "normalized_payload_candidate"
    return "flat_manual_source"


def _normalize_account_snapshot(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for field, aliases in FIELD_ALIASES.items():
        value = _first_present(raw_payload, aliases)
        if value is not None:
            normalized[field] = _normalize_account_field(field, value)

    if "source" not in normalized:
        normalized["source"] = "IBKR statement export"

    if "warnings" not in normalized:
        normalized["warnings"] = []

    raw_positions = _first_present(raw_payload, FIELD_ALIASES["open_positions"])
    if raw_positions is not None:
        normalized["open_positions"] = _normalize_positions(raw_positions, normalized["source"])

    return normalized


def _normalize_positions(raw_positions: Any, default_source: Any) -> list[Any]:
    if not isinstance(raw_positions, Sequence) or isinstance(
        raw_positions, (str, bytes, bytearray)
    ):
        return raw_positions

    positions = []
    for raw_position in raw_positions:
        if not isinstance(raw_position, Mapping):
            positions.append(raw_position)
            continue

        position: dict[str, Any] = {}
        for field, aliases in POSITION_FIELD_ALIASES.items():
            value = _first_present(raw_position, aliases)
            if value is not None:
                position[field] = _normalize_position_field(field, value)

        if "source" not in position and default_source is not None:
            position["source"] = default_source

        positions.append(position)

    return positions


def _first_present(payload: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        if alias in payload and payload.get(alias) is not None:
            return payload.get(alias)
    return None


def _normalize_account_field(field: str, value: Any) -> Any:
    if field in NUMERIC_FIELDS:
        return _safe_float_or_original(value)

    if field == "day_trades_remaining":
        return _safe_int_or_original(value)

    if field == "warnings":
        return _normalize_list(value)

    return value


def _normalize_position_field(field: str, value: Any) -> Any:
    if field in POSITION_NUMERIC_FIELDS:
        return _safe_float_or_original(value)

    if field == "asset_type":
        return str(value).lower()

    if field == "option_type":
        return str(value).lower()

    return value


def _normalized_payload_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    positions = _as_list(payload.get("open_positions"))

    return {
        "field_count": len(payload),
        "has_snapshot_timestamp": "snapshot_timestamp" in payload,
        "has_net_liquidation_value": "net_liquidation_value" in payload,
        "has_open_positions": "open_positions" in payload,
        "position_count": len(positions),
        "has_cash": "cash" in payload,
        "has_buying_power": "buying_power" in payload,
        "has_account_id_alias": "account_id_alias" in payload,
        "top_level_fields": sorted(str(key) for key in payload.keys()),
    }


def _account_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_timestamp": payload.get("snapshot_timestamp"),
        "account_id_alias": payload.get("account_id_alias"),
        "net_liquidation_value": payload.get("net_liquidation_value"),
        "cash": payload.get("cash"),
        "buying_power": payload.get("buying_power"),
        "unrealized_pnl": payload.get("unrealized_pnl"),
        "realized_pnl": payload.get("realized_pnl"),
        "currency": payload.get("currency"),
        "source": payload.get("source"),
    }


def _position_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    positions = _as_list(payload.get("open_positions"))
    option_positions = [
        item for item in positions if isinstance(item, Mapping) and item.get("asset_type") == "option"
    ]

    return {
        "position_count": len(positions),
        "option_position_count": len(option_positions),
        "symbols": [
            str(item.get("symbol"))
            for item in positions
            if isinstance(item, Mapping) and item.get("symbol") is not None
        ],
        "net_quantity": sum(
            _safe_float_or_zero(item.get("quantity"))
            for item in positions
            if isinstance(item, Mapping)
        ),
    }


def _raw_payload_summary(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "field_count": len(raw_payload),
        "top_level_fields": sorted(str(key) for key in raw_payload.keys()),
    }


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_ibkr_account_snapshot_import",
        "schema_version": IMPORT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "contract": CONTRACT_NAME,
        "adapter_type": "broker_account_import",
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _normalize_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    if value is None:
        return []
    return [value]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _safe_float_or_original(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _safe_float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int_or_original(value: Any) -> Any:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return value

