from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


UNIVERSE_SYMBOL_KEYS = (
    "universe_symbols",
    "expected_symbols",
    "requested_symbols",
    "symbols",
)


def extract_market_price_universe_symbols(source: Mapping[str, Any]) -> list[str]:
    symbols: list[str] = []

    for key in UNIVERSE_SYMBOL_KEYS:
        if key in source:
            symbols.extend(_symbols_from_value(source.get(key)))

    universe = source.get("universe")
    if isinstance(universe, Mapping):
        symbols.extend(_symbols_from_value(universe.get("symbols")))

    metadata = source.get("metadata")
    if isinstance(metadata, Mapping):
        for key in UNIVERSE_SYMBOL_KEYS:
            if key in metadata:
                symbols.extend(_symbols_from_value(metadata.get(key)))

    return _normalize_symbols(symbols)


def build_market_price_universe_coverage(
    *,
    source: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_symbols = extract_market_price_universe_symbols(source)
    observed_symbols = _normalize_symbols(
        [
            str(row.get("symbol"))
            for row in normalized_rows
            if isinstance(row, Mapping) and row.get("symbol") is not None
        ]
    )

    expected = set(expected_symbols)
    observed = set(observed_symbols)

    covered_symbols = sorted(expected & observed)
    missing_symbols = sorted(expected - observed)
    extra_symbols = sorted(observed - expected) if expected else []

    coverage_ratio = (
        round(len(covered_symbols) / len(expected_symbols), 6)
        if expected_symbols
        else None
    )

    return {
        "is_enforced": bool(expected_symbols),
        "status": "ready"
        if not expected_symbols or not missing_symbols
        else "needs_review",
        "expected_symbols": expected_symbols,
        "observed_symbols": observed_symbols,
        "covered_symbols": covered_symbols,
        "missing_symbols": missing_symbols,
        "extra_symbols": extra_symbols,
        "expected_symbol_count": len(expected_symbols),
        "observed_symbol_count": len(observed_symbols),
        "covered_symbol_count": len(covered_symbols),
        "missing_symbol_count": len(missing_symbols),
        "extra_symbol_count": len(extra_symbols),
        "coverage_ratio": coverage_ratio,
        "is_complete": not missing_symbols if expected_symbols else None,
    }


def universe_coverage_warning_items(
    coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not coverage.get("is_enforced"):
        return []

    warnings: list[dict[str, Any]] = []

    missing_symbols = _string_list(coverage.get("missing_symbols"))
    if missing_symbols:
        warnings.append(
            {
                "reason": "missing_universe_symbols",
                "missing_symbol_count": len(missing_symbols),
                "missing_symbols": missing_symbols,
            }
        )

    extra_symbols = _string_list(coverage.get("extra_symbols"))
    if extra_symbols:
        warnings.append(
            {
                "reason": "extra_symbols_not_in_universe",
                "extra_symbol_count": len(extra_symbols),
                "extra_symbols": extra_symbols,
            }
        )

    return warnings


def _symbols_from_value(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, Mapping):
        return _symbols_from_value(value.get("symbols"))

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        symbols: list[str] = []
        for item in value:
            symbols.extend(_symbols_from_value(item))
        return symbols

    return []


def _normalize_symbols(symbols: Sequence[str]) -> list[str]:
    return sorted(
        {
            str(symbol).strip().upper()
            for symbol in symbols
            if str(symbol).strip()
        }
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []

    return [str(item) for item in value if str(item)]
