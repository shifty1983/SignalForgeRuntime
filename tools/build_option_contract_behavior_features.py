from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


KEY_ALIASES = {
    "underlying_symbol": ["underlying_symbol", "symbol", "asset_symbol", "ticker"],
    "quote_date": ["quote_date", "asof_date", "date", "decision_date"],
    "expiration": ["expiration", "requested_expiration"],
    "strike": ["strike", "requested_strike"],
    "option_right": ["option_right", "requested_option_right", "right"],
}

FIELD_ALIASES = {
    "bid": ["bid"],
    "ask": ["ask"],
    "mid": ["mid", "mid_price"],
    "spread": ["spread"],
    "spread_pct": ["spread_pct"],
    "implied_volatility": ["implied_volatility", "iv"],
    "delta": ["delta"],
    "gamma": ["gamma"],
    "theta": ["theta"],
    "vega": ["vega"],
    "volume": ["volume"],
    "open_interest": ["open_interest", "oi"],
    "dte": ["dte"],
    "underlying_price": [
        "underlying_price",
        "underlying_close",
        "underlying_last",
        "spot_price",
        "close",
    ],
}

CANONICAL_CARRY_FIELDS = [
    "bid",
    "ask",
    "mid",
    "spread",
    "spread_pct",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "volume",
    "open_interest",
    "dte",
    "quote_resolution_state",
    "quote_role_observed",
    "quote_outcome_id",
    "requested_expiration",
    "requested_option_right",
    "requested_strike",
]

SF_VALUE_FIELDS = [
    "bid",
    "ask",
    "mid",
    "spread",
    "spread_pct",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "volume",
    "open_interest",
    "dte",
    "underlying_price",
]

CANONICAL_METRIC_FIELDS = [
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "volume",
    "open_interest",
    "spread_pct",
]


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}

    if isinstance(obj, dict):
        for key, value in obj.items():
            next_key = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                out.update(flatten(value, next_key))
            else:
                out[next_key] = value
    else:
        out[prefix or "value"] = obj

    return out


def is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def to_float(value: Any) -> float | None:
    if is_blank(value):
        return None

    try:
        result = float(value)
    except Exception:
        return None

    if math.isnan(result) or math.isinf(result):
        return None

    return result


def norm_symbol(value: Any) -> str | None:
    if is_blank(value):
        return None
    return str(value).strip().upper().replace("$", "")


def norm_date(value: Any) -> str | None:
    if is_blank(value):
        return None

    text = str(value).strip()

    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group(0)

    match = re.search(r"\d{8}", text)
    if match:
        raw = match.group(0)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    return text[:10]


def norm_right(value: Any) -> str | None:
    if is_blank(value):
        return None

    text = str(value).strip().upper()

    if text in {"P", "PUT"}:
        return "PUT"
    if text in {"C", "CALL"}:
        return "CALL"

    return text


def norm_strike(value: Any) -> str | None:
    if is_blank(value):
        return None

    try:
        return f"{float(value):.6f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value).strip()


def get_first(row: dict[str, Any] | None, names: list[str]) -> Any:
    if row is None:
        return None

    for name in names:
        if name in row and not is_blank(row[name]):
            return row[name]

    return None


def make_key(row: dict[str, Any]) -> tuple[str, str, str, str, str] | None:
    symbol = norm_symbol(get_first(row, KEY_ALIASES["underlying_symbol"]))
    quote_date = norm_date(get_first(row, KEY_ALIASES["quote_date"]))
    expiration = norm_date(get_first(row, KEY_ALIASES["expiration"]))
    strike = norm_strike(get_first(row, KEY_ALIASES["strike"]))
    right = norm_right(get_first(row, KEY_ALIASES["option_right"]))

    if not symbol or not quote_date or not expiration or not strike or not right:
        return None

    return symbol, quote_date, expiration, strike, right


def key_to_string(key: tuple[str, str, str, str, str] | None) -> str | None:
    if key is None:
        return None
    return "|".join(key)


def canonical_quality_score(row: dict[str, Any]) -> int:
    score = 0

    for field in ["bid", "ask", "mid", "spread"]:
        if not is_blank(row.get(field)):
            score += 100

    for field in CANONICAL_METRIC_FIELDS:
        if not is_blank(row.get(field)):
            score += 10

    if not is_blank(row.get("quote_resolution_state")):
        score += 5
    if not is_blank(row.get("quote_role_observed")):
        score += 5
    if not is_blank(row.get("quote_outcome_id")):
        score += 5

    return score


def load_canonical(path: Path) -> tuple[dict[tuple[str, str, str, str, str], dict[str, Any]], dict[str, Any]]:
    canonical: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}

    row_count = 0
    bad_line_count = 0
    missing_key_count = 0
    duplicate_key_count = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            try:
                row = flatten(json.loads(line))
            except Exception:
                bad_line_count += 1
                continue

            row_count += 1
            key = make_key(row)

            if key is None:
                missing_key_count += 1
                continue

            existing = canonical.get(key)

            if existing is not None:
                duplicate_key_count += 1
                if canonical_quality_score(row) <= canonical_quality_score(existing):
                    continue

            canonical[key] = row

    return canonical, {
        "row_count": row_count,
        "bad_line_count": bad_line_count,
        "missing_key_count": missing_key_count,
        "key_count": len(canonical),
        "duplicate_key_count": duplicate_key_count,
    }


def choose_observed_value(
    field: str,
    behavior_row: dict[str, Any],
    canonical_row: dict[str, Any] | None,
) -> tuple[Any, str]:
    aliases = FIELD_ALIASES.get(field, [field])

    canonical_value = get_first(canonical_row, aliases)
    if not is_blank(canonical_value):
        return canonical_value, "canonical_observed"

    behavior_value = get_first(behavior_row, aliases)
    if not is_blank(behavior_value):
        return behavior_value, "behavior_existing"

    return None, "missing"


def derive_quote_values(
    behavior_row: dict[str, Any],
    canonical_row: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}

    for field in [
        "bid",
        "ask",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
        "volume",
        "open_interest",
        "dte",
        "underlying_price",
    ]:
        values[field], sources[field] = choose_observed_value(field, behavior_row, canonical_row)

    mid_value, mid_source = choose_observed_value("mid", behavior_row, canonical_row)

    if is_blank(mid_value):
        bid = to_float(values.get("bid"))
        ask = to_float(values.get("ask"))
        if bid is not None and ask is not None:
            mid_value = (bid + ask) / 2.0
            mid_source = "derived_from_selected_bid_ask"

    values["mid"] = mid_value
    sources["mid"] = mid_source

    spread_value, spread_source = choose_observed_value("spread", behavior_row, canonical_row)

    if is_blank(spread_value):
        bid = to_float(values.get("bid"))
        ask = to_float(values.get("ask"))
        if bid is not None and ask is not None:
            spread_value = ask - bid
            spread_source = "derived_from_selected_bid_ask"

    values["spread"] = spread_value
    sources["spread"] = spread_source

    spread_pct_value, spread_pct_source = choose_observed_value(
        "spread_pct",
        behavior_row,
        canonical_row,
    )

    if is_blank(spread_pct_value):
        spread = to_float(values.get("spread"))
        mid = to_float(values.get("mid"))
        if spread is not None and mid is not None and mid > 0:
            spread_pct_value = spread / mid
            spread_pct_source = "derived_from_selected_spread_mid"

    values["spread_pct"] = spread_pct_value
    sources["spread_pct"] = spread_pct_source

    return values, sources


def canonical_price_full(canonical_row: dict[str, Any] | None) -> bool:
    if canonical_row is None:
        return False

    return (
        not is_blank(canonical_row.get("bid"))
        and not is_blank(canonical_row.get("ask"))
        and not is_blank(canonical_row.get("mid"))
        and not is_blank(canonical_row.get("spread"))
    )


def canonical_metrics_full(canonical_row: dict[str, Any] | None) -> bool:
    if canonical_row is None:
        return False

    return all(not is_blank(canonical_row.get(field)) for field in CANONICAL_METRIC_FIELDS)


def overlay_state_for(
    key: tuple[str, str, str, str, str] | None,
    canonical_row: dict[str, Any] | None,
) -> str:
    if key is None:
        return "behavior_missing_contract_key"

    if canonical_row is None:
        return "behavior_only_no_canonical_quote"

    if canonical_price_full(canonical_row) and canonical_metrics_full(canonical_row):
        return "canonical_quote_matched_price_full_metrics_full"

    if canonical_price_full(canonical_row):
        return "canonical_quote_matched_price_full_metrics_partial"

    return "canonical_quote_matched_price_partial"


def bucket_dte(value: Any) -> str:
    dte = to_float(value)
    if dte is None:
        return "missing"
    if dte <= 7:
        return "000_007"
    if dte <= 14:
        return "008_014"
    if dte <= 30:
        return "015_030"
    if dte <= 45:
        return "031_045"
    if dte <= 60:
        return "046_060"
    if dte <= 90:
        return "061_090"
    if dte <= 180:
        return "091_180"
    return "181_plus"


def bucket_abs_delta(value: Any) -> str:
    delta = to_float(value)
    if delta is None:
        return "missing"

    delta = abs(delta)

    if delta <= 0.10:
        return "000_010"
    if delta <= 0.20:
        return "010_020"
    if delta <= 0.30:
        return "020_030"
    if delta <= 0.40:
        return "030_040"
    if delta <= 0.60:
        return "040_060"
    if delta <= 0.80:
        return "060_080"
    return "080_100"


def bucket_spread_pct(value: Any) -> str:
    spread_pct = to_float(value)
    if spread_pct is None:
        return "missing"
    if spread_pct <= 0.02:
        return "000_002"
    if spread_pct <= 0.05:
        return "002_005"
    if spread_pct <= 0.10:
        return "005_010"
    if spread_pct <= 0.25:
        return "010_025"
    if spread_pct <= 0.50:
        return "025_050"
    return "050_plus"


def bucket_count_like(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "missing"
    if number <= 0:
        return "000"
    if number < 10:
        return "001_009"
    if number < 50:
        return "010_049"
    if number < 200:
        return "050_199"
    if number < 1000:
        return "200_999"
    return "1000_plus"


def bucket_iv(value: Any) -> str:
    iv = to_float(value)
    if iv is None:
        return "missing"

    if iv <= 0.20:
        return "000_020"
    if iv <= 0.40:
        return "020_040"
    if iv <= 0.60:
        return "040_060"
    if iv <= 1.00:
        return "060_100"
    return "100_plus"


def compute_moneyness(
    strike_value: Any,
    underlying_price_value: Any,
) -> tuple[float | None, float | None, str]:
    strike = to_float(strike_value)
    underlying = to_float(underlying_price_value)

    if strike is None or underlying is None or strike <= 0 or underlying <= 0:
        return None, None, "missing"

    strike_to_underlying = strike / underlying
    log_moneyness = math.log(underlying / strike)

    if strike_to_underlying <= 0.80:
        bucket = "deep_itm_call_deep_otm_put"
    elif strike_to_underlying <= 0.95:
        bucket = "itm_call_otm_put"
    elif strike_to_underlying <= 1.05:
        bucket = "near_atm"
    elif strike_to_underlying <= 1.20:
        bucket = "otm_call_itm_put"
    else:
        bucket = "deep_otm_call_deep_itm_put"

    return strike_to_underlying, log_moneyness, bucket


def execution_flags_and_reasons(
    values: dict[str, Any],
    key: tuple[str, str, str, str, str] | None,
    canonical_row: dict[str, Any] | None,
    max_spread_pct: float,
    min_open_interest: float,
    min_volume: float,
    require_canonical: bool,
) -> tuple[dict[str, Any], list[str]]:
    bid = to_float(values.get("bid"))
    ask = to_float(values.get("ask"))
    mid = to_float(values.get("mid"))
    spread = to_float(values.get("spread"))
    spread_pct = to_float(values.get("spread_pct"))
    open_interest = to_float(values.get("open_interest"))
    volume = to_float(values.get("volume"))

    flags = {
        "sf_bid_present": bid is not None,
        "sf_ask_present": ask is not None,
        "sf_mid_present": mid is not None,
        "sf_spread_present": spread is not None,
        "sf_spread_pct_present": spread_pct is not None,
        "sf_bid_ask_crossed": bid is not None and ask is not None and ask < bid,
        "sf_bid_ask_locked": bid is not None and ask is not None and ask == bid,
        "sf_zero_bid": bid is not None and bid <= 0,
        "sf_nonpositive_mid": mid is not None and mid <= 0,
        "sf_wide_spread_flag": spread_pct is not None and spread_pct > max_spread_pct,
        "sf_low_open_interest_flag": (
            open_interest is None or open_interest < min_open_interest
        )
        if min_open_interest > 0
        else False,
        "sf_low_volume_flag": (
            volume is None or volume < min_volume
        )
        if min_volume > 0
        else False,
        "sf_no_canonical_quote_flag": canonical_row is None,
    }

    reasons: list[str] = []

    if key is None:
        reasons.append("missing_contract_key")

    if require_canonical and canonical_row is None:
        reasons.append("missing_canonical_quote")

    if bid is None:
        reasons.append("missing_bid")
    if ask is None:
        reasons.append("missing_ask")
    if mid is None:
        reasons.append("missing_mid")
    if spread_pct is None:
        reasons.append("missing_spread_pct")

    if flags["sf_bid_ask_crossed"]:
        reasons.append("crossed_bid_ask")
    if flags["sf_zero_bid"]:
        reasons.append("zero_bid")
    if flags["sf_nonpositive_mid"]:
        reasons.append("nonpositive_mid")
    if flags["sf_wide_spread_flag"]:
        reasons.append("wide_spread")
    if flags["sf_low_open_interest_flag"]:
        reasons.append("low_open_interest")
    if flags["sf_low_volume_flag"]:
        reasons.append("low_volume")

    return flags, reasons


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build contract-level option behavior features with canonical quote overlay."
    )
    parser.add_argument("--behavior-input", required=True)
    parser.add_argument("--canonical-options", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--require-canonical", action="store_true")
    parser.add_argument("--max-spread-pct", type=float, default=0.25)
    parser.add_argument("--min-open-interest", type=float, default=1.0)
    parser.add_argument("--min-volume", type=float, default=0.0)
    parser.add_argument("--progress-every", type=int, default=500000)
    args = parser.parse_args()

    behavior_path = Path(args.behavior_input)
    canonical_path = Path(args.canonical_options)
    out = Path(args.output_dir)

    if not behavior_path.exists():
        raise FileNotFoundError(f"Missing behavior input: {behavior_path}")
    if not canonical_path.exists():
        raise FileNotFoundError(f"Missing canonical options data: {canonical_path}")

    out.mkdir(parents=True, exist_ok=True)

    features_path = out / "signalforge_option_contract_behavior_features.jsonl"
    summary_path = out / "signalforge_option_contract_behavior_features_summary.json"
    sample_path = out / "signalforge_option_contract_behavior_features_samples.jsonl"

    canonical_map, canonical_profile = load_canonical(canonical_path)

    row_count = 0
    bad_line_count = 0
    missing_key_count = 0

    overlay_state_counts = Counter()
    execution_eligibility_state_counts = Counter()
    execution_support_state_counts = Counter()
    reject_reason_counts = Counter()
    option_right_counts = Counter()
    dte_bucket_counts = Counter()
    delta_bucket_counts = Counter()
    spread_pct_bucket_counts = Counter()
    iv_bucket_counts = Counter()
    open_interest_bucket_counts = Counter()
    volume_bucket_counts = Counter()

    source_counts: dict[str, Counter] = defaultdict(Counter)
    value_coverage_counts = Counter()

    samples: list[dict[str, Any]] = []
    samples_by_state = Counter()

    writer = None
    if not args.summary_only:
        writer = features_path.open("w", encoding="utf-8")

    try:
        with behavior_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue

                try:
                    original_row = json.loads(line)
                    flat_row = flatten(original_row)
                except Exception:
                    bad_line_count += 1
                    continue

                row_count += 1

                key = make_key(flat_row)
                if key is None:
                    missing_key_count += 1

                canonical_row = canonical_map.get(key) if key is not None else None
                overlay_state = overlay_state_for(key, canonical_row)
                values, sources = derive_quote_values(flat_row, canonical_row)

                flags, reject_reasons = execution_flags_and_reasons(
                    values=values,
                    key=key,
                    canonical_row=canonical_row,
                    max_spread_pct=args.max_spread_pct,
                    min_open_interest=args.min_open_interest,
                    min_volume=args.min_volume,
                    require_canonical=args.require_canonical,
                )

                if reject_reasons:
                    execution_state = "execution_rejected"
                else:
                    execution_state = "execution_eligible"

                if canonical_row is None:
                    support_state = "behavior_surface_only"
                elif canonical_price_full(canonical_row):
                    support_state = "canonical_quote_backed_price_full"
                else:
                    support_state = "canonical_quote_backed_price_partial"

                key_fields = {
                    "sf_contract_key": key_to_string(key),
                    "sf_key_underlying_symbol": key[0] if key else None,
                    "sf_key_quote_date": key[1] if key else None,
                    "sf_key_expiration": key[2] if key else None,
                    "sf_key_strike": key[3] if key else None,
                    "sf_key_option_right": key[4] if key else None,
                }

                strike_to_underlying, log_moneyness, moneyness_bucket = compute_moneyness(
                    key[3] if key else get_first(flat_row, KEY_ALIASES["strike"]),
                    values.get("underlying_price"),
                )

                feature_row = dict(original_row)
                feature_row.update(key_fields)

                feature_row["sf_canonical_quote_overlay_state"] = overlay_state
                feature_row["sf_execution_support_state"] = support_state
                feature_row["sf_execution_eligibility_state"] = execution_state
                feature_row["sf_execution_reject_reasons"] = reject_reasons
                feature_row["sf_canonical_quote_matched"] = canonical_row is not None
                feature_row["sf_canonical_price_full"] = canonical_price_full(canonical_row)
                feature_row["sf_canonical_metrics_full"] = canonical_metrics_full(canonical_row)

                for field in SF_VALUE_FIELDS:
                    feature_row[f"sf_{field}"] = values.get(field)
                    feature_row[f"sf_{field}_source"] = sources.get(field, "missing")

                for field in CANONICAL_CARRY_FIELDS:
                    if canonical_row is None:
                        feature_row[f"canonical_{field}"] = None
                    else:
                        feature_row[f"canonical_{field}"] = canonical_row.get(field)

                feature_row.update(flags)

                feature_row["sf_dte_bucket"] = bucket_dte(values.get("dte"))
                feature_row["sf_abs_delta_bucket"] = bucket_abs_delta(values.get("delta"))
                feature_row["sf_spread_pct_bucket"] = bucket_spread_pct(values.get("spread_pct"))
                feature_row["sf_iv_bucket"] = bucket_iv(values.get("implied_volatility"))
                feature_row["sf_open_interest_bucket"] = bucket_count_like(values.get("open_interest"))
                feature_row["sf_volume_bucket"] = bucket_count_like(values.get("volume"))
                feature_row["sf_strike_to_underlying"] = strike_to_underlying
                feature_row["sf_log_moneyness"] = log_moneyness
                feature_row["sf_moneyness_bucket"] = moneyness_bucket

                overlay_state_counts[overlay_state] += 1
                execution_eligibility_state_counts[execution_state] += 1
                execution_support_state_counts[support_state] += 1

                for reason in reject_reasons:
                    reject_reason_counts[reason] += 1

                if key is not None:
                    option_right_counts[key[4]] += 1

                dte_bucket_counts[feature_row["sf_dte_bucket"]] += 1
                delta_bucket_counts[feature_row["sf_abs_delta_bucket"]] += 1
                spread_pct_bucket_counts[feature_row["sf_spread_pct_bucket"]] += 1
                iv_bucket_counts[feature_row["sf_iv_bucket"]] += 1
                open_interest_bucket_counts[feature_row["sf_open_interest_bucket"]] += 1
                volume_bucket_counts[feature_row["sf_volume_bucket"]] += 1

                for field in SF_VALUE_FIELDS:
                    source_counts[field][feature_row[f"sf_{field}_source"]] += 1
                    if not is_blank(feature_row.get(f"sf_{field}")):
                        value_coverage_counts[field] += 1

                if samples_by_state[overlay_state] < 10:
                    samples_by_state[overlay_state] += 1
                    samples.append(
                        {
                            "sf_contract_key": feature_row["sf_contract_key"],
                            "sf_canonical_quote_overlay_state": overlay_state,
                            "sf_execution_support_state": support_state,
                            "sf_execution_eligibility_state": execution_state,
                            "sf_execution_reject_reasons": reject_reasons,
                            "sf_bid": feature_row["sf_bid"],
                            "sf_ask": feature_row["sf_ask"],
                            "sf_mid": feature_row["sf_mid"],
                            "sf_spread": feature_row["sf_spread"],
                            "sf_spread_pct": feature_row["sf_spread_pct"],
                            "sf_implied_volatility": feature_row["sf_implied_volatility"],
                            "sf_delta": feature_row["sf_delta"],
                            "sf_open_interest": feature_row["sf_open_interest"],
                            "sf_volume": feature_row["sf_volume"],
                            "sf_dte": feature_row["sf_dte"],
                            "sf_abs_delta_bucket": feature_row["sf_abs_delta_bucket"],
                            "sf_spread_pct_bucket": feature_row["sf_spread_pct_bucket"],
                        }
                    )

                if writer is not None:
                    writer.write(json.dumps(feature_row, sort_keys=True, default=str) + "\n")

                if args.progress_every and row_count % args.progress_every == 0:
                    print(f"processed_behavior_rows={row_count}", flush=True)

    finally:
        if writer is not None:
            writer.close()

    if args.summary_only:
        features_path.unlink(missing_ok=True)

    summary = {
        "adapter_type": "option_contract_behavior_features_builder",
        "artifact_type": "signalforge_option_contract_behavior_features",
        "contract": "option_contract_behavior_features",
        "is_ready": True,
        "blocker_count": 0,
        "blockers": [],
        "inputs": {
            "behavior_input": str(behavior_path),
            "canonical_options": str(canonical_path),
        },
        "parameters": {
            "require_canonical": args.require_canonical,
            "max_spread_pct": args.max_spread_pct,
            "min_open_interest": args.min_open_interest,
            "min_volume": args.min_volume,
            "summary_only": args.summary_only,
        },
        "canonical_profile": canonical_profile,
        "behavior_profile": {
            "row_count": row_count,
            "bad_line_count": bad_line_count,
            "missing_key_count": missing_key_count,
        },
        "overlay_state_counts": dict(overlay_state_counts),
        "overlay_state_rates": {
            key: round(value / row_count, 6) if row_count else 0
            for key, value in overlay_state_counts.items()
        },
        "execution_support_state_counts": dict(execution_support_state_counts),
        "execution_support_state_rates": {
            key: round(value / row_count, 6) if row_count else 0
            for key, value in execution_support_state_counts.items()
        },
        "execution_eligibility_state_counts": dict(execution_eligibility_state_counts),
        "execution_eligibility_state_rates": {
            key: round(value / row_count, 6) if row_count else 0
            for key, value in execution_eligibility_state_counts.items()
        },
        "reject_reason_counts": dict(reject_reason_counts),
        "option_right_counts": dict(option_right_counts),
        "dte_bucket_counts": dict(dte_bucket_counts),
        "abs_delta_bucket_counts": dict(delta_bucket_counts),
        "spread_pct_bucket_counts": dict(spread_pct_bucket_counts),
        "iv_bucket_counts": dict(iv_bucket_counts),
        "open_interest_bucket_counts": dict(open_interest_bucket_counts),
        "volume_bucket_counts": dict(volume_bucket_counts),
        "sf_value_coverage_counts": dict(value_coverage_counts),
        "sf_value_coverage_rates": {
            key: round(value / row_count, 6) if row_count else 0
            for key, value in value_coverage_counts.items()
        },
        "sf_value_source_counts": {
            field: dict(counter)
            for field, counter in source_counts.items()
        },
        "paths": {
            "features_path": str(features_path) if not args.summary_only else None,
            "summary_path": str(summary_path),
            "sample_path": str(sample_path),
        },
    }

    write_json(summary_path, summary)
    write_jsonl(sample_path, samples)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
