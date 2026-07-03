from __future__ import annotations

import argparse
import json
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


def run(args: argparse.Namespace) -> None:
    source_path = Path(args.requests)
    output_dir = Path(args.output_dir)
    batch_dir = output_dir / "batches"
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_dir.mkdir(parents=True, exist_ok=True)

    requests = list(read_jsonl(source_path))

    batches = []
    current = []
    current_contracts = 0

    for req in requests:
        contract_count = int(req.get("contract_count") or len(req.get("contracts") or []))

        would_exceed_request_count = len(current) >= args.max_symbol_date_requests
        would_exceed_contract_count = current_contracts + contract_count > args.max_contracts

        if current and (would_exceed_request_count or would_exceed_contract_count):
            batches.append(current)
            current = []
            current_contracts = 0

        current.append(req)
        current_contracts += contract_count

    if current:
        batches.append(current)

    batch_index_rows = []
    total_contracts = 0
    total_symbol_date_requests = 0

    for idx, batch in enumerate(batches, start=1):
        contract_count = sum(int(x.get("contract_count") or len(x.get("contracts") or [])) for x in batch)
        symbols = sorted({str(x.get("symbol") or "").upper() for x in batch})
        dates = sorted({str(x.get("quote_date") or "")[:10] for x in batch})

        batch_name = f"qc_option_quote_backfill_batch_{idx:04d}.json"
        batch_path = batch_dir / batch_name

        payload = {
            "batch_id": f"qc_option_quote_backfill_batch_{idx:04d}",
            "request_type": "option_quote_backfill",
            "source_manifest": str(source_path),
            "symbol_date_request_count": len(batch),
            "contract_request_count": contract_count,
            "unique_symbol_count": len(symbols),
            "unique_quote_date_count": len(dates),
            "symbols": symbols,
            "quote_date_min": min(dates) if dates else "",
            "quote_date_max": max(dates) if dates else "",
            "requests": batch,
        }

        write_json(batch_path, payload)

        batch_index_rows.append({
            "batch_id": payload["batch_id"],
            "batch_path": str(batch_path),
            "symbol_date_request_count": len(batch),
            "contract_request_count": contract_count,
            "unique_symbol_count": len(symbols),
            "unique_quote_date_count": len(dates),
            "quote_date_min": payload["quote_date_min"],
            "quote_date_max": payload["quote_date_max"],
        })

        total_contracts += contract_count
        total_symbol_date_requests += len(batch)

    summary = {
        "adapter_type": "qc_option_quote_backfill_batch_builder",
        "artifact_type": "signalforge_qc_option_quote_backfill_batches",
        "contract": "qc_option_quote_backfill_batches",
        "is_ready": True,
        "readiness_state": "qc_backfill_batches_available",
        "source_requests": str(source_path),
        "batch_count": len(batches),
        "symbol_date_request_count": total_symbol_date_requests,
        "contract_request_count": total_contracts,
        "max_symbol_date_requests_per_batch": args.max_symbol_date_requests,
        "max_contracts_per_batch": args.max_contracts,
        "paths": {
            "summary": str(output_dir / "signalforge_qc_option_quote_backfill_batches_summary.json"),
            "batch_index": str(output_dir / "signalforge_qc_option_quote_backfill_batch_index.jsonl"),
            "batch_dir": str(batch_dir),
        },
        "blockers": [],
        "warnings": [
            "batches may still contain market holidays; QC exporter should mark empty holiday results as non_trading_date",
            "batch sizing should be adjusted based on QuantConnect runtime and ObjectStore limits",
        ],
    }

    write_json(output_dir / "signalforge_qc_option_quote_backfill_batches_summary.json", summary)
    write_jsonl(output_dir / "signalforge_qc_option_quote_backfill_batch_index.jsonl", batch_index_rows)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "batch_count": summary["batch_count"],
        "symbol_date_request_count": summary["symbol_date_request_count"],
        "contract_request_count": summary["contract_request_count"],
        "paths": summary["paths"],
        "blockers": summary["blockers"],
    }, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-symbol-date-requests", type=int, default=500)
    parser.add_argument("--max-contracts", type=int, default=2500)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
