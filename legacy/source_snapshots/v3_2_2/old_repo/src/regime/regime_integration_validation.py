from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import polars as pl

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.regime.breadth import breadth_trend, classify_breadth, moving_average_breadth
from src.regime.composite_macro import build_composite_macro_regime
from src.regime.risk_environment import (
    add_enhanced_risk_score,
    add_enhanced_risk_trend,
    add_risk_confidence,
    classify_enhanced_risk_environment,
)

REGIME_INTEGRATION_VALIDATION_SCHEMA_VERSION = "signalforge_regime_integration_validation.v1"

PRICE_ROW_KEYS = (
    "normalized_payloads",
    "payloads",
    "accepted_payloads",
    "accepted_rows",
    "valid_rows",
    "market_price_history",
    "price_rows",
    "rows",
    "data",
    "items",
    "records",
)

DEFAULT_BREADTH_SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "RSP",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLI",
    "XLY",
    "XLP",
    "XLU",
    "XLB",
    "XLRE",
    "XLC",
)

DEFAULT_RISK_PAIRS = (
    ("SPY", "TLT"),
    ("QQQ", "XLU"),
    ("HYG", "LQD"),
    ("IWM", "SPY"),
)

DEFAULT_VOLATILITY_PROXIES = ("VIXY", "VXX", "UVXY")


def build_signalforge_regime_integration_validation(
    *,
    fred_regime_pipeline: Mapping[str, Any] | None = None,
    market_price_history: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    as_of_date: str | date | datetime | None = None,
    breadth_window: int = 200,
    breadth_trend_periods: int = 20,
    risk_lookback_periods: int = 60,
    min_breadth_symbols: int = 8,
) -> dict[str, Any]:
    """Validate the integrated Regime path with FRED and market-price inputs.

    The artifact proves whether the new market-side Regime components are wired
    into an integrated output path before Asset Behavior consumes them. It does
    not call broker APIs, submit orders, model fills, or make automatic changes.
    """

    warnings: list[str] = []
    blocked_reasons: list[str] = []

    market_result = build_market_price_regime_validation(
        market_price_history=market_price_history,
        as_of_date=as_of_date,
        breadth_window=breadth_window,
        breadth_trend_periods=breadth_trend_periods,
        risk_lookback_periods=risk_lookback_periods,
        min_breadth_symbols=min_breadth_symbols,
    )

    if market_result["status"] == "blocked":
        blocked_reasons.extend(market_result["blocked_reasons"])
    else:
        warnings.extend(market_result["warnings"])

    fred_context = _latest_fred_context(fred_regime_pipeline)
    if fred_regime_pipeline is None:
        warnings.append("fred_regime_pipeline was not supplied; composite macro validation skipped")
    elif fred_context is None:
        warnings.append("no latest FRED ready regime row available; composite macro validation skipped")

    integrated_row = None
    composite_status = "not_run"
    composite_rows: list[dict[str, Any]] = []

    market_row = market_result.get("latest_ready_market_regime_row")
    if isinstance(market_row, Mapping) and isinstance(fred_context, Mapping):
        integrated_row = _build_integrated_row(fred_context, market_row)
        try:
            composite_df = build_composite_macro_regime(
                pl.DataFrame([integrated_row], infer_schema_length=None)
            )
            composite_rows = composite_df.to_dicts()
            integrated_row = composite_rows[0] if composite_rows else integrated_row
            composite_status = "ready"
        except ValueError as error:
            composite_status = "blocked"
            blocked_reasons.append(str(error))

    if blocked_reasons:
        status = "blocked"
    elif composite_status == "ready" and not warnings:
        status = "ready"
    else:
        status = "needs_review"

    return {
        "artifact_type": "signalforge_regime_integration_validation",
        "schema_version": REGIME_INTEGRATION_VALIDATION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "market_price_regime_validation": market_result,
        "fred_context_summary": _fred_context_summary(fred_regime_pipeline, fred_context),
        "composite_status": composite_status,
        "latest_integrated_regime_row": integrated_row,
        "composite_rows": composite_rows,
        "warnings": _dedupe(warnings),
        "blocked_reasons": _dedupe(blocked_reasons),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def build_market_price_regime_validation(
    *,
    market_price_history: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    as_of_date: str | date | datetime | None = None,
    breadth_window: int = 200,
    breadth_trend_periods: int = 20,
    risk_lookback_periods: int = 60,
    min_breadth_symbols: int = 8,
) -> dict[str, Any]:
    """Build breadth and enhanced-risk classifications from market price history."""

    input_errors = _market_input_errors(
        market_price_history=market_price_history,
        breadth_window=breadth_window,
        breadth_trend_periods=breadth_trend_periods,
        risk_lookback_periods=risk_lookback_periods,
        min_breadth_symbols=min_breadth_symbols,
    )
    if input_errors:
        return _blocked_market_result(input_errors)

    rows = _extract_price_rows(market_price_history)
    if not rows:
        return _blocked_market_result(["no usable market price history rows"])

    price_df = _price_frame(rows)
    if price_df.is_empty() or "date" not in price_df.columns:
        return _blocked_market_result(["market price history could not be normalized to a price frame"])

    price_df = _filter_as_of_date(price_df, as_of_date)
    if price_df.is_empty():
        return _blocked_market_result(["no market price rows on or before as_of_date"])

    breadth_symbols = _available_columns(price_df, DEFAULT_BREADTH_SYMBOLS)
    if len(breadth_symbols) < min_breadth_symbols:
        return _blocked_market_result(
            [
                f"only {len(breadth_symbols)} breadth symbols available; "
                f"minimum required is {min_breadth_symbols}"
            ],
            source_symbols=_source_symbols(price_df),
        )

    result = moving_average_breadth(
        price_df,
        breadth_symbols,
        window=breadth_window,
        output_column="breadth_score",
    )
    result = breadth_trend(
        result,
        column="breadth_score",
        periods=breadth_trend_periods,
        output_column="breadth_trend",
    )
    result = classify_breadth(result)

    return_columns = _add_return_columns(result, risk_lookback_periods)
    result = return_columns["df"]
    risk_pairs = return_columns["risk_pairs"]
    vix_trend_column = return_columns["vix_trend_column"]

    if not risk_pairs and vix_trend_column is None:
        return _blocked_market_result(
            ["no enhanced risk market proxy pairs or volatility proxy could be calculated"],
            source_symbols=_source_symbols(price_df),
        )

    result = add_enhanced_risk_score(
        result,
        risk_pairs=risk_pairs,
        vix_trend_column=vix_trend_column,
        breadth_score_column="breadth_score",
        breadth_trend_column="breadth_trend",
        output_column="risk_score",
    )
    result = add_enhanced_risk_trend(result)
    result = add_risk_confidence(result)
    result = classify_enhanced_risk_environment(result)

    output_rows = result.to_dicts()
    latest_ready = _latest_market_ready_row(output_rows)
    warnings: list[str] = []
    if latest_ready is None:
        warnings.append("no complete market regime row is available after lookbacks")

    status = "ready" if latest_ready is not None and not warnings else "needs_review"
    latest_date = output_rows[-1].get("date") if output_rows else None

    return {
        "artifact_type": "signalforge_market_price_regime_validation",
        "schema_version": "signalforge_market_price_regime_validation.v1",
        "status": status,
        "is_ready": status == "ready",
        "as_of_date": str(latest_date) if latest_date is not None else None,
        "source_symbol_count": len(_source_symbols(price_df)),
        "source_symbols": _source_symbols(price_df),
        "breadth_symbols": breadth_symbols,
        "risk_pair_count": len(risk_pairs),
        "vix_trend_column": vix_trend_column,
        "breadth_window": breadth_window,
        "breadth_trend_periods": breadth_trend_periods,
        "risk_lookback_periods": risk_lookback_periods,
        "market_regime_row_count": len(output_rows),
        "latest_ready_market_regime_row": latest_ready,
        "warnings": _dedupe(warnings),
        "blocked_reasons": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_integrated_row(
    fred_context: Mapping[str, Any],
    market_row: Mapping[str, Any],
) -> dict[str, Any]:
    row = dict(fred_context)
    row["fred_risk_environment"] = fred_context.get("risk_environment")
    row["market_date"] = str(market_row.get("date")) if market_row.get("date") is not None else None
    row["breadth_score"] = market_row.get("breadth_score")
    row["breadth_trend"] = market_row.get("breadth_trend")
    row["breadth_regime"] = market_row.get("breadth_regime")
    row["market_risk_score"] = market_row.get("risk_score")
    row["market_risk_trend"] = market_row.get("risk_trend")
    row["market_risk_confidence"] = market_row.get("risk_confidence")
    row["market_risk_environment"] = market_row.get("risk_environment")
    row["risk_environment"] = market_row.get("risk_environment")
    return row


def _latest_fred_context(fred_regime_pipeline: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(fred_regime_pipeline, Mapping):
        return None

    latest = fred_regime_pipeline.get("latest_ready_regime_row")
    if isinstance(latest, Mapping):
        return latest

    if _looks_like_fred_row(fred_regime_pipeline):
        return fred_regime_pipeline

    rows = fred_regime_pipeline.get("regime_rows")
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)):
        for row in reversed(rows):
            if isinstance(row, Mapping) and _looks_like_fred_row(row):
                return row

    return None


def _looks_like_fred_row(row: Mapping[str, Any]) -> bool:
    required = [
        "growth_regime",
        "inflation_regime",
        "rates_regime",
        "liquidity_regime",
        "credit_regime",
        "credit_stress_level",
        "yield_curve_regime",
    ]
    return all(key in row for key in required)


def _fred_context_summary(
    fred_regime_pipeline: Mapping[str, Any] | None,
    fred_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(fred_regime_pipeline, Mapping):
        return {"status": "not_supplied", "latest_ready_regime_row_available": False}

    return {
        "artifact_type": fred_regime_pipeline.get("artifact_type"),
        "status": fred_regime_pipeline.get("status"),
        "latest_date": fred_regime_pipeline.get("latest_date") or (fred_context or {}).get("date"),
        "latest_ready_regime_row_available": fred_context is not None,
    }


def _market_input_errors(
    *,
    market_price_history: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    breadth_window: int,
    breadth_trend_periods: int,
    risk_lookback_periods: int,
    min_breadth_symbols: int,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(market_price_history, Mapping) and not _is_sequence(market_price_history):
        errors.append("market_price_history must be a mapping or sequence of mappings")
    if breadth_window <= 0:
        errors.append("breadth_window must be positive")
    if breadth_trend_periods <= 0:
        errors.append("breadth_trend_periods must be positive")
    if risk_lookback_periods <= 0:
        errors.append("risk_lookback_periods must be positive")
    if min_breadth_symbols <= 0:
        errors.append("min_breadth_symbols must be positive")
    return errors


def _extract_price_rows(source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    if source is None:
        return []
    if _is_sequence(source):
        rows: list[Mapping[str, Any]] = []
        for item in source:  # type: ignore[union-attr]
            rows.extend(_extract_price_rows(item))
        return rows
    if not isinstance(source, Mapping):
        return []

    if _row_from_mapping(source) is not None:
        return [source]

    rows: list[Mapping[str, Any]] = []
    for key in PRICE_ROW_KEYS:
        value = source.get(key)
        if value is not None:
            rows.extend(_extract_price_rows(value))

    payload = source.get("payload") or source.get("normalized_payload") or source.get("record")
    if isinstance(payload, Mapping):
        rows.extend(_extract_price_rows(payload))

    return rows


def _row_from_mapping(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if _symbol_from_row(row) and _date_from_row(row) is not None and _close_from_row(row) is not None:
        return row
    return None


def _price_frame(rows: Sequence[Mapping[str, Any]]) -> pl.DataFrame:
    normalized = []
    for row in rows:
        symbol = _symbol_from_row(row)
        row_date = _date_from_row(row)
        close = _close_from_row(row)
        if symbol and row_date is not None and close is not None:
            normalized.append({"date": row_date, "symbol": symbol, "close": close})

    if not normalized:
        return pl.DataFrame()

    return (
        pl.DataFrame(normalized, infer_schema_length=None)
        .group_by(["date", "symbol"])
        .agg(pl.col("close").last())
        .pivot(values="close", index="date", on="symbol", aggregate_function="last")
        .sort("date")
    )


def _filter_as_of_date(df: pl.DataFrame, as_of_date: str | date | datetime | None) -> pl.DataFrame:
    parsed = _parse_date(as_of_date)
    if parsed is None:
        return df
    return df.filter(pl.col("date") <= parsed)


def _add_return_columns(df: pl.DataFrame, periods: int) -> dict[str, Any]:
    required_symbols = set(DEFAULT_VOLATILITY_PROXIES)
    for risk_symbol, defensive_symbol in DEFAULT_RISK_PAIRS:
        required_symbols.add(risk_symbol)
        required_symbols.add(defensive_symbol)

    available_symbols = _available_columns(df, sorted(required_symbols))
    return_alias = {symbol: f"{symbol}_return_{periods}" for symbol in available_symbols}
    result = df.with_columns(
        [pl.col(symbol).pct_change(periods).alias(alias) for symbol, alias in return_alias.items()]
    )

    risk_pairs = []
    for risk_symbol, defensive_symbol in DEFAULT_RISK_PAIRS:
        risk_alias = return_alias.get(risk_symbol)
        defensive_alias = return_alias.get(defensive_symbol)
        if risk_alias and defensive_alias:
            signal_name = f"{risk_symbol}_vs_{defensive_symbol}_risk_signal"
            risk_pairs.append((risk_alias, defensive_alias, signal_name))

    vix_trend_column = None
    for symbol in DEFAULT_VOLATILITY_PROXIES:
        alias = return_alias.get(symbol)
        if alias:
            vix_trend_column = alias
            break

    return {"df": result, "risk_pairs": risk_pairs, "vix_trend_column": vix_trend_column}


def _latest_market_ready_row(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    required = ["breadth_score", "breadth_trend", "breadth_regime", "risk_score", "risk_environment"]
    for row in reversed(rows):
        if all(row.get(key) is not None for key in required):
            return dict(row)
    return None


def _available_columns(df: pl.DataFrame, columns: Sequence[str]) -> list[str]:
    return [column for column in columns if column in df.columns]


def _source_symbols(df: pl.DataFrame) -> list[str]:
    return sorted(column for column in df.columns if column != "date")


def _symbol_from_row(row: Mapping[str, Any]) -> str | None:
    symbol = row.get("symbol") or row.get("ticker")
    if symbol is None:
        return None
    value = str(symbol).strip().upper()
    return value or None


def _date_from_row(row: Mapping[str, Any]) -> date | None:
    value = row.get("timestamp") or row.get("date") or row.get("time")
    return _parse_date(value)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _close_from_row(row: Mapping[str, Any]) -> float | None:
    for key in ("adjusted_close", "close", "adj_close", "last"):
        value = row.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _blocked_market_result(
    blocked_reasons: Sequence[str],
    *,
    source_symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_market_price_regime_validation",
        "schema_version": "signalforge_market_price_regime_validation.v1",
        "status": "blocked",
        "is_ready": False,
        "source_symbol_count": len(source_symbols or []),
        "source_symbols": list(source_symbols or []),
        "market_regime_row_count": 0,
        "latest_ready_market_regime_row": None,
        "warnings": [],
        "blocked_reasons": _dedupe(blocked_reasons),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _dedupe(values: Sequence[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
