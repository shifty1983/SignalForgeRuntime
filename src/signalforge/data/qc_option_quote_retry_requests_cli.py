from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PIPE_KEY_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)\|(\d{4}-\d{2}-\d{2})\|(\d{4}-\d{2}-\d{2})\|([0-9.]+)\|(call|put|c|p)$",
    re.IGNORECASE,
)


def read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def norm_right(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in ("c", "call", "optionright.call"):
        return "call"
    if s in ("p", "put", "optionright.put"):
        return "put"
    return s


def iter_leaf_values(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            next_path = f"{path}.{k}" if path else str(k)
            yield from iter_leaf_values(v, next_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            next_path = f"{path}[{i}]"
            yield from iter_leaf_values(v, next_path)
    else:
        yield path, obj


def leaf_map(row: dict[str, Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = defaultdict(list)

    for path, value in iter_leaf_values(row):
        name = path.split(".")[-1]
        name = name.split("[")[0]
        key = name.lower()
        out[key].append(value)

    return out


def pick(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if row.get(name) not in (None, ""):
            return row.get(name)

    leaves = leaf_map(row)
    for name in names:
        values = leaves.get(name.lower()) or []
        for v in values:
            if v not in (None, ""):
                return v

    return None


def parse_pipe_key(row: dict[str, Any]) -> dict[str, Any] | None:
    candidate_names = [
        "quote_key",
        "required_quote_key",
        "lookup_key",
        "coverage_key",
        "canonical_key",
        "option_quote_key",
        "key",
    ]

    for name in candidate_names:
        value = pick(row, [name])
        if value:
            m = PIPE_KEY_RE.match(str(value).strip())
            if m:
                return {
                    "symbol": m.group(1).upper(),
                    "quote_date": m.group(2),
                    "expiration": m.group(3),
                    "strike": float(m.group(4)),
                    "option_right": norm_right(m.group(5)),
                }

    for _, value in iter_leaf_values(row):
        if isinstance(value, str):
            m = PIPE_KEY_RE.match(value.strip())
            if m:
                return {
                    "symbol": m.group(1).upper(),
                    "quote_date": m.group(2),
                    "expiration": m.group(3),
                    "strike": float(m.group(4)),
                    "option_right": norm_right(m.group(5)),
                }

    return None


def extract_contract(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    parsed = parse_pipe_key(row)
    if parsed:
        return parsed, "pipe_key"

    symbol = pick(row, [
        "symbol",
        "underlying_symbol",
        "underlying",
        "ticker",
        "root_symbol",
        "required_symbol",
        "selected_symbol",
    ])

    quote_date = pick(row, [
        "quote_date",
        "date",
        "required_quote_date",
        "target_quote_date",
        "candidate_quote_date",
        "exit_quote_date",
        "entry_quote_date",
    ])

    expiration = pick(row, [
        "expiration",
        "expiry",
        "expiration_date",
        "expiry_date",
        "required_expiration",
        "selected_expiration",
    ])

    strike = pick(row, [
        "strike",
        "required_strike",
        "selected_strike",
        "option_strike",
    ])

    option_right = pick(row, [
        "option_right",
        "right",
        "put_call",
        "call_put",
        "option_type",
        "required_option_right",
        "selected_option_right",
    ])

    option_right = norm_right(option_right)

    if not symbol or not quote_date or not expiration or strike in (None, "") or option_right not in ("call", "put"):
        return None, "missing_identity_fields"

    try:
        strike_float = float(strike)
    except Exception:
        return None, "bad_strike"

    return {
        "symbol": str(symbol).upper(),
        "quote_date": str(quote_date)[:10],
        "expiration": str(expiration)[:10],
        "strike": strike_float,
        "option_right": option_right,
    }, "field_extract"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing-quotes", required=True)
    parser.add_argument("--weak-quotes", required=True)
    parser.add_argument("--output-requests", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--include-weak", action="store_true")
    args = parser.parse_args()

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    seen_contracts = set()

    input_counts = Counter()
    extract_counts = Counter()
    skipped_examples = []

    def add_row(row: dict[str, Any], source_state: str) -> None:
        input_counts[source_state] += 1

        contract, method = extract_contract(row)
        extract_counts[f"{source_state}|{method}"] += 1

        if contract is None:
            if len(skipped_examples) < 10:
                skipped_examples.append({
                    "source_state": source_state,
                    "reason": method,
                    "keys": list(row.keys()),
                    "row": row,
                })
            return

        ck = "|".join([
            contract["symbol"],
            contract["quote_date"],
            contract["expiration"],
            str(contract["strike"]),
            contract["option_right"],
        ])

        if ck in seen_contracts:
            extract_counts[f"{source_state}|duplicate_contract"] += 1
            return

        seen_contracts.add(ck)

        key = (contract["symbol"], contract["quote_date"])

        if key not in grouped:
            grouped[key] = {
                "symbol": contract["symbol"],
                "quote_date": contract["quote_date"],
                "contracts": [],
                "source_states": set(),
            }

        grouped[key]["contracts"].append({
            "expiration": contract["expiration"],
            "strike": contract["strike"],
            "option_right": contract["option_right"],
            "source_state": source_state,
            "required_role": pick(row, ["required_role", "role", "quote_role"]),
            "selected_quote_outcome_id": pick(row, [
                "selected_quote_outcome_id",
                "quote_outcome_id",
                "contract_outcome_id",
            ]),
        })
        grouped[key]["source_states"].add(source_state)

    for row in read_jsonl(Path(args.missing_quotes)):
        add_row(row, "missing")

    if args.include_weak:
        for row in read_jsonl(Path(args.weak_quotes)):
            add_row(row, "weak")

    requests = []
    for idx, ((symbol, quote_date), req) in enumerate(sorted(grouped.items()), start=1):
        contracts = req["contracts"]
        requests.append({
            "request_id": f"retry_{idx:06d}_{symbol}_{quote_date}",
            "symbol": symbol,
            "quote_date": quote_date,
            "contract_count": len(contracts),
            "contracts": contracts,
            "source_states": sorted(req["source_states"]),
        })

    output_path = Path(args.output_requests)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for req in requests:
            f.write(json.dumps(req, sort_keys=True, default=str) + "\n")

    summary = {
        "adapter_type": "qc_option_quote_retry_request_builder",
        "artifact_type": "signalforge_qc_option_quote_retry_requests",
        "is_ready": len(requests) > 0,
        "readiness_state": "retry_requests_available" if requests else "no_retry_requests",
        "missing_quotes": args.missing_quotes,
        "weak_quotes": args.weak_quotes,
        "include_weak": bool(args.include_weak),
        "input_counts": dict(input_counts),
        "extract_counts": dict(extract_counts),
        "symbol_date_request_count": len(requests),
        "contract_request_count": sum(len(r["contracts"]) for r in requests),
        "unique_symbol_count": len({r["symbol"] for r in requests}),
        "unique_quote_date_count": len({r["quote_date"] for r in requests}),
        "skipped_example_count": len(skipped_examples),
        "skipped_examples": skipped_examples,
        "paths": {
            "output_requests": str(output_path),
            "summary_json": args.summary_json,
        },
        "blockers": [] if requests else ["no_retry_requests"],
    }

    write_json(Path(args.summary_json), summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
