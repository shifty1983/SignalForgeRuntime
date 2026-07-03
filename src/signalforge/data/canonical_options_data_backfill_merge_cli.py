from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


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


def quote_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("underlying_symbol") or row.get("symbol") or "").upper(),
        str(row.get("quote_date") or row.get("date") or "")[:10],
        str(row.get("expiration") or "")[:10],
        str(row.get("strike") or ""),
        str(row.get("option_right") or "").lower(),
    ])


def quote_quality(row: dict[str, Any]) -> int:
    state = str(row.get("quote_resolution_state") or "")
    bid = row.get("bid")
    ask = row.get("ask")
    mid = row.get("mid")

    if state == "quote_found" and bid is not None and ask is not None and mid is not None:
        return 3

    if state == "quote_values_missing" and mid is not None:
        return 2

    if bid is not None or ask is not None or mid is not None:
        return 1

    return 0


def normalize_row(row: dict[str, Any], source_tag: str) -> dict[str, Any]:
    out = dict(row)

    if "underlying_symbol" not in out and "symbol" in out:
        out["underlying_symbol"] = out.get("symbol")

    out["underlying_symbol"] = str(out.get("underlying_symbol") or "").upper()
    out["quote_date"] = str(out.get("quote_date") or out.get("date") or "")[:10]
    out["expiration"] = str(out.get("expiration") or "")[:10]
    out["option_right"] = str(out.get("option_right") or "").lower()
    out["source_merge_tag"] = source_tag

    if out.get("mid") is None and out.get("bid") is not None and out.get("ask") is not None:
        try:
            out["mid"] = (float(out["bid"]) + float(out["ask"])) / 2.0
        except Exception:
            pass

    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-options", required=True)
    parser.add_argument("--backfill-options", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--reject-jsonl", required=True)
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()

    base_path = Path(args.base_options)
    backfill_path = Path(args.backfill_options)
    output_path = Path(args.output_jsonl)
    reject_path = Path(args.reject_jsonl)
    summary_path = Path(args.summary_json)

    rows_by_key: dict[str, dict[str, Any]] = {}
    source_counts = Counter()
    resolution_counts = Counter()
    reject_counts = Counter()

    base_count = 0
    backfill_count = 0
    imported_backfill_count = 0
    rejected_backfill_count = 0
    replaced_count = 0

    for row in read_jsonl(base_path):
        base_count += 1
        norm = normalize_row(row, "base")
        key = quote_key(norm)
        rows_by_key[key] = norm
        source_counts["base"] += 1

    reject_path.parent.mkdir(parents=True, exist_ok=True)
    with reject_path.open("w", encoding="utf-8") as reject_f:
        for row in read_jsonl(backfill_path):
            backfill_count += 1
            norm = normalize_row(row, "backfill")
            state = str(norm.get("quote_resolution_state") or "unknown")
            resolution_counts[state] += 1

            if quote_quality(norm) <= 0:
                rejected_backfill_count += 1
                reject_counts[state] += 1
                reject_f.write(json.dumps(norm, sort_keys=True, default=str) + "\n")
                continue

            key = quote_key(norm)
            existing = rows_by_key.get(key)

            if existing is None:
                rows_by_key[key] = norm
                imported_backfill_count += 1
                source_counts["backfill_new"] += 1
                continue

            if quote_quality(norm) > quote_quality(existing):
                rows_by_key[key] = norm
                imported_backfill_count += 1
                replaced_count += 1
                source_counts["backfill_replaced"] += 1
            else:
                source_counts["backfill_duplicate_not_better"] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out_f:
        for row in rows_by_key.values():
            out_f.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    summary = {
        "adapter_type": "canonical_options_data_backfill_merge_importer",
        "artifact_type": "signalforge_canonical_options_data_backfill_merge",
        "is_ready": True,
        "readiness_state": "merged",
        "base_options": str(base_path),
        "backfill_options": str(backfill_path),
        "base_count": base_count,
        "backfill_count": backfill_count,
        "imported_backfill_count": imported_backfill_count,
        "rejected_backfill_count": rejected_backfill_count,
        "replaced_count": replaced_count,
        "merged_count": len(rows_by_key),
        "backfill_resolution_counts": dict(resolution_counts),
        "reject_counts": dict(reject_counts),
        "source_counts": dict(source_counts),
        "paths": {
            "output_jsonl": str(output_path),
            "reject_jsonl": str(reject_path),
            "summary_json": str(summary_path),
        },
        "blockers": [],
    }

    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
