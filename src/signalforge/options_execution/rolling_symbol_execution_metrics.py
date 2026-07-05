from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_WINDOWS = [20, 60, 252]


SYMBOL_FIELDS = [
    "underlying_symbol",
    "requested_underlying_symbol",
    "option_underlying",
    "underlying",
    "root_symbol",
    "market_symbol",
    "asset_symbol",
    "ticker",
    "symbol",
]

DATE_FIELDS = [
    "quote_date",
    "date",
    "as_of_date",
    "decision_date",
    "trade_date",
]




def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def row_symbol(row: dict[str, Any]) -> str | None:
    value = first_present(row, SYMBOL_FIELDS)
    if value is None:
        return None

    text = str(value).strip().upper()
    return text if text else None


def row_quote_date(row: dict[str, Any]) -> str | None:
    value = first_present(row, DATE_FIELDS)
    if value is None:
        return None

    text = str(value).strip()
    return text[:10] if text else None


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None

    try:
        value = float(value)
    except Exception:
        return None

    if value != value:
        return None

    return value


def to_int(value: Any) -> int:
    if value in (None, ""):
        return 0

    try:
        return int(float(value))
    except Exception:
        return 0


def parse_date(value: Any) -> date:
    text = str(value).strip()[:10]
    return date.fromisoformat(text)


def avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def weighted_avg(pairs: list[tuple[float, float]]) -> float | None:
    numerator = 0.0
    denominator = 0.0

    for value, weight in pairs:
        if weight <= 0:
            continue
        numerator += value * weight
        denominator += weight

    if denominator <= 0:
        return None

    return numerator / denominator


def min_or_none(values: list[float]) -> float | None:
    return min(values) if values else None


def max_or_none(values: list[float]) -> float | None:
    return max(values) if values else None


def classify_rolling_liquidity(
    observation_count: int,
    avg_daily_contract_row_count: float | None,
    median_relative_spread: float | None,
    ab_day_rate: float,
) -> str:
    if observation_count < 5:
        return "sample_limited"

    if (
        avg_daily_contract_row_count is not None
        and median_relative_spread is not None
        and avg_daily_contract_row_count >= 100
        and median_relative_spread <= 0.10
        and ab_day_rate >= 0.60
    ):
        return "A"

    if (
        avg_daily_contract_row_count is not None
        and median_relative_spread is not None
        and avg_daily_contract_row_count >= 50
        and median_relative_spread <= 0.20
        and ab_day_rate >= 0.40
    ):
        return "B"

    if (
        avg_daily_contract_row_count is not None
        and avg_daily_contract_row_count >= 10
    ):
        return "C"

    return "D"


def summarize_window(
    symbol: str,
    asof_quote_date: str,
    window_size: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    observation_count = len(rows)

    row_counts = [to_int(r.get("row_count")) for r in rows]
    total_contract_rows = sum(row_counts)

    relative_spread_weighted_pairs = []
    spread_weighted_pairs = []
    oi_weighted_pairs = []
    volume_weighted_pairs = []

    daily_median_relative_spreads = []
    daily_median_spreads = []
    max_relative_spreads = []
    max_spreads = []
    min_deltas = []
    max_deltas = []
    min_dtes = []
    max_dtes = []

    tier_counts = Counter()

    bid_count = 0
    ask_count = 0
    mid_count = 0
    spread_count = 0
    relative_spread_count = 0
    open_interest_count = 0
    volume_count = 0
    delta_count = 0
    dte_count = 0

    for r in rows:
        tier = str(r.get("liquidity_tier") or "unknown")
        tier_counts[tier] += 1

        bid_count += to_int(r.get("bid_count"))
        ask_count += to_int(r.get("ask_count"))
        mid_count += to_int(r.get("mid_count"))
        spread_count += to_int(r.get("spread_count"))
        relative_spread_count += to_int(r.get("relative_spread_count"))
        open_interest_count += to_int(r.get("open_interest_count"))
        volume_count += to_int(r.get("volume_count"))
        delta_count += to_int(r.get("delta_count"))
        dte_count += to_int(r.get("dte_count"))

        avg_relative_spread = to_float(r.get("avg_relative_spread"))
        median_relative_spread = to_float(r.get("median_relative_spread"))
        max_relative_spread = to_float(r.get("max_relative_spread"))

        avg_spread = to_float(r.get("avg_spread"))
        median_spread = to_float(r.get("median_spread"))
        max_spread = to_float(r.get("max_spread"))

        avg_open_interest = to_float(r.get("avg_open_interest"))
        avg_volume = to_float(r.get("avg_volume"))

        min_delta = to_float(r.get("min_delta"))
        max_delta = to_float(r.get("max_delta"))
        min_dte = to_float(r.get("min_dte"))
        max_dte = to_float(r.get("max_dte"))

        rel_weight = to_int(r.get("relative_spread_count"))
        spread_weight = to_int(r.get("spread_count"))
        oi_weight = to_int(r.get("open_interest_count"))
        volume_weight = to_int(r.get("volume_count"))

        if avg_relative_spread is not None and rel_weight > 0:
            relative_spread_weighted_pairs.append((avg_relative_spread, rel_weight))

        if median_relative_spread is not None:
            daily_median_relative_spreads.append(median_relative_spread)

        if max_relative_spread is not None:
            max_relative_spreads.append(max_relative_spread)

        if avg_spread is not None and spread_weight > 0:
            spread_weighted_pairs.append((avg_spread, spread_weight))

        if median_spread is not None:
            daily_median_spreads.append(median_spread)

        if max_spread is not None:
            max_spreads.append(max_spread)

        if avg_open_interest is not None and oi_weight > 0:
            oi_weighted_pairs.append((avg_open_interest, oi_weight))

        if avg_volume is not None and volume_weight > 0:
            volume_weighted_pairs.append((avg_volume, volume_weight))

        if min_delta is not None:
            min_deltas.append(min_delta)

        if max_delta is not None:
            max_deltas.append(max_delta)

        if min_dte is not None:
            min_dtes.append(min_dte)

        if max_dte is not None:
            max_dtes.append(max_dte)

    avg_daily_contract_row_count = (
        total_contract_rows / observation_count if observation_count else None
    )

    ab_day_count = tier_counts.get("A", 0) + tier_counts.get("B", 0)
    ab_day_rate = ab_day_count / observation_count if observation_count else 0.0

    rolling_median_relative_spread = median(daily_median_relative_spreads)

    rolling_liquidity_tier = classify_rolling_liquidity(
        observation_count=observation_count,
        avg_daily_contract_row_count=avg_daily_contract_row_count,
        median_relative_spread=rolling_median_relative_spread,
        ab_day_rate=ab_day_rate,
    )

    return {
        "adapter_type": "rolling_symbol_execution_metrics_builder",
        "artifact_type": "signalforge_rolling_symbol_execution_metrics",
        "source": "options_execution_symbol_date_metrics",
        "asof_rule": "uses_symbol_date_metrics_with_quote_date_less_than_or_equal_to_asof_quote_date",
        "symbol": symbol,
        "asof_quote_date": asof_quote_date,
        "window_name": f"rolling_{window_size}d",
        "window_size": window_size,
        "window_observation_count": observation_count,
        "window_first_quote_date": rows[0]["quote_date"] if rows else None,
        "window_last_quote_date": rows[-1]["quote_date"] if rows else None,
        "total_contract_row_count": total_contract_rows,
        "avg_daily_contract_row_count": avg_daily_contract_row_count,
        "median_daily_contract_row_count": median([float(x) for x in row_counts]),
        "bid_count": bid_count,
        "ask_count": ask_count,
        "mid_count": mid_count,
        "spread_count": spread_count,
        "relative_spread_count": relative_spread_count,
        "open_interest_count": open_interest_count,
        "volume_count": volume_count,
        "delta_count": delta_count,
        "dte_count": dte_count,
        "weighted_avg_spread": weighted_avg(spread_weighted_pairs),
        "median_daily_median_spread": median(daily_median_spreads),
        "max_daily_max_spread": max_or_none(max_spreads),
        "weighted_avg_relative_spread": weighted_avg(relative_spread_weighted_pairs),
        "median_daily_median_relative_spread": rolling_median_relative_spread,
        "max_daily_max_relative_spread": max_or_none(max_relative_spreads),
        "weighted_avg_open_interest": weighted_avg(oi_weighted_pairs),
        "weighted_avg_volume": weighted_avg(volume_weighted_pairs),
        "min_delta": min_or_none(min_deltas),
        "max_delta": max_or_none(max_deltas),
        "min_dte": min_or_none(min_dtes),
        "max_dte": max_or_none(max_dtes),
        "liquidity_tier_A_day_count": tier_counts.get("A", 0),
        "liquidity_tier_B_day_count": tier_counts.get("B", 0),
        "liquidity_tier_C_day_count": tier_counts.get("C", 0),
        "liquidity_tier_D_day_count": tier_counts.get("D", 0),
        "liquidity_tier_unknown_day_count": tier_counts.get("unknown", 0),
        "ab_liquidity_day_rate": ab_day_rate,
        "rolling_liquidity_tier": rolling_liquidity_tier,
        "sample_state": "ready" if observation_count >= 5 else "sample_limited",
    }


def build_rolling_symbol_execution_metrics(
    symbol_date_metrics_path: Path,
    output_dir: Path,
    windows: list[int] | None = None,
) -> dict[str, Any]:
    windows = windows or DEFAULT_WINDOWS

    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_rolling_symbol_execution_metrics.jsonl"
    summary_path = output_dir / "signalforge_rolling_symbol_execution_metrics_summary.json"

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    input_row_count = 0
    bad_row_count = 0
    duplicate_keys = []
    seen_keys = set()

    for row in read_jsonl(symbol_date_metrics_path):
        input_row_count += 1

        symbol = row_symbol(row)
        quote_date = row_quote_date(row)

        if not symbol or not quote_date:
            bad_row_count += 1
            continue

        try:
            quote_date_obj = parse_date(quote_date)
        except Exception:
            bad_row_count += 1
            continue

        key = (symbol, quote_date)
        if key in seen_keys:
            duplicate_keys.append(key)

        seen_keys.add(key)

        row = dict(row)
        row["symbol"] = symbol
        row["quote_date"] = quote_date
        row["_quote_date_obj"] = quote_date_obj
        grouped[symbol].append(row)

    output_rows = []
    window_output_counts = Counter()

    for symbol, symbol_rows in sorted(grouped.items()):
        symbol_rows = sorted(symbol_rows, key=lambda r: r["_quote_date_obj"])

        for idx, current_row in enumerate(symbol_rows):
            asof_quote_date = current_row["quote_date"]

            for window_size in windows:
                start_idx = max(0, idx - window_size + 1)
                window_rows = symbol_rows[start_idx: idx + 1]

                out = summarize_window(
                    symbol=symbol,
                    asof_quote_date=asof_quote_date,
                    window_size=window_size,
                    rows=window_rows,
                )

                output_rows.append(out)
                window_output_counts[out["window_name"]] += 1

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    blockers = []
    if bad_row_count:
        blockers.append("bad_input_symbol_date_rows")
    if duplicate_keys:
        blockers.append("duplicate_input_symbol_date_keys")
    if not output_rows:
        blockers.append("no_output_rows")

    all_dates = [
        r["quote_date"]
        for rows in grouped.values()
        for r in rows
    ]

    summary = {
        "adapter_type": "rolling_symbol_execution_metrics_builder",
        "artifact_type": "signalforge_rolling_symbol_execution_metrics",
        "contract": "rolling_symbol_execution_metrics",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "source_symbol_date_metrics_path": str(symbol_date_metrics_path),
        "input_row_count": input_row_count,
        "bad_row_count": bad_row_count,
        "duplicate_key_count": len(duplicate_keys),
        "duplicate_keys_sample": [
            {"symbol": k[0], "quote_date": k[1]}
            for k in duplicate_keys[:50]
        ],
        "symbol_count": len(grouped),
        "min_quote_date": min(all_dates) if all_dates else None,
        "max_quote_date": max(all_dates) if all_dates else None,
        "windows": windows,
        "window_count": len(windows),
        "output_row_count": len(output_rows),
        "expected_output_row_count": input_row_count * len(windows),
        "window_output_counts": dict(sorted(window_output_counts.items())),
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return summary
