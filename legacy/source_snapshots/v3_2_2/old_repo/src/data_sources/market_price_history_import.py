from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_contract_validator import (
    validate_signalforge_data_source_contract_payload,
)
from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.data_sources.market_price_universe import (
    build_market_price_universe_coverage,
    universe_coverage_warning_items,
)


IMPORT_SCHEMA_VERSION = "signalforge_market_price_history_import.v1"

CONTRACT_NAME = "market_price_history"


FIELD_ALIASES = {
    "symbol": [
        "symbol",
        "ticker",
        "underlying",
        "security",
    ],
    "timestamp": [
        "timestamp",
        "time",
        "date",
        "datetime",
        "bar_time",
    ],
    "open": [
        "open",
        "o",
    ],
    "high": [
        "high",
        "h",
    ],
    "low": [
        "low",
        "l",
    ],
    "close": [
        "close",
        "c",
        "last",
    ],
    "source": [
        "source",
        "source_name",
        "provider",
        "price_source",
    ],
    "volume": [
        "volume",
        "vol",
        "v",
    ],
    "adjusted_close": [
        "adjusted_close",
        "adj_close",
        "adjusted",
    ],
    "timeframe": [
        "timeframe",
        "resolution",
        "bar_size",
        "period",
    ],
    "currency": [
        "currency",
        "quote_currency",
    ],
    "warnings": [
        "warnings",
        "import_warnings",
        "notes",
    ],
    "dividend": [
        "dividend",
        "dividends",
    ],
    "split_factor": [
        "split_factor",
        "split",
    ],
    "vwap": [
        "vwap",
    ],
    "provider_symbol": [
        "provider_symbol",
        "vendor_symbol",
        "source_symbol",
    ],
}


NUMERIC_FIELDS = {
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjusted_close",
    "dividend",
    "split_factor",
    "vwap",
}


def build_signalforge_market_price_history_import(
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize local price-history rows into SignalForge market_price_history shape.

    This adapter only transforms local JSON provided by the user. It does not call
    market-data vendors, QuantConnect, brokers, route orders, submit orders,
    model fills, perform live execution, model slippage, create automatic
    close/roll/defense orders, change strategies automatically, update
    parameters automatically, or pause strategies automatically.
    """

    if source is not None and not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    source = source or {}
    raw_rows, source_kind = _raw_rows(source)

    if raw_rows is None:
        raw_rows = [source]

    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        return _blocked_result("raw market price payload must be a mapping or list of mappings")

    if len(raw_rows) == 0:
        return _blocked_result("raw market price rows are empty")

    normalized_rows = []
    validation_artifacts = []
    blocker_items = []
    warning_items = []

    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            blocker_items.append(
                {
                    "reason": "raw market price row must be a mapping",
                    "row_index": index,
                }
            )
            continue

        normalized_row = _normalize_market_price_row(raw_row, source)
        normalized_rows.append(normalized_row)

        validation = validate_signalforge_data_source_contract_payload(
            {
                "contract": CONTRACT_NAME,
                "payload": normalized_row,
            }
        )
        validation_artifacts.append(
            {
                "row_index": index,
                "validation": validation,
            }
        )

        for item in _as_list(validation.get("blocker_items")):
            blocker_items.append(_with_row_index(item, index))

        for item in _as_list(validation.get("warning_items")):
            warning_items.append(_with_row_index(item, index))

    universe_symbol_coverage = build_market_price_universe_coverage(
        source=source,
        normalized_rows=normalized_rows,
    )
    warning_items.extend(universe_coverage_warning_items(universe_symbol_coverage))

    status = "blocked" if blocker_items else "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_market_price_history_import",
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
        "adapter_type": "market_price_import",
        "source_kind": source_kind,
        "normalized_payloads": normalized_rows,
        "normalized_payload_summary": _normalized_payload_summary(normalized_rows),
        "validation_artifacts": validation_artifacts,
        "blocker_items": blocker_items,
        "warning_items": warning_items,
        "missing_required_fields": _missing_fields(validation_artifacts, "missing_required_fields"),
        "missing_preferred_fields": _missing_fields(validation_artifacts, "missing_preferred_fields"),
        "price_history_summary": _price_history_summary(normalized_rows),
        "universe_symbol_coverage": universe_symbol_coverage,
        "raw_payload_summary": _raw_payload_summary(raw_rows),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _raw_rows(source: Mapping[str, Any]) -> tuple[Any | None, str]:
    for key, source_kind in (
        ("quantconnect_history", "quantconnect_manual_history_export"),
        ("market_price_history", "manual_market_price_history"),
        ("price_rows", "manual_price_rows"),
        ("rows", "generic_rows"),
        ("payload", "normalized_payload_candidate"),
    ):
        if key in source:
            value = source.get(key)
            if isinstance(value, Mapping):
                return [value], source_kind
            return value, source_kind

    return None, "flat_manual_source"


def _normalize_market_price_row(
    raw_row: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for field, aliases in FIELD_ALIASES.items():
        value = _first_present(raw_row, aliases)
        if value is not None:
            normalized[field] = _normalize_field_value(field, value)

    if "symbol" not in normalized:
        symbol = _first_present(source, ["symbol", "ticker", "underlying"])
        if symbol is not None:
            normalized["symbol"] = symbol

    if "source" not in normalized:
        source_name = _first_present(source, ["source", "source_name", "provider", "price_source"])
        normalized["source"] = source_name if source_name is not None else "manual market price export"

    if "timeframe" not in normalized:
        timeframe = _first_present(source, ["timeframe", "resolution", "bar_size", "period"])
        if timeframe is not None:
            normalized["timeframe"] = timeframe

    if "currency" not in normalized:
        currency = _first_present(source, ["currency", "quote_currency"])
        if currency is not None:
            normalized["currency"] = currency

    if "warnings" not in normalized:
        normalized["warnings"] = []

    return normalized


def _first_present(payload: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        if alias in payload and payload.get(alias) is not None:
            return payload.get(alias)
    return None


def _normalize_field_value(field: str, value: Any) -> Any:
    if field in NUMERIC_FIELDS:
        return _safe_float_or_original(value)

    if field == "warnings":
        return _normalize_list(value)

    return value


def _normalized_payload_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "symbols": sorted(
            {
                str(row.get("symbol"))
                for row in rows
                if isinstance(row, Mapping) and row.get("symbol") is not None
            }
        ),
        "has_volume_count": sum(1 for row in rows if row.get("volume") is not None),
        "has_adjusted_close_count": sum(
            1 for row in rows if row.get("adjusted_close") is not None
        ),
        "has_timeframe_count": sum(1 for row in rows if row.get("timeframe") is not None),
        "has_currency_count": sum(1 for row in rows if row.get("currency") is not None),
    }


def _price_history_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    timestamps = [
        str(row.get("timestamp"))
        for row in rows
        if isinstance(row, Mapping) and row.get("timestamp") is not None
    ]

    closes = [
        _safe_float_or_zero(row.get("close"))
        for row in rows
        if isinstance(row, Mapping) and row.get("close") is not None
    ]

    return {
        "row_count": len(rows),
        "symbol_count": len(
            {
                str(row.get("symbol"))
                for row in rows
                if isinstance(row, Mapping) and row.get("symbol") is not None
            }
        ),
        "start_timestamp": min(timestamps) if timestamps else None,
        "end_timestamp": max(timestamps) if timestamps else None,
        "first_close": closes[0] if closes else None,
        "last_close": closes[-1] if closes else None,
        "min_close": min(closes) if closes else None,
        "max_close": max(closes) if closes else None,
    }


def _raw_payload_summary(raw_rows: Sequence[Any]) -> dict[str, Any]:
    mapping_rows = [row for row in raw_rows if isinstance(row, Mapping)]

    return {
        "row_count": len(raw_rows),
        "mapping_row_count": len(mapping_rows),
        "non_mapping_row_count": len(raw_rows) - len(mapping_rows),
        "field_names": sorted(
            {
                str(key)
                for row in mapping_rows
                for key in row.keys()
            }
        ),
    }


def _missing_fields(
    validation_artifacts: Sequence[Mapping[str, Any]],
    field_name: str,
) -> list[str]:
    missing = []
    seen = set()

    for artifact in validation_artifacts:
        validation = artifact.get("validation")
        if not isinstance(validation, Mapping):
            continue

        for field in _as_list(validation.get(field_name)):
            field_text = str(field)
            if field_text not in seen:
                seen.add(field_text)
                missing.append(field_text)

    return missing


def _with_row_index(item: Any, row_index: int) -> dict[str, Any]:
    if isinstance(item, Mapping):
        row_item = dict(item)
    else:
        row_item = {"reason": str(item)}
    row_item["row_index"] = row_index
    return row_item


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_market_price_history_import",
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
        "adapter_type": "market_price_import",
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

