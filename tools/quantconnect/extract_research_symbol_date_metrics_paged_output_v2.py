from __future__ import annotations

import argparse
import base64
import gzip
import json
import re
from pathlib import Path
from typing import Any


BEGIN = "SF_SYMBOL_DATE_METRICS_CHUNK_BEGIN"
END = "SF_SYMBOL_DATE_METRICS_CHUNK_END"
SUMMARY_BEGIN = "SF_SYMBOL_DATE_METRICS_EXPORT_SUMMARY_BEGIN"
SUMMARY_END = "SF_SYMBOL_DATE_METRICS_EXPORT_SUMMARY_END"


def extract_blocks(text: str, begin: str, end: str) -> list[str]:
    blocks: list[str] = []
    parts = text.split(begin)

    for part in parts[1:]:
        if end not in part:
            continue

        block = part.split(end, 1)[0].strip()

        start = block.find("{")
        stop = block.rfind("}")

        if start < 0 or stop < start:
            continue

        blocks.append(block[start : stop + 1])

    return blocks


def decode_payload(payload_b64: str) -> list[dict[str, Any]]:
    raw = gzip.decompress(base64.b64decode(payload_b64)).decode("utf-8")
    rows: list[dict[str, Any]] = []

    for line in raw.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    pages_dir = Path(args.pages_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    page_paths = sorted(pages_dir.glob("*.txt"))

    if not page_paths:
        raise SystemExit(f"No page files found in {pages_dir}")

    all_text = "\n".join(
        p.read_text(encoding="utf-8-sig", errors="replace")
        for p in page_paths
    )

    summary_blocks = extract_blocks(all_text, SUMMARY_BEGIN, SUMMARY_END)
    source_summary = json.loads(summary_blocks[0]) if summary_blocks else {}

    chunk_blocks = extract_blocks(all_text, BEGIN, END)

    rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    bad_chunks: list[dict[str, Any]] = []

    for block in chunk_blocks:
        try:
            chunk = json.loads(block)
            chunk_rows.append({
                "chunk_index": chunk.get("chunk_index"),
                "total_chunks": chunk.get("total_chunks"),
                "row_count": chunk.get("row_count"),
                "run_id": chunk.get("run_id"),
                "encoding": chunk.get("encoding"),
            })

            payload_b64 = chunk.get("payload_b64")
            if not isinstance(payload_b64, str) or not payload_b64.strip():
                raise ValueError("missing payload_b64")

            decoded_rows = decode_payload(payload_b64)
            rows.extend(decoded_rows)

        except Exception as err:
            bad_chunks.append({
                "error": str(err),
                "block_preview": block[:500],
            })

    chunk_indices = [
        c.get("chunk_index")
        for c in chunk_rows
        if c.get("chunk_index") is not None
    ]

    duplicate_chunk_indices = sorted({
        x for x in chunk_indices if chunk_indices.count(x) > 1
    })

    row_keys = []
    for row in rows:
        symbol = row.get("symbol")
        quote_date = row.get("quote_date")
        if symbol and quote_date:
            row_keys.append((str(symbol), str(quote_date)))

    duplicate_symbol_dates = sorted({
        key for key in row_keys if row_keys.count(key) > 1
    })

    rows_path = output_dir / "signalforge_options_execution_symbol_date_metrics.jsonl"
    summary_path = output_dir / "signalforge_options_execution_symbol_date_metrics_summary.json"

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "adapter_type": "research_symbol_date_metrics_paged_output_extractor_v2",
        "artifact_type": "signalforge_options_execution_symbol_date_metrics",
        "is_ready": (
            len(rows) > 0
            and len(bad_chunks) == 0
            and len(duplicate_chunk_indices) == 0
        ),
        "source_page_count": len(page_paths),
        "source_summary": source_summary,
        "actual_chunk_count": len(chunk_blocks),
        "decoded_chunk_count": len(chunk_rows),
        "bad_chunk_count": len(bad_chunks),
        "bad_chunks": bad_chunks[:10],
        "duplicate_chunk_indices": duplicate_chunk_indices,
        "expected_total_chunks_from_source_summary": source_summary.get("expected_total_chunks"),
        "expected_output_row_count_from_source_summary": source_summary.get("output_row_count"),
        "output_row_count": len(rows),
        "symbol_count": len(set(str(r.get("symbol")) for r in rows if r.get("symbol"))),
        "symbol_date_count": len(set(row_keys)),
        "duplicate_symbol_date_count": len(duplicate_symbol_dates),
        "duplicate_symbol_dates_sample": duplicate_symbol_dates[:20],
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
