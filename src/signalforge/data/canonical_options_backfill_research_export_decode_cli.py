from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


BEGIN = "SIGNALFORGE_CANONICAL_BACKFILL_EXPORT_BEGIN"
END = "SIGNALFORGE_CANONICAL_BACKFILL_EXPORT_END"
CHUNK_PREFIX = "SIGNALFORGE_CANONICAL_BACKFILL_EXPORT_CHUNK "


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def parse_export_text(text: str) -> tuple[dict[str, str], str]:
    inside = False
    meta: dict[str, str] = {}
    chunks: list[tuple[int, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line == BEGIN:
            inside = True
            continue

        if line == END:
            break

        if not inside or not line:
            continue

        if line.startswith(CHUNK_PREFIX):
            rest = line[len(CHUNK_PREFIX):]
            idx_text, chunk = rest.split(" ", 1)
            chunks.append((int(idx_text), chunk.strip()))
            continue

        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()

    if not chunks:
        raise ValueError("No export chunks found.")

    chunks.sort(key=lambda x: x[0])
    encoded = "".join(chunk for _, chunk in chunks)

    expected_count = int(meta.get("chunk_count") or 0)
    if expected_count and expected_count != len(chunks):
        raise ValueError(f"Chunk count mismatch expected={expected_count} actual={len(chunks)}")

    return meta, encoded


def decode_export(encoded: str, expected_sha: str | None) -> dict[str, Any]:
    compressed = base64.b64decode(encoded.encode("ascii"))
    actual_sha = hashlib.sha256(compressed).hexdigest()

    if expected_sha and expected_sha != actual_sha:
        raise ValueError(f"Checksum mismatch expected={expected_sha} actual={actual_sha}")

    raw = gzip.decompress(compressed).decode("utf-8")
    value = json.loads(raw)

    if not isinstance(value, dict):
        raise ValueError("Decoded export root was not an object.")

    return value


def decode_part_rows(part_payload: dict[str, Any]) -> list[dict[str, Any]]:
    part = part_payload.get("part") or {}
    encoded = part.get("payload")
    expected_sha = part.get("compressed_sha256")

    if not encoded:
        return []

    compressed = base64.b64decode(str(encoded).encode("ascii"))
    actual_sha = hashlib.sha256(compressed).hexdigest()

    if expected_sha and expected_sha != actual_sha:
        raise ValueError(
            "Part checksum mismatch "
            f"part_id={part.get('part_id')} expected={expected_sha} actual={actual_sha}"
        )

    raw = gzip.decompress(compressed).decode("utf-8")

    rows = []
    for line in raw.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def canonical_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("underlying_symbol") or "").upper(),
        str(row.get("quote_date") or "")[:10],
        str(row.get("expiration") or "")[:10],
        str(row.get("strike") or ""),
        str(row.get("option_right") or "").lower(),
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasted-export", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()

    pasted_path = Path(args.pasted_export)
    output_jsonl = Path(args.output_jsonl)
    summary_json = Path(args.summary_json)

    text = pasted_path.read_text(encoding="utf-8-sig", errors="ignore")
    meta, encoded = parse_export_text(text)
    export = decode_export(encoded, meta.get("compressed_sha256"))

    rows_by_key: dict[str, dict[str, Any]] = {}
    row_count_before_dedupe = 0
    resolution_counts = Counter()

    for part_payload in export.get("part_payloads", []):
        rows = decode_part_rows(part_payload)
        row_count_before_dedupe += len(rows)

        for row in rows:
            resolution_counts[str(row.get("quote_resolution_state") or "unknown")] += 1
            key = canonical_key(row)

            existing = rows_by_key.get(key)
            if existing is None:
                rows_by_key[key] = row
                continue

            old_good = existing.get("quote_resolution_state") == "quote_found"
            new_good = row.get("quote_resolution_state") == "quote_found"

            if new_good and not old_good:
                rows_by_key[key] = row

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as f:
        for row in rows_by_key.values():
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    manifest = export.get("manifest") or {}

    summary = {
        "adapter_type": "canonical_options_backfill_research_export_decoder",
        "artifact_type": "signalforge_canonical_options_backfill_decoded",
        "is_ready": True,
        "readiness_state": "decoded",
        "pasted_export": str(pasted_path),
        "manifest_key": export.get("manifest_key"),
        "batch_id": manifest.get("batch_id"),
        "manifest_row_count": manifest.get("row_count"),
        "manifest_part_count": manifest.get("part_count"),
        "decoded_part_payload_count": len(export.get("part_payloads", [])),
        "row_count_before_dedupe": row_count_before_dedupe,
        "row_count_after_dedupe": len(rows_by_key),
        "resolution_counts": dict(resolution_counts),
        "paths": {
            "output_jsonl": str(output_jsonl),
            "summary_json": str(summary_json),
        },
        "blockers": [],
    }

    write_json(summary_json, summary)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
