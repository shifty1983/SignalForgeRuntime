from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.signalforge.engines.options.options_behavior_production_input_plan import (
    CORE_OPTION_ROW_FIELDS,
    OPTIONAL_OPTION_ROW_FIELDS,
)


PRODUCTION_READY_OPTION_ROW_SAMPLE_SCHEMA_VERSION = (
    "signalforge_production_ready_option_row_sample.v2"
)

COVERED_CAPABILITIES = [
    "production_ready_option_row_sample",
    "deterministic_option_row_sample_generation",
    "validator_ready_option_row_contract_sample",
    "historical_iv_ready_option_row_sample",
    "path_b_options_input_fixture",
]

DEFAULT_SYMBOLS = ["SPY", "QQQ"]
DEFAULT_QUOTE_DATES = ["2026-06-08", "2026-06-09", "2026-06-10"]
DEFAULT_EXPIRATIONS = ["2026-07-17", "2026-08-21"]
DEFAULT_UNDERLYING_PRICE = 100.0
DEFAULT_STRIKE_MULTIPLIERS = [0.90, 0.95, 1.00, 1.05, 1.10]


def build_signalforge_production_ready_option_row_sample(
    *,
    symbols: list[str] | tuple[str, ...] | None = None,
    quote_date: str | None = None,
    quote_dates: list[str] | tuple[str, ...] | None = None,
    expirations: list[str] | tuple[str, ...] | None = None,
    underlying_price: float = DEFAULT_UNDERLYING_PRICE,
) -> dict[str, Any]:
    """Build deterministic option rows that pass production and IV-history gates.

    The sample is not market data. It is a deterministic fixture for validating
    the Path B option-row import contract and the downstream Options Behavior
    pipeline before a real broker, vendor, or manual source is connected.

    ``quote_date`` remains supported for one-date smoke fixtures. The default is
    now a multi-date fixture so IV rank/percentile and IV expansion/contraction
    can be tested without vendor data.
    """

    normalized_symbols = _normalize_symbols(DEFAULT_SYMBOLS if symbols is None else symbols)
    normalized_quote_dates = _normalize_quote_dates(
        quote_dates=quote_dates,
        quote_date=quote_date,
    )
    normalized_expirations = _normalize_dates(
        DEFAULT_EXPIRATIONS if expirations is None else expirations
    )
    rows = [
        row
        for symbol in normalized_symbols
        for quote_date_index, current_quote_date in enumerate(normalized_quote_dates)
        for row in _rows_for_symbol_date(
            symbol=symbol,
            quote_date=current_quote_date,
            quote_date_index=quote_date_index,
            expirations=normalized_expirations,
            underlying_price=underlying_price,
        )
    ]
    summary = _summary(rows)
    status = "ready" if rows and normalized_symbols and normalized_quote_dates else "blocked"
    blocked_reasons = [] if status == "ready" else _blocked_reasons(
        normalized_symbols=normalized_symbols,
        normalized_quote_dates=normalized_quote_dates,
    )

    rows_per_symbol_per_quote_date = (
        len(normalized_expirations) * 2 * len(DEFAULT_STRIKE_MULTIPLIERS)
    )

    return {
        "artifact_type": "signalforge_production_ready_option_row_sample",
        "schema_version": PRODUCTION_READY_OPTION_ROW_SAMPLE_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "production_ready_option_row_sample",
        "adapter_type": "production_ready_option_row_sample_builder",
        "review_scope": "deterministic_sample_not_vendor_data_contract_selection_or_execution",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": [
            "options_behavior_production_input_plan",
            "production_option_row_import_validator",
            "option_iv_history_snapshot",
            "option_iv_expansion_contraction",
        ],
        "core_option_row_fields": list(CORE_OPTION_ROW_FIELDS),
        "optional_option_row_fields": list(OPTIONAL_OPTION_ROW_FIELDS),
        "sample_policy": {
            "sample_type": "deterministic_fixture",
            "market_data_source": "none",
            "production_decision_use": "validator_and_pipeline_shape_testing_only",
            "row_policy": "filtered_relevant_rows_not_all_raw_chain_rows",
            "history_policy": "multi_quote_date_rows_for_iv_history_pipeline_testing",
            "intended_validator_state": "production_ready_for_sample_symbols",
            "intended_iv_history_state": "ready_for_sample_symbols",
            "intended_iv_expansion_state": "ready_for_sample_symbols",
        },
        "sample_parameters": {
            "symbols": normalized_symbols,
            "quote_dates": normalized_quote_dates,
            "current_quote_date": normalized_quote_dates[-1] if normalized_quote_dates else None,
            "expirations": normalized_expirations,
            "underlying_price": underlying_price,
            "strike_multipliers": list(DEFAULT_STRIKE_MULTIPLIERS),
            "rows_per_symbol_per_quote_date": rows_per_symbol_per_quote_date,
            "rows_per_symbol": rows_per_symbol_per_quote_date * len(normalized_quote_dates),
        },
        "option_rows": rows,
        "production_ready_option_row_sample_summary": summary,
        "next_build_recommendations": [
            {
                "capability": "options_behavior_pipeline_sample_ready_rerun",
                "priority": "high",
                "recommendation": "Use this multi-date option_rows fixture to rerun IV history, IV expansion, gamma, theta, volatility-risk-premium, and Options Behavior integration before connecting real source data.",
            },
            {
                "capability": "full_universe_options_behavior_input",
                "priority": "high",
                "recommendation": "Use the same option_rows contract with real vendor, broker, or manual data for the full universe, then rerun the production validator and Options Behavior pipeline.",
            },
        ],
        "blocked_reasons": blocked_reasons,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _normalize_symbols(symbols: list[str] | tuple[str, ...]) -> list[str]:
    normalized = []
    for symbol in symbols:
        text = str(symbol).strip().upper()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_quote_dates(
    *,
    quote_dates: list[str] | tuple[str, ...] | None,
    quote_date: str | None,
) -> list[str]:
    if quote_dates is not None:
        return _normalize_dates(quote_dates)
    if quote_date:
        return _normalize_dates([quote_date])
    return list(DEFAULT_QUOTE_DATES)


def _normalize_dates(values: list[str] | tuple[str, ...]) -> list[str]:
    normalized = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        parsed = _parse_date(text)
        normalized_text = parsed.isoformat()
        if normalized_text not in normalized:
            normalized.append(normalized_text)
    return normalized


def _blocked_reasons(
    *,
    normalized_symbols: list[str],
    normalized_quote_dates: list[str],
) -> list[str]:
    reasons = []
    if not normalized_symbols:
        reasons.append("no symbols supplied")
    if not normalized_quote_dates:
        reasons.append("no quote dates supplied")
    return reasons or ["no option rows produced"]


def _rows_for_symbol_date(
    *,
    symbol: str,
    quote_date: str,
    quote_date_index: int,
    expirations: list[str],
    underlying_price: float,
) -> list[dict[str, Any]]:
    rows = []
    for expiration_index, expiration in enumerate(expirations):
        dte = _dte(quote_date, expiration)
        for right in ("call", "put"):
            for multiplier_index, multiplier in enumerate(DEFAULT_STRIKE_MULTIPLIERS):
                strike = round(underlying_price * multiplier, 2)
                distance = abs(1.0 - multiplier)
                base_mid = max(
                    1.0,
                    5.0
                    - distance * 25.0
                    + expiration_index * 0.35
                    + quote_date_index * 0.12,
                )
                bid = round(base_mid * 0.96, 2)
                ask = round(base_mid * 1.04, 2)
                delta = _delta(right, multiplier)
                rows.append(
                    {
                        "underlying_symbol": symbol,
                        "quote_date": quote_date,
                        "expiration": expiration,
                        "strike": strike,
                        "option_right": right,
                        "bid": bid,
                        "ask": ask,
                        "implied_volatility": _implied_volatility(
                            quote_date_index=quote_date_index,
                            expiration_index=expiration_index,
                            distance=distance,
                        ),
                        "delta": delta,
                        "gamma": round(max(0.01, 0.045 - distance * 0.12), 4),
                        "theta": round(
                            -(0.025 + expiration_index * 0.005 + distance * 0.04),
                            4,
                        ),
                        "vega": round(
                            0.10 + expiration_index * 0.02 + (0.10 - distance) * 0.08,
                            4,
                        ),
                        "open_interest": 500
                        + expiration_index * 100
                        + multiplier_index * 25
                        + quote_date_index * 10,
                        "volume": 25
                        + expiration_index * 5
                        + multiplier_index * 3
                        + quote_date_index,
                        "underlying_price": underlying_price,
                        "dte": dte,
                        "moneyness": round(strike / underlying_price, 4),
                        "mid_price": round((bid + ask) / 2.0, 2),
                        "option_symbol": _option_symbol(
                            symbol,
                            expiration,
                            right,
                            strike,
                        ),
                        "source_vendor": "signalforge_deterministic_sample",
                    }
                )
    return rows


def _implied_volatility(
    *,
    quote_date_index: int,
    expiration_index: int,
    distance: float,
) -> float:
    # The quote-date offset intentionally creates a non-flat IV history. With
    # defaults, current IV rises by roughly 0.03 from the prior date, allowing
    # IV expansion/contraction logic to classify the sample as ready.
    return round(0.18 + quote_date_index * 0.03 + expiration_index * 0.015 + distance * 0.08, 4)


def _delta(right: str, multiplier: float) -> float:
    call_delta = max(0.15, min(0.85, 0.50 - (multiplier - 1.0) * 3.0))
    if right == "call":
        return round(call_delta, 4)
    return round(-(1.0 - call_delta), 4)


def _dte(quote_date: str, expiration: str) -> int:
    quote = _parse_date(quote_date)
    expiry = _parse_date(expiration)
    return max(0, (expiry - quote).days)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _option_symbol(symbol: str, expiration: str, right: str, strike: float) -> str:
    right_code = "C" if right == "call" else "P"
    compact_date = expiration.replace("-", "")
    strike_text = str(int(round(strike * 1000))).zfill(8)
    return f"{symbol}{compact_date}{right_code}{strike_text}"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    symbol_counts = Counter(row["underlying_symbol"] for row in rows)
    symbol_date_counts = Counter(
        (row["underlying_symbol"], row["quote_date"]) for row in rows
    )
    expiration_counts = Counter(
        (row["underlying_symbol"], row["quote_date"], row["expiration"])
        for row in rows
    )
    right_counts = Counter(row["option_right"] for row in rows)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "symbol_count": len(symbol_counts),
        "quote_date_count": len({row["quote_date"] for row in rows}),
        "option_row_count": len(rows),
        "rows_per_symbol_counts": dict(sorted(symbol_counts.items())),
        "rows_per_symbol_date_counts": {
            f"{symbol}:{quote_date}": count
            for (symbol, quote_date), count in sorted(symbol_date_counts.items())
        },
        "expiration_count_by_symbol": {
            symbol: len(
                {
                    row["expiration"]
                    for row in rows
                    if row["underlying_symbol"] == symbol
                }
            )
            for symbol in sorted(symbol_counts)
        },
        "rows_per_expiration_counts": {
            f"{symbol}:{quote_date}:{expiration}": count
            for (symbol, quote_date, expiration), count in sorted(expiration_counts.items())
        },
        "option_right_counts": dict(sorted(right_counts.items())),
        "required_field_count": len(CORE_OPTION_ROW_FIELDS),
        "optional_field_count": len(OPTIONAL_OPTION_ROW_FIELDS),
        "expected_validator_contract_state": "production_ready_for_sample_symbols",
        "expected_iv_history_state": "ready_for_sample_symbols",
        "expected_iv_expansion_state": "ready_for_sample_symbols",
    }
