from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def to_float(value: Any) -> float | None:
    if value in (None, "", "NaN", "nan"):
        return None
    try:
        value = float(value)
    except Exception:
        return None
    if value != value:
        return None
    return value


def to_int(value: Any) -> int | None:
    if value in (None, "", "NaN", "nan"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def normalize_right(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()

    if text in {"call", "c", "0"}:
        return "call"

    if text in {"put", "p", "1"}:
        return "put"

    return text if text else None


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def classify_contract_liquidity(
    bid: float | None,
    ask: float | None,
    mid: float | None,
    spread_pct: float | None,
    open_interest: int | None,
    volume: int | None,
) -> str:
    quote_complete = bid is not None and ask is not None and mid is not None

    if not quote_complete:
        return "quote_incomplete"

    oi = open_interest or 0
    vol = volume or 0

    if spread_pct is not None and spread_pct <= 0.05 and (oi >= 500 or vol >= 50):
        return "A"

    if spread_pct is not None and spread_pct <= 0.10 and (oi >= 100 or vol >= 10):
        return "B"

    if spread_pct is not None and spread_pct <= 0.20:
        return "C"

    return "D"


def build_feature_row(row: dict[str, Any]) -> dict[str, Any]:
    underlying_symbol = str(first_present(row, ["underlying_symbol", "symbol", "ticker"]) or "").strip().upper()
    quote_date = str(first_present(row, ["quote_date", "date", "as_of_date"]) or "").strip()[:10]

    option_symbol = str(first_present(row, ["option_symbol", "option_contract_symbol", "contract_symbol"]) or "").strip()
    right = normalize_right(first_present(row, ["option_right", "right", "put_call", "call_put"]))

    strike = to_float(first_present(row, ["strike", "strike_price"]))
    expiration = str(first_present(row, ["expiration", "expiration_date", "expiry"]) or "").strip()[:10]
    dte = to_int(first_present(row, ["dte", "days_to_expiration"]))

    underlying_price = to_float(first_present(row, ["underlying_price", "underlying_close", "spot_price"]))
    bid = to_float(first_present(row, ["bid", "bid_price"]))
    ask = to_float(first_present(row, ["ask", "ask_price"]))
    mid_price = to_float(first_present(row, ["mid_price", "mid", "quote_mid"]))

    spread_pct = to_float(first_present(row, ["spread_pct", "relative_spread"]))
    spread = None

    if bid is not None and ask is not None:
        spread = ask - bid

    if spread_pct is None and spread is not None and mid_price not in (None, 0):
        spread_pct = spread / mid_price

    delta = to_float(row.get("delta"))
    gamma = to_float(row.get("gamma"))
    theta = to_float(row.get("theta"))
    vega = to_float(row.get("vega"))
    implied_volatility = to_float(first_present(row, ["implied_volatility", "iv"]))

    open_interest = to_int(first_present(row, ["open_interest", "oi"]))
    volume = to_int(row.get("volume"))

    moneyness = safe_div(strike, underlying_price)
    log_moneyness = None
    if moneyness is not None and moneyness > 0:
        log_moneyness = math.log(moneyness)

    abs_delta = abs(delta) if delta is not None else None

    quote_complete = bid is not None and ask is not None and mid_price is not None
    greeks_complete = (
        delta is not None
        and gamma is not None
        and theta is not None
        and vega is not None
        and implied_volatility is not None
    )

    liquidity_tier = classify_contract_liquidity(
        bid=bid,
        ask=ask,
        mid=mid_price,
        spread_pct=spread_pct,
        open_interest=open_interest,
        volume=volume,
    )

    return {
        "adapter_type": "option_contract_execution_features_v21_builder",
        "artifact_type": "signalforge_option_contract_execution_features_v21",
        "contract": "option_contract_execution_features_v21",
        "underlying_symbol": underlying_symbol,
        "quote_date": quote_date,
        "option_symbol": option_symbol,
        "right": right,
        "strike": strike,
        "expiration": expiration,
        "dte": dte,
        "underlying_price": underlying_price,
        "moneyness": moneyness,
        "log_moneyness": log_moneyness,
        "bid": bid,
        "ask": ask,
        "mid_price": mid_price,
        "spread": spread,
        "spread_pct": spread_pct,
        "delta": delta,
        "abs_delta": abs_delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "implied_volatility": implied_volatility,
        "open_interest": open_interest,
        "volume": volume,
        "quote_complete": quote_complete,
        "greeks_complete": greeks_complete,
        "open_interest_available": open_interest is not None,
        "volume_available": volume is not None,
        "liquidity_tier": liquidity_tier,
        "is_call": right == "call",
        "is_put": right == "put",
    }


def build_contract_features(source_jsonl: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_option_contract_execution_features_v21.jsonl"
    summary_path = output_dir / "signalforge_option_contract_execution_features_v21_summary.json"

    input_row_count = 0
    output_row_count = 0
    bad_row_count = 0

    symbol_dates = set()
    symbols = set()
    option_symbols = set()

    right_counts = Counter()
    liquidity_counts = Counter()

    quote_complete_count = 0
    greeks_complete_count = 0
    oi_available_count = 0
    volume_available_count = 0

    bad_rows_sample = []

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in read_jsonl(source_jsonl):
            input_row_count += 1

            feature = build_feature_row(row)

            required_missing = [
                name
                for name in [
                    "underlying_symbol",
                    "quote_date",
                    "option_symbol",
                    "right",
                    "strike",
                    "expiration",
                    "dte",
                    "underlying_price",
                ]
                if feature.get(name) in (None, "")
            ]

            if required_missing:
                bad_row_count += 1
                if len(bad_rows_sample) < 20:
                    bad_rows_sample.append({
                        "missing": required_missing,
                        "source_row": row,
                    })
                continue

            handle.write(json.dumps(feature, sort_keys=True) + "\n")
            output_row_count += 1

            symbols.add(feature["underlying_symbol"])
            symbol_dates.add((feature["underlying_symbol"], feature["quote_date"]))
            option_symbols.add(feature["option_symbol"])

            right_counts[feature["right"]] += 1
            liquidity_counts[feature["liquidity_tier"]] += 1

            if feature["quote_complete"]:
                quote_complete_count += 1
            if feature["greeks_complete"]:
                greeks_complete_count += 1
            if feature["open_interest_available"]:
                oi_available_count += 1
            if feature["volume_available"]:
                volume_available_count += 1

    blockers = []

    if bad_row_count:
        blockers.append("bad_contract_feature_rows")

    if output_row_count == 0:
        blockers.append("no_contract_feature_rows")

    summary = {
        "adapter_type": "option_contract_execution_features_v21_builder",
        "artifact_type": "signalforge_option_contract_execution_features_v21",
        "contract": "option_contract_execution_features_v21",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "source_jsonl": str(source_jsonl),
        "input_row_count": input_row_count,
        "output_row_count": output_row_count,
        "bad_row_count": bad_row_count,
        "bad_rows_sample": bad_rows_sample,
        "symbol_count": len(symbols),
        "symbol_date_count": len(symbol_dates),
        "option_symbol_count": len(option_symbols),
        "right_counts": dict(sorted(right_counts.items())),
        "liquidity_tier_counts": dict(sorted(liquidity_counts.items())),
        "quote_complete_count": quote_complete_count,
        "quote_complete_rate": quote_complete_count / output_row_count if output_row_count else 0.0,
        "greeks_complete_count": greeks_complete_count,
        "greeks_complete_rate": greeks_complete_count / output_row_count if output_row_count else 0.0,
        "open_interest_available_count": oi_available_count,
        "open_interest_available_rate": oi_available_count / output_row_count if output_row_count else 0.0,
        "volume_available_count": volume_available_count,
        "volume_available_rate": volume_available_count / output_row_count if output_row_count else 0.0,
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = build_contract_features(
        source_jsonl=Path(args.source_jsonl),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
