from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SOURCE_PATH = Path("artifacts/qc_replay_5y_behavior_inputs/signalforge_qc_replay_option_behavior_input.jsonl")

MISSING_SUMMARY_PATH = Path(
    "artifacts/options_execution_v2_source_coverage_audit_v2full_20260703_234020/"
    "signalforge_options_execution_v2_missing_symbol_date_summary.jsonl"
)

OUTPUT_DIR = Path("artifacts/qc_option_behavior_v2_missing_backfill_input_v2full_20260703_234020")
OUTPUT_PATH = OUTPUT_DIR / "signalforge_qc_option_behavior_v2_missing_backfill_input.jsonl"
SUMMARY_PATH = OUTPUT_DIR / "signalforge_qc_option_behavior_v2_missing_backfill_input_summary.json"


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
    if not text:
        return None
    if " " in text and len(text) > 12:
        return None
    return text.replace("/", "-")


def row_date(row: dict[str, Any]) -> str | None:
    value = first_present(row, DATE_FIELDS)
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if text else None


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    missing_keys = set()
    missing_symbols = set()

    for row in read_jsonl(MISSING_SUMMARY_PATH):
        symbol = str(row["underlying_symbol"]).upper()
        missing_symbols.add(symbol)
        for date_value in row.get("missing_dates_sample", []):
            missing_keys.add((symbol, str(date_value)[:10]))

    # The summary rows only contain a sample of dates, so rebuild the missing keys
    # directly from the detailed source-vs-metrics comparison.
    # Safer path: use source rows minus current metrics rows.
    metrics_path = Path(
        "artifacts/options_execution_symbol_date_metrics_v2full_20260703_234020/"
        "signalforge_options_execution_symbol_date_metrics.jsonl"
    )

    metric_keys = set()
    for row in read_jsonl(metrics_path):
        symbol = row_symbol(row)
        date_value = row_date(row)
        if symbol and date_value:
            metric_keys.add((symbol, date_value))

    selected_rows = 0
    source_rows = 0
    selected_symbol_dates = set()
    selected_symbols = set()

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        for row in read_jsonl(SOURCE_PATH):
            source_rows += 1
            symbol = row_symbol(row)
            date_value = row_date(row)

            if not symbol or not date_value:
                continue

            key = (symbol, date_value)

            if key not in metric_keys:
                selected_rows += 1
                selected_symbol_dates.add(key)
                selected_symbols.add(symbol)
                handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "adapter_type": "option_behavior_v2_missing_backfill_input_builder",
        "artifact_type": "signalforge_qc_option_behavior_v2_missing_backfill_input",
        "is_ready": selected_rows > 0,
        "blocker_count": 0 if selected_rows > 0 else 1,
        "blockers": [] if selected_rows > 0 else ["no_missing_backfill_rows_selected"],
        "source_path": str(SOURCE_PATH),
        "metrics_path": str(metrics_path),
        "source_row_count": source_rows,
        "output_row_count": selected_rows,
        "output_symbol_count": len(selected_symbols),
        "output_symbol_date_count": len(selected_symbol_dates),
        "output_symbols": sorted(selected_symbols),
        "paths": {
            "rows_path": str(OUTPUT_PATH),
            "summary_path": str(SUMMARY_PATH),
        },
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
