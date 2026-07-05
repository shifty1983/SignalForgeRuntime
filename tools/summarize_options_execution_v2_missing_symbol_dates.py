from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SOURCE_PATH = Path("artifacts/qc_replay_5y_behavior_inputs/signalforge_qc_replay_option_behavior_input.jsonl")
METRICS_PATH = Path("artifacts/options_execution_symbol_date_metrics_v2full_20260703_234020/signalforge_options_execution_symbol_date_metrics.jsonl")
OUTPUT_DIR = Path("artifacts/options_execution_v2_source_coverage_audit_v2full_20260703_234020")


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


def symbol(row: dict[str, Any]) -> str | None:
    value = first_present(row, SYMBOL_FIELDS)
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if " " in text and len(text) > 12:
        return None
    return text.replace("/", "-")


def quote_date(row: dict[str, Any]) -> str | None:
    value = first_present(row, DATE_FIELDS)
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if text else None


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source_counts = Counter()
    source_dates = defaultdict(set)

    for row in read_jsonl(SOURCE_PATH):
        s = symbol(row)
        d = quote_date(row)
        if s and d:
            source_counts[(s, d)] += 1
            source_dates[s].add(d)

    metric_counts = Counter()
    metric_dates = defaultdict(set)

    for row in read_jsonl(METRICS_PATH):
        s = symbol(row)
        d = quote_date(row)
        count = int(float(row.get("row_count") or 0))
        if s and d:
            metric_counts[(s, d)] += count
            metric_dates[s].add(d)

    missing_keys = sorted(set(source_counts) - set(metric_counts))

    by_symbol = defaultdict(list)
    for s, d in missing_keys:
        by_symbol[s].append(d)

    rows = []
    for s in sorted(by_symbol):
        dates = sorted(by_symbol[s])
        missing_contract_rows = sum(source_counts[(s, d)] for d in dates)
        has_any_metric_dates = s in metric_dates

        rows.append({
            "underlying_symbol": s,
            "missing_symbol_date_count": len(dates),
            "missing_contract_row_count": missing_contract_rows,
            "first_missing_date": dates[0],
            "last_missing_date": dates[-1],
            "source_date_count": len(source_dates[s]),
            "metric_date_count": len(metric_dates.get(s, set())),
            "entire_symbol_missing": not has_any_metric_dates,
            "missing_dates_sample": dates[:25],
        })

    rows = sorted(
        rows,
        key=lambda r: (r["entire_symbol_missing"], r["missing_contract_row_count"]),
        reverse=True,
    )

    rows_path = OUTPUT_DIR / "signalforge_options_execution_v2_missing_symbol_date_summary.jsonl"
    summary_path = OUTPUT_DIR / "signalforge_options_execution_v2_missing_symbol_date_summary.json"

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "adapter_type": "options_execution_v2_missing_symbol_date_summarizer",
        "artifact_type": "signalforge_options_execution_v2_missing_symbol_date_summary",
        "is_ready": len(rows) == 0,
        "blocker_count": 0 if len(rows) == 0 else 1,
        "blockers": [] if len(rows) == 0 else ["missing_source_symbol_dates"],
        "missing_symbol_count": len(rows),
        "entire_missing_symbol_count": sum(1 for r in rows if r["entire_symbol_missing"]),
        "partial_missing_symbol_count": sum(1 for r in rows if not r["entire_symbol_missing"]),
        "missing_symbol_date_count": len(missing_keys),
        "missing_contract_row_count": sum(source_counts[k] for k in missing_keys),
        "top_missing_by_contract_rows": rows[:50],
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
