from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
from pathlib import Path


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.=-]+", "_", value)
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    prefix = cleaned[:60] or "objectstore_item"
    return f"{prefix}_{digest}"


def maybe_decompress(payload: bytes) -> bytes:
    if payload[:2] == b"\x1f\x8b":
        return gzip.decompress(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-export", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    export_path = Path(args.research_export)
    out_dir = Path(args.output_dir)
    raw_dir = out_dir / "raw_objectstore_items"

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    combined_jsonl = out_dir / "signalforge_qc_option_behavior_v2_combined_decoded.jsonl"
    summary_path = out_dir / "signalforge_qc_option_behavior_v2_decode_summary.json"

    item_count = 0
    decoded_item_count = 0
    combined_row_count = 0
    bad_json_line_count = 0

    items = []

    with export_path.open("r", encoding="utf-8") as src, combined_jsonl.open("w", encoding="utf-8") as combined:
        for line in src:
            line = line.strip()
            if not line:
                continue

            item_count += 1
            envelope = json.loads(line)

            key = envelope["key"]
            payload = base64.b64decode(envelope["payload_b64"])
            payload = maybe_decompress(payload)

            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                text = payload.decode("utf-8", errors="replace")

            item_name = safe_name(key)
            raw_path = raw_dir / f"{item_count:05d}_{item_name}.txt"
            raw_path.write_text(text, encoding="utf-8")

            decoded_item_count += 1

            item_row_count = 0
            item_bad_json_line_count = 0

            for raw_line in text.splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                try:
                    obj = json.loads(raw_line)
                except Exception:
                    item_bad_json_line_count += 1
                    bad_json_line_count += 1
                    continue

                combined.write(json.dumps(obj, sort_keys=True) + "\n")
                item_row_count += 1
                combined_row_count += 1

            items.append(
                {
                    "key": key,
                    "raw_path": str(raw_path),
                    "payload_byte_count": envelope.get("payload_byte_count"),
                    "decoded_text_char_count": len(text),
                    "jsonl_row_count": item_row_count,
                    "bad_json_line_count": item_bad_json_line_count,
                }
            )

    summary = {
        "adapter_type": "qc_research_objectstore_export_decoder",
        "artifact_type": "signalforge_qc_option_behavior_v2_decode_summary",
        "input_path": str(export_path),
        "output_dir": str(out_dir),
        "item_count": item_count,
        "decoded_item_count": decoded_item_count,
        "combined_row_count": combined_row_count,
        "bad_json_line_count": bad_json_line_count,
        "paths": {
            "combined_jsonl": str(combined_jsonl),
            "summary_path": str(summary_path),
            "raw_objectstore_items_dir": str(raw_dir),
        },
        "items": items,
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
