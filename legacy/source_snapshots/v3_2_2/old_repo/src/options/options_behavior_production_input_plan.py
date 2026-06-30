from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_SCHEMA_VERSION = (
    "signalforge_options_behavior_production_input_plan.v1"
)

COVERED_CAPABILITIES = [
    "options_behavior_production_input_plan",
    "full_universe_options_input_contract",
    "option_row_field_readiness",
    "options_behavior_source_compatibility",
    "manual_import_format_readiness",
]

OPTIONS_BEHAVIOR_CAPABILITY_FIELDS = {
    "iv_level": ["implied_volatility"],
    "iv_rank_percentile": ["underlying_symbol", "quote_date", "implied_volatility"],
    "iv_expansion_contraction": ["underlying_symbol", "quote_date", "implied_volatility"],
    "skew_behavior": [
        "underlying_symbol",
        "quote_date",
        "expiration",
        "strike",
        "option_right",
        "implied_volatility",
        "underlying_price",
    ],
    "term_structure_behavior": [
        "underlying_symbol",
        "quote_date",
        "expiration",
        "implied_volatility",
    ],
    "liquidity_state": ["bid", "ask", "open_interest", "volume"],
    "spread_width": ["bid", "ask"],
    "open_interest_behavior": ["open_interest"],
    "volume_behavior": ["volume"],
    "gamma_concentration": ["gamma", "strike", "expiration", "open_interest"],
    "delta_availability": ["delta"],
    "theta_sensitivity": ["theta"],
    "vega_sensitivity": ["vega"],
    "volatility_risk_premium": ["implied_volatility"],
}

CORE_OPTION_ROW_FIELDS = [
    "underlying_symbol",
    "quote_date",
    "expiration",
    "strike",
    "option_right",
    "bid",
    "ask",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "open_interest",
    "volume",
    "underlying_price",
]

OPTIONAL_OPTION_ROW_FIELDS = [
    "option_symbol",
    "dte",
    "moneyness",
    "mid_price",
    "mark_price",
    "last_price",
    "theoretical_value",
    "probability_itm",
    "probability_otm",
    "earnings_date",
    "event_flag",
    "source_vendor",
]

FIELD_ALIASES = {
    "underlying_symbol": ("underlying_symbol", "symbol", "ticker", "underlying"),
    "quote_date": ("quote_date", "date", "as_of_date", "timestamp", "time"),
    "expiration": ("expiration", "expiry", "expiration_date", "expiry_date"),
    "strike": ("strike", "strike_price"),
    "option_right": ("option_right", "right", "type", "option_type", "put_call", "call_put"),
    "bid": ("bid", "bid_price"),
    "ask": ("ask", "ask_price", "offer", "offer_price"),
    "implied_volatility": ("implied_volatility", "iv", "mid_iv", "smv_vol", "volatility"),
    "delta": ("delta",),
    "gamma": ("gamma",),
    "theta": ("theta",),
    "vega": ("vega",),
    "open_interest": ("open_interest", "oi"),
    "volume": ("volume", "option_volume"),
    "underlying_price": ("underlying_price", "underlying_last", "spot", "spot_price", "underlying_close"),
    "asset_realized_volatility": (
        "asset_realized_volatility",
        "realized_volatility",
        "realized_volatility_20d",
        "selected_realized_volatility",
    ),
}

ROW_CONTAINER_KEYS = (
    "option_rows",
    "rows",
    "data",
    "items",
    "contracts",
    "option_chain_rows",
    "option_analytics_rows",
)

SYMBOL_CONTAINER_KEYS = (
    "symbols",
    "universe",
    "tickers",
    "asset_symbols",
)

ITEM_CONTAINER_KEYS = (
    "asset_behavior_items",
    "asset_behaviors",
    "market_price_behavior_items",
    "options_behavior_items",
    "items",
    "rows",
    "data",
)

SOURCE_COMPATIBILITY = [
    {
        "source_type": "manual_json_snapshot",
        "compatibility_state": "compatible",
        "notes": "Use the documented option_rows JSON shape with one row per contract observation.",
    },
    {
        "source_type": "broker_snapshot_or_api",
        "compatibility_state": "compatible_if_fields_present",
        "notes": "Broker data is suitable when it includes quotes, Greeks, IV, OI, volume, expiration, strike, and option right. This artifact does not call the broker API.",
    },
    {
        "source_type": "ORATS_or_similar_vendor",
        "compatibility_state": "compatible_if_mapped",
        "notes": "Vendor analytics are suitable when mapped into canonical SignalForge fields. Proprietary vendor forecasts are optional enhancements, not required for ETF MVP.",
    },
    {
        "source_type": "quantconnect_raw_export",
        "compatibility_state": "not_assumed",
        "notes": "Raw QuantConnect export is not assumed because prior workflow constraints blocked local raw data export. Compact derived summaries may still be mapped into SignalForge fields.",
    },
]


def build_signalforge_options_behavior_production_input_plan(
    *,
    universe_source: Mapping[str, Any] | Sequence[Any] | None = None,
    option_source: Mapping[str, Any] | Sequence[Any] | None = None,
    min_rows_per_symbol: int = 3,
) -> dict[str, Any]:
    """Define and validate production option-row input requirements.

    The artifact is a data-contract/readiness plan for Path B. It does not call
    vendor APIs, broker APIs, route orders, select contracts, or execute trades.
    """

    min_rows = max(int(min_rows_per_symbol or 1), 1)
    universe_symbols = _extract_symbols(universe_source)
    option_rows = _extract_rows(option_source)
    option_symbols = _extract_symbols(option_rows)

    symbols = sorted(universe_symbols or option_symbols)

    if not symbols:
        return _blocked_result(
            "no symbols found in universe_source or option_source",
            min_rows_per_symbol=min_rows,
        )

    rows_by_symbol = _rows_by_symbol(option_rows)
    items = [
        _build_symbol_item(
            symbol=symbol,
            rows=rows_by_symbol.get(symbol, []),
            min_rows_per_symbol=min_rows,
        )
        for symbol in symbols
    ]
    summary = _summary(items, option_rows)
    status = "ready" if summary["production_input_ready_symbol_count"] == len(symbols) else "needs_review"

    return {
        "artifact_type": "signalforge_options_behavior_production_input_plan",
        "schema_version": OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "options_behavior_production_input_plan",
        "adapter_type": "options_behavior_production_input_plan_builder",
        "review_scope": "full_universe_options_input_contract_not_data_vendor_or_execution_workflow",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": [
            "asset_universe",
            "option_row_source",
            "options_behavior_integration",
        ],
        "minimum_rows_per_symbol": min_rows,
        "core_option_row_fields": list(CORE_OPTION_ROW_FIELDS),
        "optional_option_row_fields": list(OPTIONAL_OPTION_ROW_FIELDS),
        "field_aliases": {key: list(value) for key, value in FIELD_ALIASES.items()},
        "options_behavior_capability_fields": {
            key: list(value) for key, value in OPTIONS_BEHAVIOR_CAPABILITY_FIELDS.items()
        },
        "source_compatibility": list(SOURCE_COMPATIBILITY),
        "manual_import_contract": _manual_import_contract(min_rows),
        "options_behavior_production_input_items": items,
        "options_behavior_production_input_summary": summary,
        "next_build_recommendations": [
            {
                "capability": "full_universe_options_behavior_input",
                "priority": "high",
                "recommendation": "Provide option rows for the full universe using the canonical option_rows contract, then rerun IV, gamma, theta, volatility-risk-premium, integration, alignment, eligibility, EV, and final-review artifacts.",
            }
        ],
        "blocked_reasons": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_result(reason: str, *, min_rows_per_symbol: int) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_options_behavior_production_input_plan",
        "schema_version": OPTIONS_BEHAVIOR_PRODUCTION_INPUT_PLAN_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "options_behavior_production_input_plan",
        "adapter_type": "options_behavior_production_input_plan_builder",
        "review_scope": "full_universe_options_input_contract_not_data_vendor_or_execution_workflow",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": ["asset_universe", "option_row_source"],
        "minimum_rows_per_symbol": min_rows_per_symbol,
        "core_option_row_fields": list(CORE_OPTION_ROW_FIELDS),
        "optional_option_row_fields": list(OPTIONAL_OPTION_ROW_FIELDS),
        "field_aliases": {key: list(value) for key, value in FIELD_ALIASES.items()},
        "options_behavior_capability_fields": {
            key: list(value) for key, value in OPTIONS_BEHAVIOR_CAPABILITY_FIELDS.items()
        },
        "source_compatibility": list(SOURCE_COMPATIBILITY),
        "manual_import_contract": _manual_import_contract(min_rows_per_symbol),
        "options_behavior_production_input_items": [],
        "options_behavior_production_input_summary": {
            "symbol_count": 0,
            "option_row_count": 0,
            "production_input_ready_symbol_count": 0,
            "production_input_review_symbol_count": 0,
            "blocked_symbol_count": 0,
            "coverage_status_counts": {},
            "missing_field_counts": {},
            "row_count_state_counts": {},
            "covered_capabilities": list(COVERED_CAPABILITIES),
        },
        "next_build_recommendations": [],
        "blocked_reasons": [reason],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_symbol_item(
    *,
    symbol: str,
    rows: Sequence[Mapping[str, Any]],
    min_rows_per_symbol: int,
) -> dict[str, Any]:
    field_presence = {
        field: _field_present(rows, field) for field in CORE_OPTION_ROW_FIELDS
    }
    missing_fields = [field for field, present in field_presence.items() if not present]
    row_count = len(rows)
    row_count_state = "sufficient_rows" if row_count >= min_rows_per_symbol else "insufficient_rows"
    capability_status = {
        capability: _capability_status(fields, field_presence)
        for capability, fields in OPTIONS_BEHAVIOR_CAPABILITY_FIELDS.items()
    }
    missing_capabilities = [
        capability for capability, status in capability_status.items() if status != "ready"
    ]

    review_reasons = []
    if row_count == 0:
        review_reasons.append("missing_option_rows")
    elif row_count < min_rows_per_symbol:
        review_reasons.append("insufficient_option_rows")
    if missing_fields:
        review_reasons.append("missing_required_option_fields")
    if missing_capabilities:
        review_reasons.append("missing_required_capability_inputs")

    coverage_status = "ready" if not review_reasons else "needs_review"

    return {
        "symbol": symbol,
        "coverage_status": coverage_status,
        "option_row_count": row_count,
        "minimum_rows_per_symbol": min_rows_per_symbol,
        "row_count_state": row_count_state,
        "field_presence": field_presence,
        "missing_required_fields": missing_fields,
        "capability_input_status": capability_status,
        "missing_capability_inputs": missing_capabilities,
        "review_reasons": review_reasons,
        "manual_import_ready": coverage_status == "ready",
        "production_input_handoff": "ready_for_options_behavior_build" if coverage_status == "ready" else "data_review_required",
    }


def _capability_status(fields: Sequence[str], field_presence: Mapping[str, bool]) -> str:
    missing = [field for field in fields if not field_presence.get(field, False)]
    return "ready" if not missing else "missing_inputs"


def _field_present(rows: Sequence[Mapping[str, Any]], field: str) -> bool:
    aliases = FIELD_ALIASES.get(field, (field,))
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for alias in aliases:
            if alias in row and _has_value(row.get(alias)):
                return True
    return False


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _summary(items: Sequence[Mapping[str, Any]], option_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage = Counter(str(item.get("coverage_status")) for item in items)
    row_states = Counter(str(item.get("row_count_state")) for item in items)
    missing_fields = Counter(
        field
        for item in items
        for field in item.get("missing_required_fields", [])
    )
    missing_capabilities = Counter(
        capability
        for item in items
        for capability in item.get("missing_capability_inputs", [])
    )
    review_reasons = Counter(
        reason for item in items for reason in item.get("review_reasons", [])
    )

    ready_count = coverage.get("ready", 0)
    review_count = coverage.get("needs_review", 0)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "symbol_count": len(items),
        "option_row_count": len(option_rows),
        "production_input_ready_symbol_count": ready_count,
        "production_input_review_symbol_count": review_count,
        "blocked_symbol_count": coverage.get("blocked", 0),
        "coverage_status_counts": dict(sorted(coverage.items())),
        "row_count_state_counts": dict(sorted(row_states.items())),
        "missing_field_counts": dict(sorted(missing_fields.items())),
        "missing_capability_input_counts": dict(sorted(missing_capabilities.items())),
        "review_reason_counts": dict(sorted(review_reasons.items())),
        "source_contract_state": "ready" if review_count == 0 and items else "needs_review",
    }


def _manual_import_contract(min_rows_per_symbol: int) -> dict[str, Any]:
    return {
        "artifact_shape": "mapping_with_option_rows_array",
        "minimum_rows_per_symbol": min_rows_per_symbol,
        "root_key": "option_rows",
        "required_row_fields": list(CORE_OPTION_ROW_FIELDS),
        "optional_row_fields": list(OPTIONAL_OPTION_ROW_FIELDS),
        "example_row": {
            "underlying_symbol": "SPY",
            "quote_date": "2026-06-10",
            "expiration": "2026-07-17",
            "strike": 500,
            "option_right": "call",
            "bid": 4.8,
            "ask": 5.1,
            "implied_volatility": 0.22,
            "delta": 0.45,
            "gamma": 0.03,
            "theta": -0.04,
            "vega": 0.12,
            "open_interest": 1000,
            "volume": 50,
            "underlying_price": 498.25,
        },
    }


def _extract_rows(source: Mapping[str, Any] | Sequence[Any] | None) -> list[Mapping[str, Any]]:
    if source is None:
        return []
    if isinstance(source, Mapping):
        for key in ROW_CONTAINER_KEYS:
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [row for row in value if isinstance(row, Mapping)]
        return []
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        return [row for row in source if isinstance(row, Mapping)]
    return []


def _extract_symbols(source: Any) -> set[str]:
    symbols: set[str] = set()
    if source is None:
        return symbols

    if isinstance(source, str):
        symbol = source.strip().upper()
        if symbol:
            symbols.add(symbol)
        return symbols

    if isinstance(source, Mapping):
        for key in SYMBOL_CONTAINER_KEYS:
            value = source.get(key)
            symbols.update(_extract_symbols(value))
        for key in ITEM_CONTAINER_KEYS:
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                symbols.update(_extract_symbols(value))
        for alias in FIELD_ALIASES["underlying_symbol"]:
            if alias in source and _has_value(source.get(alias)):
                symbols.add(str(source.get(alias)).strip().upper())
        return symbols

    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        for item in source:
            symbols.update(_extract_symbols(item))
        return symbols

    return symbols


def _rows_by_symbol(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = _row_symbol(row)
        if symbol:
            grouped[symbol].append(row)
    return dict(grouped)


def _row_symbol(row: Mapping[str, Any]) -> str | None:
    for alias in FIELD_ALIASES["underlying_symbol"]:
        value = row.get(alias)
        if _has_value(value):
            return str(value).strip().upper()
    return None
