from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.signalforge.engines.options.options_behavior_production_input_plan import (
    CORE_OPTION_ROW_FIELDS,
    FIELD_ALIASES,
    OPTIONAL_OPTION_ROW_FIELDS,
)


PRODUCTION_OPTION_ROW_IMPORT_VALIDATOR_SCHEMA_VERSION = (
    "signalforge_production_option_row_import_validator.v1"
)

COVERED_CAPABILITIES = [
    "production_option_row_import_validator",
    "structural_option_row_validation",
    "decision_complete_option_slice_validation",
    "filtered_relevant_contract_slice",
    "option_row_source_quality_gate",
]

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


DEFAULT_MIN_STRUCTURAL_ROWS_PER_SYMBOL = 3
DEFAULT_MIN_PRODUCTION_ROWS_PER_SYMBOL = 20
DEFAULT_MIN_EXPIRATION_COUNT = 2
DEFAULT_MIN_LIQUID_CONTRACT_COUNT = 4
DEFAULT_MIN_ROWS_PER_EXPIRATION = 4
DEFAULT_MIN_DTE = 7
DEFAULT_MAX_DTE = 90
DEFAULT_MONEYNESS_LOWER_BOUND = 0.80
DEFAULT_MONEYNESS_UPPER_BOUND = 1.20
DEFAULT_MAX_SPREAD_PCT = 0.15
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_VOLUME = 1


def build_signalforge_production_option_row_import_validator(
    *,
    universe_source: Mapping[str, Any] | Sequence[Any] | None = None,
    option_source: Mapping[str, Any] | Sequence[Any] | None = None,
    min_structural_rows_per_symbol: int = DEFAULT_MIN_STRUCTURAL_ROWS_PER_SYMBOL,
    min_production_rows_per_symbol: int = DEFAULT_MIN_PRODUCTION_ROWS_PER_SYMBOL,
    min_expiration_count: int = DEFAULT_MIN_EXPIRATION_COUNT,
    min_liquid_contract_count: int = DEFAULT_MIN_LIQUID_CONTRACT_COUNT,
    min_rows_per_expiration: int = DEFAULT_MIN_ROWS_PER_EXPIRATION,
    min_dte: int = DEFAULT_MIN_DTE,
    max_dte: int = DEFAULT_MAX_DTE,
    moneyness_lower_bound: float = DEFAULT_MONEYNESS_LOWER_BOUND,
    moneyness_upper_bound: float = DEFAULT_MONEYNESS_UPPER_BOUND,
    max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
    min_open_interest: int = DEFAULT_MIN_OPEN_INTEREST,
    min_volume: int = DEFAULT_MIN_VOLUME,
) -> dict[str, Any]:
    """Validate an option-row source before it feeds Options Behavior builders.

    This artifact separates structural file validity from production decision
    adequacy. Three rows can prove that a source is shaped correctly, but a
    larger filtered and liquid option slice is required before strategy-selection
    decisions should use the rows.
    """

    thresholds = _thresholds(
        min_structural_rows_per_symbol=min_structural_rows_per_symbol,
        min_production_rows_per_symbol=min_production_rows_per_symbol,
        min_expiration_count=min_expiration_count,
        min_liquid_contract_count=min_liquid_contract_count,
        min_rows_per_expiration=min_rows_per_expiration,
        min_dte=min_dte,
        max_dte=max_dte,
        moneyness_lower_bound=moneyness_lower_bound,
        moneyness_upper_bound=moneyness_upper_bound,
        max_spread_pct=max_spread_pct,
        min_open_interest=min_open_interest,
        min_volume=min_volume,
    )

    universe_symbols = _extract_symbols(universe_source)
    option_rows = _extract_rows(option_source)
    option_symbols = _extract_symbols(option_rows)
    symbols = sorted(universe_symbols or option_symbols)

    if not symbols:
        return _blocked_result(
            "no symbols found in universe_source or option_source",
            thresholds=thresholds,
        )

    rows_by_symbol = _rows_by_symbol(option_rows)
    items = [
        _build_symbol_item(
            symbol=symbol,
            rows=rows_by_symbol.get(symbol, []),
            thresholds=thresholds,
        )
        for symbol in symbols
    ]
    summary = _summary(items, option_rows)
    status = (
        "ready"
        if summary["production_ready_symbol_count"] == len(symbols) and symbols
        else "needs_review"
    )

    return {
        "artifact_type": "signalforge_production_option_row_import_validator",
        "schema_version": PRODUCTION_OPTION_ROW_IMPORT_VALIDATOR_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "production_option_row_import_validator",
        "adapter_type": "production_option_row_import_validator_builder",
        "review_scope": "option_row_import_validation_not_vendor_access_or_execution_workflow",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": [
            "asset_universe",
            "option_row_source",
            "options_behavior_production_input_plan",
        ],
        "core_option_row_fields": list(CORE_OPTION_ROW_FIELDS),
        "optional_option_row_fields": list(OPTIONAL_OPTION_ROW_FIELDS),
        "validation_thresholds": thresholds,
        "production_slice_policy": {
            "row_policy": "filtered_relevant_rows_not_all_raw_chain_rows",
            "decision_slice": "contracts_inside_dte_moneyness_and_liquidity_filters",
            "minimum_structural_rows_are_for_smoke_validation_only": True,
        },
        "production_option_row_import_items": items,
        "production_option_row_import_summary": summary,
        "next_build_recommendations": [
            {
                "capability": "full_universe_options_behavior_input",
                "priority": "high",
                "recommendation": "Use production-ready option rows to rerun IV history, IV expansion, gamma, theta, volatility-risk-premium, Options Behavior integration, alignment, eligibility, EV, and final-review artifacts.",
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


def _thresholds(**kwargs: Any) -> dict[str, Any]:
    return {
        "min_structural_rows_per_symbol": max(int(kwargs["min_structural_rows_per_symbol"] or 1), 1),
        "min_production_rows_per_symbol": max(int(kwargs["min_production_rows_per_symbol"] or 1), 1),
        "min_expiration_count": max(int(kwargs["min_expiration_count"] or 1), 1),
        "min_liquid_contract_count": max(int(kwargs["min_liquid_contract_count"] or 1), 1),
        "min_rows_per_expiration": max(int(kwargs["min_rows_per_expiration"] or 1), 1),
        "min_dte": int(kwargs["min_dte"]),
        "max_dte": int(kwargs["max_dte"]),
        "moneyness_lower_bound": float(kwargs["moneyness_lower_bound"]),
        "moneyness_upper_bound": float(kwargs["moneyness_upper_bound"]),
        "max_spread_pct": float(kwargs["max_spread_pct"]),
        "min_open_interest": int(kwargs["min_open_interest"]),
        "min_volume": int(kwargs["min_volume"]),
    }


def _blocked_result(reason: str, *, thresholds: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_production_option_row_import_validator",
        "schema_version": PRODUCTION_OPTION_ROW_IMPORT_VALIDATOR_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "production_option_row_import_validator",
        "adapter_type": "production_option_row_import_validator_builder",
        "review_scope": "option_row_import_validation_not_vendor_access_or_execution_workflow",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": ["asset_universe", "option_row_source"],
        "core_option_row_fields": list(CORE_OPTION_ROW_FIELDS),
        "optional_option_row_fields": list(OPTIONAL_OPTION_ROW_FIELDS),
        "validation_thresholds": dict(thresholds),
        "production_slice_policy": {
            "row_policy": "filtered_relevant_rows_not_all_raw_chain_rows",
            "decision_slice": "contracts_inside_dte_moneyness_and_liquidity_filters",
            "minimum_structural_rows_are_for_smoke_validation_only": True,
        },
        "production_option_row_import_items": [],
        "production_option_row_import_summary": {
            "covered_capabilities": list(COVERED_CAPABILITIES),
            "symbol_count": 0,
            "option_row_count": 0,
            "production_ready_symbol_count": 0,
            "production_review_symbol_count": 0,
            "structurally_valid_symbol_count": 0,
            "limited_decision_support_symbol_count": 0,
            "blocked_symbol_count": 0,
            "coverage_status_counts": {},
            "decision_readiness_counts": {},
            "review_reason_counts": {},
            "structural_contract_state_counts": {},
            "production_contract_state_counts": {},
            "source_contract_state": "blocked",
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
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    complete_rows = [row for row in rows if _missing_required_fields(row) == []]
    relevant_rows = [row for row in complete_rows if _is_relevant_row(row, thresholds)]
    liquid_rows = [row for row in relevant_rows if _is_liquid_row(row, thresholds)]

    expiration_counts = Counter(_canonical_expiration(row) for row in relevant_rows)
    expirations = sorted(exp for exp in expiration_counts if exp)
    rights = sorted({_canonical_right(row) for row in relevant_rows if _canonical_right(row)})

    field_presence = {field: _field_present(rows, field) for field in CORE_OPTION_ROW_FIELDS}
    missing_fields = [field for field, present in field_presence.items() if not present]

    review_reasons: list[str] = []
    if not rows:
        review_reasons.append("missing_option_rows")
    if len(complete_rows) < thresholds["min_structural_rows_per_symbol"]:
        review_reasons.append("insufficient_structural_rows")
    if missing_fields:
        review_reasons.append("missing_required_option_fields")
    if len(relevant_rows) < thresholds["min_production_rows_per_symbol"]:
        review_reasons.append("insufficient_relevant_production_rows")
    if len(expirations) < thresholds["min_expiration_count"]:
        review_reasons.append("insufficient_expiration_coverage")
    if not {"call", "put"}.issubset(set(rights)):
        review_reasons.append("missing_call_put_coverage")
    if not _has_min_rows_per_expiration(expiration_counts, thresholds["min_rows_per_expiration"]):
        review_reasons.append("insufficient_rows_per_expiration")
    if len(liquid_rows) < thresholds["min_liquid_contract_count"]:
        review_reasons.append("insufficient_liquid_contracts")

    structurally_valid = (
        len(complete_rows) >= thresholds["min_structural_rows_per_symbol"]
        and not missing_fields
    )
    production_ready = not review_reasons

    if production_ready:
        coverage_status = "production_ready"
        decision_readiness = "strategy_selection_ready"
        production_contract_state = "production_ready"
        handoff = "ready_for_options_behavior_build"
    elif structurally_valid:
        coverage_status = "production_needs_review"
        decision_readiness = "limited_decision_support"
        production_contract_state = "production_needs_review"
        handoff = "data_review_required"
    else:
        coverage_status = "data_review_required"
        decision_readiness = "smoke_only_or_invalid"
        production_contract_state = "data_review_required"
        handoff = "data_review_required"

    return {
        "symbol": symbol,
        "coverage_status": coverage_status,
        "decision_readiness": decision_readiness,
        "production_input_handoff": handoff,
        "structural_contract_state": "structurally_valid" if structurally_valid else "structural_needs_review",
        "production_contract_state": production_contract_state,
        "option_row_count": len(rows),
        "complete_required_row_count": len(complete_rows),
        "relevant_production_row_count": len(relevant_rows),
        "liquid_contract_count": len(liquid_rows),
        "expiration_count": len(expirations),
        "option_rights": rights,
        "expiration_row_counts": dict(sorted(expiration_counts.items())),
        "minimum_structural_rows_per_symbol": thresholds["min_structural_rows_per_symbol"],
        "minimum_production_rows_per_symbol": thresholds["min_production_rows_per_symbol"],
        "minimum_liquid_contract_count": thresholds["min_liquid_contract_count"],
        "field_presence": field_presence,
        "missing_required_fields": missing_fields,
        "review_reasons": sorted(set(review_reasons)),
    }


def _summary(items: Sequence[Mapping[str, Any]], option_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage = Counter(str(item.get("coverage_status")) for item in items)
    readiness = Counter(str(item.get("decision_readiness")) for item in items)
    structural = Counter(str(item.get("structural_contract_state")) for item in items)
    production = Counter(str(item.get("production_contract_state")) for item in items)
    review_reasons = Counter(reason for item in items for reason in item.get("review_reasons", []))
    missing_fields = Counter(field for item in items for field in item.get("missing_required_fields", []))

    ready_count = coverage.get("production_ready", 0)
    review_count = len(items) - ready_count

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "symbol_count": len(items),
        "option_row_count": len(option_rows),
        "production_ready_symbol_count": ready_count,
        "production_review_symbol_count": review_count,
        "structurally_valid_symbol_count": structural.get("structurally_valid", 0),
        "limited_decision_support_symbol_count": readiness.get("limited_decision_support", 0),
        "blocked_symbol_count": coverage.get("blocked", 0),
        "coverage_status_counts": dict(sorted(coverage.items())),
        "decision_readiness_counts": dict(sorted(readiness.items())),
        "structural_contract_state_counts": dict(sorted(structural.items())),
        "production_contract_state_counts": dict(sorted(production.items())),
        "review_reason_counts": dict(sorted(review_reasons.items())),
        "missing_field_counts": dict(sorted(missing_fields.items())),
        "source_contract_state": "production_ready" if ready_count == len(items) and items else "production_needs_review",
    }


def _is_relevant_row(row: Mapping[str, Any], thresholds: Mapping[str, Any]) -> bool:
    dte = _row_dte(row)
    moneyness = _row_moneyness(row)
    if dte is None or moneyness is None:
        return False
    return (
        thresholds["min_dte"] <= dte <= thresholds["max_dte"]
        and thresholds["moneyness_lower_bound"] <= moneyness <= thresholds["moneyness_upper_bound"]
    )


def _is_liquid_row(row: Mapping[str, Any], thresholds: Mapping[str, Any]) -> bool:
    bid = _number(_field_value(row, "bid"))
    ask = _number(_field_value(row, "ask"))
    oi = _number(_field_value(row, "open_interest"))
    volume = _number(_field_value(row, "volume"))
    if bid is None or ask is None or oi is None or volume is None:
        return False
    if bid < 0 or ask <= 0 or ask < bid:
        return False
    mid = (bid + ask) / 2
    if mid <= 0:
        return False
    spread_pct = (ask - bid) / mid
    return (
        spread_pct <= thresholds["max_spread_pct"]
        and oi >= thresholds["min_open_interest"]
        and volume >= thresholds["min_volume"]
    )


def _has_min_rows_per_expiration(expiration_counts: Mapping[str, int], minimum: int) -> bool:
    if not expiration_counts:
        return False
    return all(count >= minimum for expiration, count in expiration_counts.items() if expiration)


def _row_dte(row: Mapping[str, Any]) -> int | None:
    explicit = _number(row.get("dte"))
    if explicit is not None:
        return int(explicit)
    quote_date = _parse_date(_field_value(row, "quote_date"))
    expiration = _parse_date(_field_value(row, "expiration"))
    if quote_date is None or expiration is None:
        return None
    return (expiration - quote_date).days


def _row_moneyness(row: Mapping[str, Any]) -> float | None:
    explicit = _number(row.get("moneyness"))
    if explicit is not None:
        return float(explicit)
    strike = _number(_field_value(row, "strike"))
    underlying_price = _number(_field_value(row, "underlying_price"))
    if strike is None or underlying_price is None or underlying_price <= 0:
        return None
    return float(strike) / float(underlying_price)


def _canonical_expiration(row: Mapping[str, Any]) -> str | None:
    value = _field_value(row, "expiration")
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else (str(value).strip() if _has_value(value) else None)


def _canonical_right(row: Mapping[str, Any]) -> str | None:
    value = _field_value(row, "option_right")
    if not _has_value(value):
        return None
    text = str(value).strip().lower()
    if text in {"c", "call", "calls"}:
        return "call"
    if text in {"p", "put", "puts"}:
        return "put"
    return text


def _missing_required_fields(row: Mapping[str, Any]) -> list[str]:
    return [field for field in CORE_OPTION_ROW_FIELDS if not _has_value(_field_value(row, field))]


def _field_present(rows: Sequence[Mapping[str, Any]], field: str) -> bool:
    return any(_has_value(_field_value(row, field)) for row in rows if isinstance(row, Mapping))


def _field_value(row: Mapping[str, Any], field: str) -> Any:
    for alias in FIELD_ALIASES.get(field, (field,)):
        if alias in row:
            return row.get(alias)
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not _has_value(value):
        return None
    text = str(value).strip()
    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


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
            symbols.update(_extract_symbols(source.get(key)))
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
