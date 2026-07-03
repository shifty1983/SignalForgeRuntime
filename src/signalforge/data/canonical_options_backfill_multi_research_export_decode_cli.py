from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


BEGIN = "SIGNALFORGE_CANONICAL_BACKFILL_MULTI_EXPORT_BEGIN"
END = "SIGNALFORGE_CANONICAL_BACKFILL_MULTI_EXPORT_END"
CHUNK_PREFIX = "SIGNALFORGE_CANONICAL_BACKFILL_MULTI_EXPORT_CHUNK "


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def parse_text(path: Path) -> tuple[dict[str, str], str]:
    inside = False
    meta = {}
    chunks = []

    for raw_line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
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
            idx, chunk = rest.split(" ", 1)
            chunks.append((int(idx), chunk.strip()))
        elif "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()

    if not chunks:
        raise ValueError("No multi-export chunks found.")

    chunks.sort(key=lambda x: x[0])
    expected = int(meta.get("chunk_count") or 0)
    if expected and expected != len(chunks):
        raise ValueError(f"Chunk count mismatch expected={expected} actual={len(chunks)}")

    return meta, "".join(c for _, c in chunks)


def decode_payload(encoded: str, sha: str | None) -> dict[str, Any]:
    compressed = base64.b64decode(encoded.encode("ascii"))
    actual_sha = hashlib.sha256(compressed).hexdigest()
    if sha and sha != actual_sha:
        raise ValueError(f"Checksum mismatch expected={sha} actual={actual_sha}")
    return json.loads(gzip.decompress(compressed).decode("utf-8"))


def decode_part_rows(part_payload: dict[str, Any]) -> list[dict[str, Any]]:
    part = part_payload.get("part") or {}
    encoded = part.get("payload")
    expected_sha = part.get("compressed_sha256")

    if not encoded:
        return []

    compressed = base64.b64decode(str(encoded).encode("ascii"))
    actual_sha = hashlib.sha256(compressed).hexdigest()
    if expected_sha and expected_sha != actual_sha:
        raise ValueError(f"Part checksum mismatch part_id={part.get('part_id')}")

    raw = gzip.decompress(compressed).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


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

    pasted = Path(args.pasted_export)
    output_jsonl = Path(args.output_jsonl)
    summary_json = Path(args.summary_json)

    meta, encoded = parse_text(pasted)
    payload = decode_payload(encoded, meta.get("compressed_sha256"))

    rows_by_key = {}
    resolution_counts = Counter()
    row_count_before_dedupe = 0
    export_count = 0
    part_count = 0

    for export in payload.get("exports", []):
        export_count += 1
        for part_payload in export.get("part_payloads", []):
            part_count += 1
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

    summary = {
        "adapter_type": "canonical_options_backfill_multi_research_export_decoder",
        "artifact_type": "signalforge_canonical_options_backfill_multi_decoded",
        "is_ready": True,
        "readiness_state": "decoded",
        "pasted_export": str(pasted),
        "manifest_key_count": payload.get("manifest_key_count"),
        "export_count": export_count,
        "part_count": part_count,
        "research_error_count": payload.get("error_count"),
        "research_errors": payload.get("errors") or [],
        "row_count_before_dedupe": row_count_before_dedupe,
        "row_count_after_dedupe": len(rows_by_key),
        "resolution_counts": dict(resolution_counts),
        "paths": {
            "output_jsonl": str(output_jsonl),
            "summary_json": str(summary_json),
        },
        "blockers": [] if not payload.get("errors") else ["research_export_reported_errors"],
    }

    write_json(summary_json, summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
