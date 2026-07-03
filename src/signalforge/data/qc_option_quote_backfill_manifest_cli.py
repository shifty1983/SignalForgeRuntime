from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
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


def parse_date(value: Any):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def is_weekday(value: Any) -> bool:
    d = parse_date(value)
    return bool(d and d.weekday() < 5)


def contract_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("option_symbol") or ""),
        str(row.get("expiration") or "")[:10],
        str(row.get("strike") or ""),
        str(row.get("option_right") or "").lower(),
    ])


def request_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("required_quote_date") or "")[:10],
    )


def compact_contract(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "option_symbol": row.get("option_symbol"),
        "occ_symbol": row.get("occ_symbol"),
        "expiration": str(row.get("expiration") or "")[:10],
        "strike": row.get("strike"),
        "option_right": str(row.get("option_right") or "").lower(),
        "role": row.get("role"),
        "quantity": row.get("quantity", 1),
        "selected_strategy": row.get("selected_strategy"),
        "quote_outcome_id": row.get("quote_outcome_id"),
        "decision_date": row.get("decision_date"),
        "target_exit_date": row.get("target_exit_date"),
    }


def run(args: argparse.Namespace) -> None:
    missing_path = Path(args.missing_manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    raw_missing_count = 0
    weekend_excluded_count = 0
    malformed_count = 0
    duplicate_contract_count = 0

    symbol_counts = Counter()
    date_counts = Counter()
    strategy_counts = Counter()

    for row in read_jsonl(missing_path):
        raw_missing_count += 1

        symbol = str(row.get("symbol") or "").upper()
        qdate = str(row.get("required_quote_date") or "")[:10]

        if not symbol or not qdate or parse_date(qdate) is None:
            malformed_count += 1
            continue

        if args.exclude_weekends and not is_weekday(qdate):
            weekend_excluded_count += 1
            continue

        key = request_key(row)
        contract = compact_contract(row)
        ckey = contract_key(row)

        if key not in grouped:
            grouped[key] = {
                "request_id": f"{symbol}_{qdate}_option_quote_backfill",
                "symbol": symbol,
                "quote_date": qdate,
                "source": "quantconnect",
                "request_type": "option_quote_snapshot_for_required_contracts",
                "contracts": [],
                "_contract_keys": set(),
            }

        if ckey in grouped[key]["_contract_keys"]:
            duplicate_contract_count += 1
            continue

        grouped[key]["contracts"].append(contract)
        grouped[key]["_contract_keys"].add(ckey)

        symbol_counts[symbol] += 1
        date_counts[qdate] += 1
        strategy_counts[str(row.get("selected_strategy") or "unknown")] += 1

    request_rows = []
    contract_request_count = 0

    for _, request in sorted(grouped.items(), key=lambda x: (x[0][1], x[0][0])):
        request.pop("_contract_keys", None)
        request["contract_count"] = len(request["contracts"])
        contract_request_count += request["contract_count"]
        request_rows.append(request)

    symbol_rows = [
        {"symbol": symbol, "missing_market_date_contract_count": count}
        for symbol, count in symbol_counts.most_common()
    ]

    date_rows = [
        {"quote_date": quote_date, "missing_market_date_contract_count": count}
        for quote_date, count in date_counts.most_common()
    ]

    strategy_rows = [
        {"selected_strategy": strategy, "missing_market_date_contract_count": count}
        for strategy, count in strategy_counts.most_common()
    ]

    summary = {
        "adapter_type": "qc_option_quote_backfill_manifest_builder",
        "artifact_type": "signalforge_qc_option_quote_backfill_manifest",
        "contract": "qc_option_quote_backfill_manifest",
        "is_ready": True,
        "readiness_state": "qc_option_quote_backfill_manifest_available",
        "missing_manifest": str(missing_path),
        "raw_missing_quote_count": raw_missing_count,
        "weekend_excluded_count": weekend_excluded_count,
        "malformed_count": malformed_count,
        "duplicate_contract_count": duplicate_contract_count,
        "market_date_request_count": len(request_rows),
        "contract_request_count": contract_request_count,
        "unique_symbol_count": len(symbol_counts),
        "unique_quote_date_count": len(date_counts),
        "paths": {
            "summary": str(output_dir / "signalforge_qc_option_quote_backfill_manifest_summary.json"),
            "requests": str(output_dir / "signalforge_qc_option_quote_backfill_requests.jsonl"),
            "missing_by_symbol": str(output_dir / "signalforge_qc_option_quote_backfill_missing_by_symbol.jsonl"),
            "missing_by_date": str(output_dir / "signalforge_qc_option_quote_backfill_missing_by_date.jsonl"),
            "missing_by_strategy": str(output_dir / "signalforge_qc_option_quote_backfill_missing_by_strategy.jsonl"),
        },
        "blockers": [] if request_rows else ["no_backfill_requests_generated"],
        "warnings": [
            "weekends are excluded when --exclude-weekends is set",
            "market holidays are not excluded yet unless they fall on weekends",
            "QuantConnect importer should skip non-trading dates if returned empty",
        ],
    }

    write_json(output_dir / "signalforge_qc_option_quote_backfill_manifest_summary.json", summary)
    write_jsonl(output_dir / "signalforge_qc_option_quote_backfill_requests.jsonl", request_rows)
    write_jsonl(output_dir / "signalforge_qc_option_quote_backfill_missing_by_symbol.jsonl", symbol_rows)
    write_jsonl(output_dir / "signalforge_qc_option_quote_backfill_missing_by_date.jsonl", date_rows)
    write_jsonl(output_dir / "signalforge_qc_option_quote_backfill_missing_by_strategy.jsonl", strategy_rows)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "raw_missing_quote_count": summary["raw_missing_quote_count"],
        "weekend_excluded_count": summary["weekend_excluded_count"],
        "market_date_request_count": summary["market_date_request_count"],
        "contract_request_count": summary["contract_request_count"],
        "unique_symbol_count": summary["unique_symbol_count"],
        "unique_quote_date_count": summary["unique_quote_date_count"],
        "paths": summary["paths"],
        "blockers": summary["blockers"],
    }, indent=2, sort_keys=True, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--exclude-weekends", action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
