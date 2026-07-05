from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


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


def row_date(row: dict[str, Any]) -> str | None:
    value = first_present(row, DATE_FIELDS)
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if text else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-jsonl", required=True)
    parser.add_argument("--metrics-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source_path = Path(args.source_jsonl)
    metrics_path = Path(args.metrics_jsonl)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "signalforge_options_execution_v2_source_coverage_audit.json"

    source_counts = Counter()
    source_bad_rows = 0

    for row in read_jsonl(source_path):
        symbol = row_symbol(row)
        quote_date = row_date(row)

        if not symbol or not quote_date:
            source_bad_rows += 1
            continue

        source_counts[(symbol, quote_date)] += 1

    metrics_counts = {}
    metrics_bad_rows = 0
    duplicate_metric_keys = []

    for row in read_jsonl(metrics_path):
        symbol = row_symbol(row)
        quote_date = row_date(row)

        if not symbol or not quote_date:
            metrics_bad_rows += 1
            continue

        key = (symbol, quote_date)

        if key in metrics_counts:
            duplicate_metric_keys.append(key)

        metrics_counts[key] = int(row.get("row_count") or 0)

    source_keys = set(source_counts)
    metrics_keys = set(metrics_counts)

    missing_keys = sorted(source_keys - metrics_keys)
    extra_keys = sorted(metrics_keys - source_keys)

    mismatched = []
    for key in sorted(source_keys & metrics_keys):
        source_count = source_counts[key]
        metrics_count = metrics_counts[key]

        if source_count != metrics_count:
            mismatched.append({
                "underlying_symbol": key[0],
                "quote_date": key[1],
                "source_row_count": source_count,
                "metrics_row_count": metrics_count,
            })

    missing_symbols = sorted(set(k[0] for k in missing_keys))
    extra_symbols = sorted(set(k[0] for k in extra_keys))

    blockers = []
    if source_bad_rows:
        blockers.append("source_rows_missing_symbol_or_date")
    if metrics_bad_rows:
        blockers.append("metrics_rows_missing_symbol_or_date")
    if duplicate_metric_keys:
        blockers.append("duplicate_metric_symbol_date_keys")
    if missing_keys:
        blockers.append("source_symbol_dates_missing_from_execution_metrics")
    if extra_keys:
        blockers.append("metrics_symbol_dates_extra_vs_source")
    if mismatched:
        blockers.append("source_metric_symbol_date_row_count_mismatch")

    summary = {
        "adapter_type": "options_execution_v2_source_coverage_auditor",
        "artifact_type": "signalforge_options_execution_v2_source_coverage_audit",
        "contract": "options_execution_v2_source_coverage_audit",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "source_path": str(source_path),
        "metrics_path": str(metrics_path),
        "source_row_count": sum(source_counts.values()),
        "source_bad_row_count": source_bad_rows,
        "source_symbol_count": len(set(k[0] for k in source_counts)),
        "source_symbol_date_count": len(source_counts),
        "metrics_row_count": len(metrics_counts),
        "metrics_bad_row_count": metrics_bad_rows,
        "metrics_symbol_count": len(set(k[0] for k in metrics_counts)),
        "metrics_symbol_date_count": len(metrics_counts),
        "metrics_total_contract_rows": sum(metrics_counts.values()),
        "missing_symbol_count": len(missing_symbols),
        "missing_symbols": missing_symbols,
        "missing_symbol_date_count": len(missing_keys),
        "missing_symbol_dates_sample": [
            {"underlying_symbol": k[0], "quote_date": k[1]}
            for k in missing_keys[:100]
        ],
        "extra_symbol_count": len(extra_symbols),
        "extra_symbols": extra_symbols,
        "extra_symbol_date_count": len(extra_keys),
        "extra_symbol_dates_sample": [
            {"underlying_symbol": k[0], "quote_date": k[1]}
            for k in extra_keys[:100]
        ],
        "duplicate_metric_key_count": len(duplicate_metric_keys),
        "duplicate_metric_keys_sample": [
            {"underlying_symbol": k[0], "quote_date": k[1]}
            for k in duplicate_metric_keys[:100]
        ],
        "mismatched_symbol_date_count": len(mismatched),
        "mismatched_symbol_dates_sample": mismatched[:100],
        "paths": {
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
