from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def normalize_right(value: Any) -> str | None:
    if is_blank(value):
        return None
    text = str(value).strip().upper()
    if text in {"P", "PUT"}:
        return "put"
    if text in {"C", "CALL"}:
        return "call"
    return text.lower()


def normalize_date(value: Any) -> str | None:
    if is_blank(value):
        return None
    return str(value)[:10]


def normalize_strike(value: Any) -> float | None:
    if is_blank(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def make_occ_symbol(symbol: str, expiration: str, option_right: str, strike: float) -> str:
    # OCC root is not always exact for every ETF/index symbol, but this is useful metadata.
    # The QC template should still build symbols using symbol/date/right/strike, not depend on this only.
    root = symbol.upper()
    yymmdd = expiration.replace("-", "")[2:]
    cp = "P" if option_right.lower() == "put" else "C"
    strike_int = int(round(float(strike) * 1000))
    return f"{root}{yymmdd}{cp}{strike_int:08d}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--behavior-input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-size-contracts", type=int, default=2500)
    parser.add_argument("--max-batches", type=int, default=0)
    args = parser.parse_args()

    behavior_path = Path(args.behavior_input)
    out = Path(args.output_dir)

    grouped = defaultdict(dict)

    row_count = 0
    skipped_count = 0
    duplicate_contract_count = 0

    with behavior_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            row_count += 1
            row = json.loads(line)

            symbol = str(row.get("underlying_symbol") or row.get("symbol") or "").upper()
            quote_date = normalize_date(row.get("quote_date") or row.get("date"))
            expiration = normalize_date(row.get("expiration"))
            strike = normalize_strike(row.get("strike"))
            option_right = normalize_right(row.get("option_right"))

            if not symbol or not quote_date or not expiration or strike is None or not option_right:
                skipped_count += 1
                continue

            req_key = (symbol, quote_date)
            contract_key = (expiration, strike, option_right)

            if contract_key in grouped[req_key]:
                duplicate_contract_count += 1
                continue

            grouped[req_key][contract_key] = {
                "option_symbol": row.get("option_symbol"),
                "occ_symbol": row.get("occ_symbol") or make_occ_symbol(symbol, expiration, option_right, strike),
                "expiration": expiration,
                "strike": strike,
                "option_right": option_right,
            }

    batches = []
    current_requests = []
    current_contract_count = 0
    batch_index = 0

    for (symbol, quote_date), contract_map in sorted(grouped.items()):
        contracts = list(contract_map.values())
        request = {
            "request_id": f"{symbol}_{quote_date}",
            "symbol": symbol,
            "quote_date": quote_date,
            "contract_count": len(contracts),
            "contracts": contracts,
        }

        if current_contract_count + len(contracts) > args.batch_size_contracts and current_requests:
            batch_index += 1
            batches.append(
                {
                    "batch_id": f"qc_option_behavior_v2_batch_{batch_index:05d}",
                    "requests": current_requests,
                }
            )
            current_requests = []
            current_contract_count = 0

        current_requests.append(request)
        current_contract_count += len(contracts)

    if current_requests:
        batch_index += 1
        batches.append(
            {
                "batch_id": f"qc_option_behavior_v2_batch_{batch_index:05d}",
                "requests": current_requests,
            }
        )

    if args.max_batches and args.max_batches > 0:
        batches = batches[: args.max_batches]

    out.mkdir(parents=True, exist_ok=True)

    manifest_rows = []

    for index, batch in enumerate(batches, start=1):
        path = out / f"{batch['batch_id']}.json"
        path.write_text(json.dumps(batch, indent=2, sort_keys=True), encoding="utf-8")

        contract_count = sum(len(req.get("contracts") or []) for req in batch["requests"])

        manifest_rows.append(
            {
                "batch_id": batch["batch_id"],
                "path": str(path),
                "request_count": len(batch["requests"]),
                "contract_count": contract_count,
            }
        )

    summary = {
        "adapter_type": "option_behavior_v2_backfill_batch_builder",
        "artifact_type": "signalforge_option_behavior_v2_backfill_batches",
        "contract": "option_behavior_v2_backfill_batches",
        "is_ready": True,
        "blocker_count": 0,
        "blockers": [],
        "input_path": str(behavior_path),
        "input_row_count": row_count,
        "skipped_count": skipped_count,
        "duplicate_contract_count": duplicate_contract_count,
        "symbol_date_request_count": len(grouped),
        "batch_count": len(batches),
        "total_contract_request_count": sum(row["contract_count"] for row in manifest_rows),
        "parameters": {
            "batch_size_contracts": args.batch_size_contracts,
            "max_batches": args.max_batches,
        },
        "paths": {
            "summary_path": str(out / "signalforge_option_behavior_v2_backfill_batches_summary.json"),
            "manifest_path": str(out / "signalforge_option_behavior_v2_backfill_batches_manifest.jsonl"),
        },
    }

    (out / "signalforge_option_behavior_v2_backfill_batches_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with (out / "signalforge_option_behavior_v2_backfill_batches_manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in manifest_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
