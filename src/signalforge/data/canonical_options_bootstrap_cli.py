from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def date10(v: Any) -> str:
    return str(v or "")[:10]


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten(v, key))
    elif isinstance(obj, list):
        out[prefix] = obj
        for i, item in enumerate(obj[:12]):
            if isinstance(item, dict):
                out.update(flatten(item, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def pick(flat: dict[str, Any], names: list[str], default: Any = None) -> Any:
    lowered = {k.lower(): k for k in flat.keys()}
    for name in names:
        k = lowered.get(name.lower())
        if k and flat[k] not in (None, ""):
            return flat[k]
    return default


def fnum(v: Any) -> float | None:
    try:
        if v in (None, "", [], {}):
            return None
        return float(v)
    except Exception:
        return None


def symbol(row: dict[str, Any]) -> str:
    flat = flatten(row)
    return str(pick(flat, ["symbol", "underlying_symbol", "underlying", "ticker"], "") or "").upper()


def decision_date(row: dict[str, Any]) -> str:
    flat = flatten(row)
    return date10(pick(flat, ["decision_date", "date", "entry_date", "trade_date"], ""))


def target_exit_date(row: dict[str, Any]) -> str:
    flat = flatten(row)
    return date10(pick(flat, ["target_exit_date", "outcome_date", "exit_date"], ""))


def quote_outcome_id(row: dict[str, Any]) -> str:
    flat = flatten(row)
    return str(pick(flat, ["quote_outcome_id", "selected_quote_outcome_id", "contract_outcome_id", "outcome_id"], "") or "")


def selected_strategy(row: dict[str, Any]) -> str:
    flat = flatten(row)
    return str(pick(flat, ["selected_strategy", "strategy", "strategy_family", "selected_strategy_family"], "") or "").lower()


def get_legs(row: dict[str, Any], role: str) -> list[dict[str, Any]]:
    if role == "entry":
        for key in ["selected_legs", "entry_legs"]:
            value = row.get(key)
            if isinstance(value, list) and value:
                return [x for x in value if isinstance(x, dict)]
    if role == "exit":
        value = row.get("exit_legs")
        if isinstance(value, list) and value:
            return [x for x in value if isinstance(x, dict)]
    return []


def option_right(leg: dict[str, Any]) -> str:
    return str(
        leg.get("option_right")
        or leg.get("right")
        or leg.get("put_call")
        or ""
    ).lower()


def infer_mid(bid: float | None, ask: float | None, explicit_mid: Any) -> float | None:
    mid = fnum(explicit_mid)
    if mid is not None:
        return mid
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return None


def quote_row_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("underlying_symbol", "")).upper(),
        str(row.get("quote_date", "")),
        str(row.get("expiration", "")),
        str(row.get("strike", "")),
        str(row.get("option_right", "")).lower(),
    ])


def normalize_leg(
    parent: dict[str, Any],
    leg: dict[str, Any],
    quote_role: str,
    quote_date: str,
    source_path: str,
) -> dict[str, Any] | None:
    sym = symbol(parent)

    bid = fnum(leg.get("bid") if quote_role == "entry" else leg.get("exit_bid", leg.get("bid")))
    ask = fnum(leg.get("ask") if quote_role == "entry" else leg.get("exit_ask", leg.get("ask")))

    mid_source = (
        leg.get("mid_price")
        if quote_role == "entry"
        else leg.get("exit_mid_price", leg.get("mid_price"))
    )
    mid = infer_mid(bid, ask, mid_source)

    expiration = date10(leg.get("expiration"))
    strike = leg.get("strike")
    right = option_right(leg)

    if not sym or not quote_date or not expiration or strike in (None, "") or not right:
        return None

    return {
        "underlying_symbol": sym,
        "quote_date": quote_date,
        "option_symbol": leg.get("option_symbol"),
        "occ_symbol": leg.get("occ_symbol"),
        "expiration": expiration,
        "dte": leg.get("dte"),
        "strike": strike,
        "option_right": right,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last": leg.get("last"),
        "volume": leg.get("volume"),
        "open_interest": leg.get("open_interest"),
        "implied_volatility": leg.get("implied_volatility"),
        "delta": leg.get("delta"),
        "gamma": leg.get("gamma"),
        "theta": leg.get("theta"),
        "vega": leg.get("vega"),
        "rho": leg.get("rho"),
        "underlying_price": leg.get("underlying_price"),
        "spread": None if bid is None or ask is None else ask - bid,
        "spread_pct": leg.get("spread_pct"),
        "moneyness": leg.get("moneyness"),
        "liquidity_state": leg.get("liquidity_state"),
        "quote_role_observed": quote_role,
        "quote_outcome_id": quote_outcome_id(parent),
        "selected_strategy": selected_strategy(parent),
        "source": "bootstrap_from_quote_outcomes",
        "source_file": source_path,
        "ingested_at": datetime.utcnow().isoformat() + "Z",
    }


def run(args: argparse.Namespace) -> None:
    source_path = Path(args.quote_outcomes)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_by_key: dict[str, dict[str, Any]] = {}
    source_row_count = 0
    extracted_count = 0
    skipped_count = 0
    role_counts = Counter()

    for parent in read_jsonl(source_path):
        source_row_count += 1

        for quote_role, qdate in [
            ("entry", decision_date(parent)),
            ("exit", target_exit_date(parent)),
        ]:
            legs = get_legs(parent, quote_role)
            if not legs:
                continue

            for leg in legs:
                normalized = normalize_leg(parent, leg, quote_role, qdate, str(source_path))
                if normalized is None:
                    skipped_count += 1
                    continue

                key = quote_row_key(normalized)
                existing = rows_by_key.get(key)

                if existing is None:
                    rows_by_key[key] = normalized
                    extracted_count += 1
                    role_counts[quote_role] += 1
                else:
                    # Prefer rows with full bid/ask/mid and richer metadata.
                    existing_score = sum(existing.get(x) is not None for x in ["bid", "ask", "mid", "volume", "open_interest", "implied_volatility"])
                    new_score = sum(normalized.get(x) is not None for x in ["bid", "ask", "mid", "volume", "open_interest", "implied_volatility"])
                    if new_score > existing_score:
                        rows_by_key[key] = normalized

    canonical_rows = list(rows_by_key.values())

    summary = {
        "adapter_type": "canonical_options_bootstrap_builder",
        "artifact_type": "signalforge_canonical_options_bootstrap",
        "contract": "canonical_options_bootstrap",
        "is_ready": True,
        "readiness_state": "canonical_options_bootstrap_available",
        "quote_outcomes": str(source_path),
        "source_row_count": source_row_count,
        "canonical_option_quote_count": len(canonical_rows),
        "extracted_count_before_dedupe": extracted_count,
        "skipped_count": skipped_count,
        "observed_role_counts": dict(role_counts.most_common()),
        "paths": {
            "summary": str(output_dir / "signalforge_canonical_options_bootstrap_summary.json"),
            "canonical_options_data": str(output_dir / "signalforge_canonical_options_data_bootstrap.jsonl"),
        },
        "blockers": [],
        "warnings": [
            "bootstrap only includes quotes already present in derived quote outcome rows",
            "missing exit quotes still require backfill from raw QuantConnect option data",
        ],
    }

    write_json(output_dir / "signalforge_canonical_options_bootstrap_summary.json", summary)
    write_jsonl(output_dir / "signalforge_canonical_options_data_bootstrap.jsonl", canonical_rows)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "source_row_count": summary["source_row_count"],
        "canonical_option_quote_count": summary["canonical_option_quote_count"],
        "observed_role_counts": summary["observed_role_counts"],
        "skipped_count": summary["skipped_count"],
        "paths": summary["paths"],
    }, indent=2, sort_keys=True, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-outcomes", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
