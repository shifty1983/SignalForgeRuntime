from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import polars as pl

from src.signalforge.engines.behavior.behavior_classifier import classify_asset_behavior
from src.signalforge.engines.behavior.benchmark_symbol import (
    infer_asset_class_from_symbol,
    resolve_benchmark_symbol,
)
from src.signalforge.engines.behavior.beta_profile import build_beta_profile
from src.signalforge.engines.behavior.breadth_participation import build_breadth_participation_profile
from src.signalforge.engines.behavior.leadership_profile import build_leadership_profile
from src.signalforge.engines.behavior.relative_strength_profile import build_relative_strength_profile
from src.signalforge.engines.behavior.sector_relative_strength import (
    build_sector_relative_strength_profile,
    infer_sector_benchmark_symbol,
)
from src.signalforge.engines.behavior.volume_behavior import classify_volume_behavior
from src.signalforge.engines.behavior.diagnostics import diagnose_behavior_output
from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_BEHAVIOR_SCHEMA_VERSION = "signalforge_asset_behavior_from_market_price_history.v1"
DEFAULT_SHORT_WINDOW = 20
DEFAULT_LONG_WINDOW = 50

_PRICE_ROW_KEYS = (
    "normalized_payloads",
    "market_price_history",
    "price_rows",
    "rows",
    "payload",
)


def build_signalforge_asset_behavior_from_market_price_history(
    source: Mapping[str, Any] | None,
    *,
    symbols: Sequence[str] | None = None,
    short_window: int = DEFAULT_SHORT_WINDOW,
    long_window: int = DEFAULT_LONG_WINDOW,
    annualization_factor: int = 252,
    benchmark_symbol: str | None = None,
) -> dict[str, Any]:
    """
    Build per-symbol asset behavior from normalized market price history.

    This adapter reads local SignalForge/QuantConnect market-price artifacts only.
    It does not call market-data vendors, brokers, route orders, submit orders,
    model fills, perform live execution, model slippage, create automatic
    close/roll/defense orders, change strategies automatically, update
    parameters automatically, or pause strategies automatically.
    """

    if not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    if isinstance(source.get("import_result"), Mapping):
        source = source["import_result"]

    raw_rows = _extract_rows(source)
    if raw_rows is None:
        return _blocked_result("source does not contain market price rows")

    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        return _blocked_result("market price rows must be a list of mappings")

    if len(raw_rows) == 0:
        return _blocked_result("market price rows are empty")

    requested_symbols = _normalize_symbol_filter(symbols)
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    blocker_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for row_index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            blocker_items.append(
                {
                    "reason": "market price row must be a mapping",
                    "row_index": row_index,
                }
            )
            continue

        normalized = _normalize_price_row(raw_row, row_index)
        row_errors = normalized.pop("_errors")
        if row_errors:
            blocker_items.extend(row_errors)
            continue

        symbol = normalized["symbol"]
        if requested_symbols is not None and symbol not in requested_symbols:
            continue

        rows_by_symbol.setdefault(symbol, []).append(normalized)

    if requested_symbols is not None:
        missing_requested = sorted(set(requested_symbols) - set(rows_by_symbol))
        for symbol in missing_requested:
            warning_items.append(
                {
                    "reason": "requested symbol has no market price rows",
                    "symbol": symbol,
                }
            )

    asset_behaviors: list[dict[str, Any]] = []
    skipped_symbols: list[dict[str, Any]] = []

    for symbol in sorted(rows_by_symbol):
        symbol_rows = sorted(rows_by_symbol[symbol], key=lambda item: str(item["timestamp"]))
        symbol_result = _build_symbol_behavior(
            symbol=symbol,
            rows=symbol_rows,
            rows_by_symbol=rows_by_symbol,
            short_window=short_window,
            long_window=long_window,
            annualization_factor=annualization_factor,
            benchmark_symbol=benchmark_symbol,
        )

        if symbol_result.get("status") == "ready":
            asset_behaviors.append(symbol_result)
        else:
            skipped_symbols.append(symbol_result)
            warning_items.append(
                {
                    "reason": symbol_result.get(
                        "blocked_reason",
                        "symbol behavior could not be classified",
                    ),
                    "symbol": symbol,
                    "row_count": symbol_result.get("source_row_count"),
                }
            )

    source_status = _clean_status(source.get("status"))
    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "source market price import is not ready",
                "source_status": source_status,
            }
        )

    if blocker_items or not asset_behaviors:
        status = "blocked"
    elif warning_items:
        status = "needs_review"
    else:
        status = "ready"

    return {
        "artifact_type": "signalforge_asset_behavior_from_market_price_history",
        "schema_version": ASSET_BEHAVIOR_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_behavior",
        "adapter_type": "market_price_asset_behavior_builder",
        "source_artifact_type": source.get("artifact_type"),
        "source_status": source.get("status"),
        "source_kind": source.get("source_kind"),
        "short_window": short_window,
        "long_window": long_window,
        "annualization_factor": annualization_factor,
        "asset_behaviors": asset_behaviors,
        "skipped_symbols": skipped_symbols,
        "asset_behavior_summary": _asset_behavior_summary(asset_behaviors, skipped_symbols),
        "blocker_items": blocker_items,
        "warning_items": _dedupe_warning_items(warning_items),
        "requested_symbols": sorted(requested_symbols) if requested_symbols is not None else None,
        "observed_symbol_count": len(rows_by_symbol),
        "observed_symbols": sorted(rows_by_symbol),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_rows(source: Mapping[str, Any]) -> Any | None:
    for key in _PRICE_ROW_KEYS:
        if key in source:
            value = source.get(key)
            if isinstance(value, Mapping):
                return [value]
            return value
    return None


def _normalize_price_row(row: Mapping[str, Any], row_index: int) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    symbol = _clean_symbol(row.get("symbol") or row.get("ticker") or row.get("underlying"))
    timestamp = _string_or_none(row.get("timestamp") or row.get("date") or row.get("datetime"))
    price_field, close = _price_from_row(row)

    if symbol is None:
        errors.append({"reason": "missing symbol", "row_index": row_index})

    if timestamp is None:
        errors.append({"reason": "missing timestamp", "row_index": row_index})

    if close is None:
        errors.append({"reason": "missing numeric close or adjusted_close", "row_index": row_index})
    elif close <= 0:
        errors.append({"reason": "close must be positive", "row_index": row_index})

    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "close": close,
        "price_field": price_field,
        "volume": _float_or_none(row.get("volume")),
        "source": row.get("source"),
        "_errors": errors,
    }


def _price_from_row(row: Mapping[str, Any]) -> tuple[str | None, float | None]:
    for field in ("adjusted_close", "close"):
        value = _float_or_none(row.get(field))
        if value is not None:
            return field, value
    return None, None


def _build_symbol_behavior(
    *,
    symbol: str,
    rows: list[dict[str, Any]],
    rows_by_symbol: Mapping[str, list[dict[str, Any]]],
    short_window: int,
    long_window: int,
    annualization_factor: int,
    benchmark_symbol: str | None = None,
) -> dict[str, Any]:
    if len(rows) < long_window:
        return _skipped_symbol(
            symbol=symbol,
            rows=rows,
            reason=f"requires at least {long_window} price rows",
        )

    prices = [float(row["close"]) for row in rows]
    returns = _returns_from_prices(prices)

    if not returns:
        return _skipped_symbol(
            symbol=symbol,
            rows=rows,
            reason="requires at least one return observation",
        )

    equity = [price / prices[0] for price in prices]

    behavior = classify_asset_behavior(
        returns_df=pl.DataFrame({"return": returns}),
        price_df=pl.DataFrame({"close": prices}),
        equity_df=pl.DataFrame({"equity": equity}),
        short_window=short_window,
        long_window=long_window,
        annualization_factor=annualization_factor,
    )

    behavior.update(
        _build_cross_symbol_behavior_profiles(
            symbol=symbol,
            prices=prices,
            returns=returns,
            volumes=[row.get("volume") for row in rows],
            base_behavior=behavior,
            rows_by_symbol=rows_by_symbol,
            short_window=short_window,
            long_window=long_window,
            benchmark_symbol=benchmark_symbol,
        )
    )

    diagnostics = diagnose_behavior_output(behavior)
    status = "ready" if diagnostics.get("passed") else "needs_review"

    return {
        "artifact_type": "asset_behavior_result",
        "status": status,
        "is_ready": status == "ready",
        "symbol": symbol,
        "as_of_date": rows[-1]["timestamp"],
        "start_timestamp": rows[0]["timestamp"],
        "end_timestamp": rows[-1]["timestamp"],
        "source_row_count": len(rows),
        "return_observation_count": len(returns),
        "price_field": rows[-1].get("price_field"),
        "first_close": prices[0],
        "last_close": prices[-1],
        "period_return": round((prices[-1] / prices[0]) - 1.0, 8),
        "short_window": short_window,
        "long_window": long_window,
        **behavior,
        "diagnostics": diagnostics,
        "warnings": list(diagnostics.get("warnings", [])),
        "blocked_reasons": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_cross_symbol_behavior_profiles(
    *,
    symbol: str,
    prices: Sequence[float],
    returns: Sequence[float],
    volumes: Sequence[Any],
    base_behavior: Mapping[str, Any],
    rows_by_symbol: Mapping[str, list[dict[str, Any]]],
    short_window: int,
    long_window: int,
    benchmark_symbol: str | None = None,
) -> dict[str, Any]:
    """Build profiles that need benchmark, sector, breadth, or volume context.

    The core classifier only sees one symbol at a time. These enrichments need
    peer/benchmark series from the full market-price payload, so the builder
    attaches them after the base behavior profile is created.
    """

    asset_class = infer_asset_class_from_symbol(symbol)
    resolved_benchmark_symbol = benchmark_symbol or resolve_benchmark_symbol(
        symbol=symbol,
        asset_class=asset_class,
    )

    benchmark_prices = _prices_for_symbol(rows_by_symbol, resolved_benchmark_symbol)

    output: dict[str, Any] = {
        "asset_class": asset_class,
        "benchmark_symbol": resolved_benchmark_symbol,
    }

    relative_strength = build_relative_strength_profile(
        prices,
        benchmark_prices or prices,
        trend_window=short_window,
    )
    output.update(relative_strength)

    beta = build_beta_profile(
        prices,
        benchmark_prices or prices,
        window=max(long_window, 60),
        min_periods=min(20, max(2, len(prices) - 1)),
    )
    output.update(beta)

    volume = classify_volume_behavior(
        volumes=volumes,
        prices=prices,
        short_window=short_window,
        long_window=long_window,
    )
    output.update(volume)

    sector_benchmark_symbol = infer_sector_benchmark_symbol(symbol, asset_class)
    sector_prices = _prices_for_symbol(rows_by_symbol, sector_benchmark_symbol)
    sector_returns = _returns_from_prices(sector_prices) if sector_prices else []
    sector_relative = build_sector_relative_strength_profile(
        symbol=symbol,
        asset_class=asset_class,
        asset_returns=returns,
        sector_returns=sector_returns,
        sector_benchmark_symbol=sector_benchmark_symbol,
    )
    output.update(sector_relative)

    leadership = build_leadership_profile(
        {
            **base_behavior,
            **output,
        }
    )
    output.update(leadership)

    breadth = build_breadth_participation_profile(
        behavior={
            **base_behavior,
            **output,
        }
    )
    output.update(breadth)

    return output


def _prices_for_symbol(
    rows_by_symbol: Mapping[str, list[dict[str, Any]]],
    symbol: str | None,
) -> list[float]:
    cleaned = _clean_symbol(symbol)
    if not cleaned or cleaned not in rows_by_symbol:
        return []

    rows = sorted(rows_by_symbol[cleaned], key=lambda item: str(item["timestamp"]))
    return [float(row["close"]) for row in rows if row.get("close") is not None]


def _skipped_symbol(*, symbol: str, rows: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "asset_behavior_result",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "as_of_date": rows[-1]["timestamp"] if rows else None,
        "start_timestamp": rows[0]["timestamp"] if rows else None,
        "end_timestamp": rows[-1]["timestamp"] if rows else None,
        "source_row_count": len(rows),
        "blocked_reason": reason,
        "blocked_reasons": [reason],
        "warnings": [],
    }


def _returns_from_prices(prices: Sequence[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        if previous <= 0:
            continue
        returns.append((current / previous) - 1.0)
    return returns


def _asset_behavior_summary(
    asset_behaviors: Sequence[Mapping[str, Any]],
    skipped_symbols: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    states = Counter(_string_or_none(item.get("behavior_state")) for item in asset_behaviors)
    states.pop(None, None)

    trends = Counter(_string_or_none(item.get("trend_behavior")) for item in asset_behaviors)
    trends.pop(None, None)

    return {
        "ready_symbol_count": len(asset_behaviors),
        "skipped_symbol_count": len(skipped_symbols),
        "symbol_count": len(asset_behaviors) + len(skipped_symbols),
        "ready_symbols": [str(item.get("symbol")) for item in asset_behaviors],
        "skipped_symbols": [str(item.get("symbol")) for item in skipped_symbols],
        "behavior_state_counts": dict(sorted(states.items())),
        "trend_behavior_counts": dict(sorted(trends.items())),
    }


def _normalize_symbol_filter(symbols: Sequence[str] | None) -> set[str] | None:
    if symbols is None:
        return None
    normalized = {_clean_symbol(symbol) for symbol in symbols if _clean_symbol(symbol)}
    return normalized


def _clean_symbol(value: Any) -> str | None:
    text = _string_or_none(value)
    return text.upper() if text else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_status(value: Any) -> str | None:
    text = _string_or_none(value)
    return text.lower() if text else None


def _dedupe_warning_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []

    for item in items:
        normalized = {str(key): str(value) for key, value in item.items()}
        key = tuple(sorted(normalized.items()))
        if key not in seen:
            seen.add(key)
            deduped.append(dict(item))

    return deduped


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_asset_behavior_from_market_price_history",
        "schema_version": ASSET_BEHAVIOR_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_behavior",
        "adapter_type": "market_price_asset_behavior_builder",
        "asset_behaviors": [],
        "skipped_symbols": [],
        "asset_behavior_summary": {
            "ready_symbol_count": 0,
            "skipped_symbol_count": 0,
            "symbol_count": 0,
            "ready_symbols": [],
            "skipped_symbols": [],
            "behavior_state_counts": {},
            "trend_behavior_counts": {},
        },
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
