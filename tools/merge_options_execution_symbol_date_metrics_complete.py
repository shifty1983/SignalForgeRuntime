from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FULL_PATH = Path("artifacts/options_execution_symbol_date_metrics_v2full_20260703_234020/signalforge_options_execution_symbol_date_metrics.jsonl")
GAP_PATH = Path("artifacts/options_execution_symbol_date_metrics_v2gap_combined_plain_plus_retry2_20260704/signalforge_options_execution_symbol_date_metrics.jsonl")

OUTPUT_DIR = Path("artifacts/options_execution_symbol_date_metrics_complete_v2full_20260703_234020_plus_v2gap_combined_plain_plus_retry2_20260704")
ROWS_PATH = OUTPUT_DIR / "signalforge_options_execution_symbol_date_metrics.jsonl"
SUMMARY_PATH = OUTPUT_DIR / "signalforge_options_execution_symbol_date_metrics_summary.json"


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def key_for(row: dict[str, Any]) -> tuple[str, str]:
    symbol = str(row.get("symbol") or row.get("underlying_symbol") or "").strip().upper()
    quote_date = str(row.get("quote_date") or row.get("date") or "").strip()[:10]
    return symbol, quote_date


def load_rows(path: Path, source_name: str):
    rows = []
    duplicate_keys = []
    seen = set()

    for row in read_jsonl(path):
        key = key_for(row)
        if not key[0] or not key[1]:
            raise ValueError(f"{source_name} row missing symbol/date: {row}")

        if key in seen:
            duplicate_keys.append(key)

        seen.add(key)

        row = dict(row)
        row["merge_component"] = source_name
        rows.append(row)

    return rows, duplicate_keys


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    full_rows, full_duplicate_keys = load_rows(FULL_PATH, "v2full_20260703_234020")
    gap_rows, gap_duplicate_keys = load_rows(GAP_PATH, "v2gap_combined_plain_plus_retry2_20260704")

    full_by_key = {key_for(row): row for row in full_rows}
    gap_by_key = {key_for(row): row for row in gap_rows}

    overlap_keys = sorted(set(full_by_key) & set(gap_by_key))

    merged_by_key = dict(full_by_key)
    for key, row in gap_by_key.items():
        if key not in merged_by_key:
            merged_by_key[key] = row

    merged_rows = [
        merged_by_key[key]
        for key in sorted(merged_by_key)
    ]

    with ROWS_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        for row in merged_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    full_contract_rows = sum(int(row.get("row_count") or 0) for row in full_rows)
    gap_contract_rows = sum(int(row.get("row_count") or 0) for row in gap_rows)
    merged_contract_rows = sum(int(row.get("row_count") or 0) for row in merged_rows)

    summary = {
        "adapter_type": "options_execution_symbol_date_metrics_complete_merger",
        "artifact_type": "signalforge_options_execution_symbol_date_metrics",
        "is_ready": (
            len(full_duplicate_keys) == 0
            and len(gap_duplicate_keys) == 0
            and len(overlap_keys) == 0
            and len(merged_rows) == len(full_rows) + len(gap_rows)
        ),
        "blockers": [],
        "full_path": str(FULL_PATH),
        "gap_path": str(GAP_PATH),
        "full_row_count": len(full_rows),
        "gap_row_count": len(gap_rows),
        "output_row_count": len(merged_rows),
        "full_contract_row_count": full_contract_rows,
        "gap_contract_row_count": gap_contract_rows,
        "output_contract_row_count": merged_contract_rows,
        "symbol_count": len(set(key[0] for key in merged_by_key)),
        "symbol_date_count": len(merged_by_key),
        "full_duplicate_key_count": len(full_duplicate_keys),
        "gap_duplicate_key_count": len(gap_duplicate_keys),
        "overlap_key_count": len(overlap_keys),
        "overlap_keys_sample": overlap_keys[:20],
        "paths": {
            "rows_path": str(ROWS_PATH),
            "summary_path": str(SUMMARY_PATH),
        },
    }

    if full_duplicate_keys:
        summary["blockers"].append("full_duplicate_symbol_date_keys")
    if gap_duplicate_keys:
        summary["blockers"].append("gap_duplicate_symbol_date_keys")
    if overlap_keys:
        summary["blockers"].append("full_gap_overlap_symbol_date_keys")

    summary["blocker_count"] = len(summary["blockers"])

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
