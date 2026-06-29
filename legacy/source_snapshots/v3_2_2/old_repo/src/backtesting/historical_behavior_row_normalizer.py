from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
import json
import math
import statistics
from typing import Any


def parse_date(value: Any) -> date | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text[:10]

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def iso(value: date) -> str:
    return value.isoformat()


def normalize_symbol(value: Any) -> str:
    if value is None:
        return ""

    symbol = str(value).strip().upper()

    if symbol in {"", "NONE", "NULL", "NAN"}:
        return ""

    return symbol


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _first_present(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _walk_lists(value: Any) -> list[list[dict[str, Any]]]:
    found: list[list[dict[str, Any]]] = []

    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            found.append(value)
        for item in value:
            found.extend(_walk_lists(item))

    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_walk_lists(item))

    return found


def _looks_like_market_price_row(row: dict[str, Any]) -> bool:
    has_symbol = any(row.get(key) is not None for key in ["symbol", "ticker", "underlying_symbol", "market_symbol"])
    has_date = any(row.get(key) is not None for key in ["date", "quote_date", "timestamp", "time", "end_time"])
    has_price = any(
        row.get(key) is not None
        for key in [
            "close",
            "close_price",
            "adjusted_close",
            "price",
            "last",
            "last_close",
            "underlying_price",
        ]
    )
    return has_symbol and has_date and has_price


def extract_market_price_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in [
            "market_price_rows",
            "price_rows",
            "market_price_snapshots",
            "market_price_history",
            "history",
            "rows",
            "records",
            "items",
            "data",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                rows = [item for item in value if isinstance(item, dict) and _looks_like_market_price_row(item)]
                if rows:
                    return rows

    best_rows: list[dict[str, Any]] = []
    for candidate in _walk_lists(payload):
        rows = [item for item in candidate if _looks_like_market_price_row(item)]
        if len(rows) > len(best_rows):
            best_rows = rows

    return best_rows


def extract_regime_rows_from_date_map(regime_date_map: dict[str, Any]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}

    for item in regime_date_map.get("date_map_items") or []:
        if not isinstance(item, dict):
            continue

        regime_date = parse_date(item.get("regime_date"))
        if regime_date is None:
            continue

        regime_row = item.get("regime_row") if isinstance(item.get("regime_row"), dict) else {}

        state = (
            item.get("regime_state")
            or item.get("policy_regime_label")
            or item.get("macro_regime_label")
            or regime_row.get("regime_label")
            or regime_row.get("risk_environment")
        )

        rows[iso(regime_date)] = {
            "date": iso(regime_date),
            "regime_state": state,
            "macro_regime_label": item.get("macro_regime_label"),
            "policy_regime_label": item.get("policy_regime_label"),
            "risk_environment": item.get("risk_environment") or regime_row.get("risk_environment"),
            "volatility_regime": item.get("volatility_regime") or regime_row.get("volatility_regime"),
            "rates_regime": item.get("rates_regime") or regime_row.get("rates_regime"),
            "liquidity_regime": item.get("liquidity_regime") or regime_row.get("liquidity_regime"),
            "growth_regime": item.get("growth_regime") or regime_row.get("growth_regime"),
            "inflation_regime": item.get("inflation_regime") or regime_row.get("inflation_regime"),
            "source_state": item.get("regime_match_state"),
            "source_quote_date_sample": item.get("quote_date"),
        }

    return [rows[key] for key in sorted(rows)]


def extract_quote_dates_from_date_map(regime_date_map: dict[str, Any], start_date: str, end_date: str) -> list[date]:
    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date)

    if start_dt is None or end_dt is None:
        raise ValueError("start_date and end_date must be YYYY-MM-DD")

    quote_dates: set[date] = set()

    for item in regime_date_map.get("date_map_items") or []:
        if not isinstance(item, dict):
            continue

        quote_dt = parse_date(item.get("quote_date"))
        if quote_dt and start_dt <= quote_dt <= end_dt:
            quote_dates.add(quote_dt)

    return sorted(quote_dates)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None

    return number


def _market_row_to_tuple(row: dict[str, Any]) -> tuple[str, date, float, float | None] | None:
    symbol = normalize_symbol(
        _first_present(row, ["symbol", "ticker", "underlying_symbol", "market_symbol"])
    )
    row_dt = parse_date(_first_present(row, ["date", "quote_date", "timestamp", "time", "end_time"]))
    close = _float_or_none(
        _first_present(
            row,
            [
                "close",
                "close_price",
                "adjusted_close",
                "price",
                "last",
                "last_close",
                "underlying_price",
            ],
        )
    )
    volume = _float_or_none(_first_present(row, ["volume", "trade_volume"]))

    if not symbol or row_dt is None or close is None or close <= 0:
        return None

    return symbol, row_dt, close, volume


def _pct_return(prices: list[float]) -> float | None:
    if len(prices) < 2:
        return None
    if prices[0] == 0:
        return None
    return prices[-1] / prices[0] - 1.0


def _realized_volatility(closes: list[float]) -> float | None:
    if len(closes) < 3:
        return None

    returns: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous > 0:
            returns.append(current / previous - 1.0)

    if len(returns) < 2:
        return None

    return statistics.stdev(returns) * math.sqrt(252)


def classify_asset_behavior(short_return: float | None, long_return: float | None, realized_volatility: float | None) -> str:
    if long_return is None:
        return "sample_limited"

    if long_return > 0.03 and (short_return is None or short_return > -0.02):
        return "constructive"

    if long_return < -0.03 and (short_return is None or short_return < 0.02):
        return "defensive"

    return "neutral"


def build_historical_asset_behavior_rows(
    market_price_rows: list[dict[str, Any]],
    quote_dates: list[date],
    short_window: int = 20,
    long_window: int = 50,
) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[tuple[date, float, float | None]]] = defaultdict(list)

    for row in market_price_rows:
        parsed = _market_row_to_tuple(row)
        if parsed is None:
            continue
        symbol, row_dt, close, volume = parsed
        by_symbol[symbol].append((row_dt, close, volume))

    rows: list[dict[str, Any]] = []

    for symbol, series in sorted(by_symbol.items()):
        deduped: dict[date, tuple[float, float | None]] = {}

        for row_dt, close, volume in series:
            deduped[row_dt] = (close, volume)

        dates = sorted(deduped)
        closes = [deduped[row_dt][0] for row_dt in dates]
        volumes = [deduped[row_dt][1] for row_dt in dates]

        for quote_dt in quote_dates:
            idx = bisect_right(dates, quote_dt) - 1

            if idx < 0:
                continue

            as_of_dt = dates[idx]

            short_start = max(0, idx - short_window)
            long_start = max(0, idx - long_window)

            short_prices = closes[short_start : idx + 1]
            long_prices = closes[long_start : idx + 1]

            short_return = _pct_return(short_prices) if len(short_prices) >= min(short_window + 1, 2) else None
            long_return = _pct_return(long_prices) if len(long_prices) >= long_window + 1 else None
            realized_volatility = _realized_volatility(short_prices)

            state = classify_asset_behavior(short_return, long_return, realized_volatility)

            volume_window = [value for value in volumes[short_start : idx + 1] if value is not None]

            rows.append(
                {
                    "date": iso(quote_dt),
                    "source_price_date": iso(as_of_dt),
                    "symbol": symbol,
                    "asset_behavior_state": state,
                    "behavior_state": state,
                    "short_window_return": short_return,
                    "long_window_return": long_return,
                    "realized_volatility": realized_volatility,
                    "average_volume_short": statistics.mean(volume_window) if volume_window else None,
                    "source_state": "available",
                    "short_window": short_window,
                    "long_window": long_window,
                }
            )

    return rows


def _iv_level(avg_iv: float | None) -> str:
    if avg_iv is None:
        return "iv_unknown"
    if avg_iv < 0.25:
        return "iv_low"
    if avg_iv < 0.45:
        return "iv_moderate"
    return "iv_high"


def _liquidity_state(row_count: int, avg_spread_pct: float | None, avg_volume: float | None, avg_open_interest: float | None) -> str:
    has_activity = (avg_volume is not None and avg_volume > 0) or (avg_open_interest is not None and avg_open_interest > 0)

    if row_count >= 10 and avg_spread_pct is not None and avg_spread_pct <= 0.15 and has_activity:
        return "liquid"

    if row_count >= 3 and avg_spread_pct is not None and avg_spread_pct <= 0.30:
        return "moderate_liquidity"

    return "illiquid_or_sparse"


def build_historical_option_behavior_rows_from_jsonl(
    option_behavior_input_jsonl: str | Path,
    quote_dates: set[date] | None = None,
) -> list[dict[str, Any]]:
    aggregates: dict[tuple[str, date], dict[str, list[float] | int]] = {}

    with Path(option_behavior_input_jsonl).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue

            item = json.loads(line)

            if not isinstance(item, dict):
                continue

            symbol = normalize_symbol(
                _first_present(item, ["underlying_symbol", "symbol", "ticker", "market_symbol"])
            )
            quote_dt = parse_date(_first_present(item, ["quote_date", "date", "timestamp", "time"]))

            if not symbol or quote_dt is None:
                continue

            if quote_dates is not None and quote_dt not in quote_dates:
                continue

            key = (symbol, quote_dt)

            if key not in aggregates:
                aggregates[key] = {
                    "iv": [],
                    "spread_pct": [],
                    "volume": [],
                    "open_interest": [],
                    "row_count": 0,
                }

            bucket = aggregates[key]
            bucket["row_count"] = int(bucket["row_count"]) + 1

            for source_key, bucket_key in [
                ("implied_volatility", "iv"),
                ("spread_pct", "spread_pct"),
                ("volume", "volume"),
                ("open_interest", "open_interest"),
            ]:
                value = _float_or_none(item.get(source_key))
                if value is not None:
                    bucket[bucket_key].append(value)  # type: ignore[union-attr]

    rows: list[dict[str, Any]] = []

    for (symbol, quote_dt), bucket in sorted(aggregates.items(), key=lambda item: (item[0][1], item[0][0])):
        iv_values = bucket["iv"]  # type: ignore[assignment]
        spread_values = bucket["spread_pct"]  # type: ignore[assignment]
        volume_values = bucket["volume"]  # type: ignore[assignment]
        open_interest_values = bucket["open_interest"]  # type: ignore[assignment]

        avg_iv = statistics.mean(iv_values) if iv_values else None
        avg_spread_pct = statistics.mean(spread_values) if spread_values else None
        avg_volume = statistics.mean(volume_values) if volume_values else None
        avg_open_interest = statistics.mean(open_interest_values) if open_interest_values else None

        iv_state = _iv_level(avg_iv)
        liquidity = _liquidity_state(
            int(bucket["row_count"]),
            avg_spread_pct,
            avg_volume,
            avg_open_interest,
        )

        option_behavior_state = f"{iv_state}_{liquidity}"

        rows.append(
            {
                "date": iso(quote_dt),
                "symbol": symbol,
                "option_behavior_state": option_behavior_state,
                "behavior_state": option_behavior_state,
                "iv_level": iv_state,
                "liquidity_state": liquidity,
                "average_implied_volatility": avg_iv,
                "average_spread_pct": avg_spread_pct,
                "average_volume": avg_volume,
                "average_open_interest": avg_open_interest,
                "option_row_count": int(bucket["row_count"]),
                "source_state": "available",
            }
        )

    return rows


def build_historical_behavior_rows(
    regime_date_map: dict[str, Any],
    market_price_input: dict[str, Any],
    start_date: str,
    end_date: str,
    option_behavior_input_jsonl: str | Path | None = None,
    short_window: int = 20,
    long_window: int = 50,
) -> dict[str, Any]:
    regime_rows = extract_regime_rows_from_date_map(regime_date_map)
    quote_dates = extract_quote_dates_from_date_map(regime_date_map, start_date, end_date)

    market_price_rows = extract_market_price_rows(market_price_input)

    asset_behavior_rows = build_historical_asset_behavior_rows(
        market_price_rows=market_price_rows,
        quote_dates=quote_dates,
        short_window=short_window,
        long_window=long_window,
    )

    option_behavior_rows = (
        build_historical_option_behavior_rows_from_jsonl(
            option_behavior_input_jsonl,
            quote_dates=set(quote_dates),
        )
        if option_behavior_input_jsonl
        else []
    )

    blockers: list[str] = []

    if not regime_rows:
        blockers.append("no_regime_rows_extracted")

    if not quote_dates:
        blockers.append("no_quote_dates_extracted")

    if not market_price_rows:
        blockers.append("no_market_price_rows_extracted")

    if not asset_behavior_rows:
        blockers.append("no_asset_behavior_rows_built")

    artifact = {
        "adapter_type": "historical_behavior_row_normalizer",
        "artifact_type": "signalforge_historical_behavior_rows",
        "contract": "historical_behavior_rows",
        "start_date": start_date,
        "end_date": end_date,
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "summary": {
            "quote_date_count": len(quote_dates),
            "regime_row_count": len(regime_rows),
            "market_price_source_row_count": len(market_price_rows),
            "asset_behavior_row_count": len(asset_behavior_rows),
            "option_behavior_row_count": len(option_behavior_rows),
            "asset_symbol_count": len({row["symbol"] for row in asset_behavior_rows}),
            "option_symbol_count": len({row["symbol"] for row in option_behavior_rows}),
        },
        "regime_rows": regime_rows,
        "asset_behavior_rows": asset_behavior_rows,
        "option_behavior_rows": option_behavior_rows,
        "explicit_exclusions": [
            "broker_api_calls",
            "order_routing",
            "order_submission",
            "fills",
            "live_execution",
            "slippage_modeling",
            "automatic_close_orders",
            "automatic_roll_orders",
            "automatic_defense_orders",
            "automatic_strategy_changes",
            "automatic_parameter_changes",
            "automatic_pause_actions",
        ],
    }

    return artifact


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_historical_behavior_rows(artifact: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    regime_path = output_path / "signalforge_historical_regime_rows.jsonl"
    asset_path = output_path / "signalforge_historical_asset_behavior_rows.jsonl"
    option_path = output_path / "signalforge_historical_option_behavior_rows.jsonl"
    summary_path = output_path / "signalforge_historical_behavior_rows_summary.json"

    write_jsonl(artifact["regime_rows"], regime_path)
    write_jsonl(artifact["asset_behavior_rows"], asset_path)
    write_jsonl(artifact["option_behavior_rows"], option_path)

    summary = {
        "adapter_type": artifact["adapter_type"],
        "artifact_type": "signalforge_historical_behavior_rows_summary",
        "contract": artifact["contract"],
        "start_date": artifact["start_date"],
        "end_date": artifact["end_date"],
        "is_ready": artifact["is_ready"],
        "blocker_count": artifact["blocker_count"],
        "blockers": artifact["blockers"],
        "summary": artifact["summary"],
        "files": {
            "regime_rows": str(regime_path),
            "asset_behavior_rows": str(asset_path),
            "option_behavior_rows": str(option_path),
            "summary": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return summary["files"]
