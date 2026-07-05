from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


V2_REQUIRED_FIELDS = [
    "adapter_type",
    "artifact_type",
    "contract_key",
    "spread",
    "spread_pct",
    "quote_quality_state",
    "execution_eligibility_state",
    "execution_reject_reasons",
]


def present(value):
    return value is not None and value != ""


def decode_payload_envelope(row: dict):
    encoding = row.get("encoding")
    payload = row.get("payload")

    if encoding == "jsonl+gzip+base64" and payload:
        compressed = base64.b64decode(payload)

        expected_sha = row.get("compressed_sha256")
        actual_sha = hashlib.sha256(compressed).hexdigest()

        if expected_sha and actual_sha != expected_sha:
            raise RuntimeError(
                f"compressed_sha256 mismatch for part_id={row.get('part_id')}: "
                f"expected={expected_sha} actual={actual_sha}"
            )

        text = gzip.decompress(compressed).decode("utf-8")
        return text

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    parts_path = Path(args.parts_jsonl)
    out_path = Path(args.output_jsonl)
    summary_path = Path(args.summary)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    input_line_count = 0
    part_envelope_count = 0
    pass_through_row_count = 0
    final_row_count = 0
    bad_input_line_count = 0
    bad_inner_line_count = 0

    outer_artifact_type_counts = Counter()
    inner_artifact_type_counts = Counter()
    source_batch_id_counts = Counter()
    quote_resolution_state_counts = Counter()
    field_present_counts = Counter()

    sample_rows = []

    with parts_path.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as out:
        for raw_line in src:
            line = raw_line.strip()
            if not line:
                continue

            input_line_count += 1

            try:
                row = json.loads(line)
            except Exception:
                bad_input_line_count += 1
                continue

            outer_artifact_type_counts[str(row.get("artifact_type"))] += 1

            decoded_text = decode_payload_envelope(row)

            if decoded_text is None:
                # Already a final row; pass through.
                out.write(json.dumps(row, sort_keys=True) + "\n")
                pass_through_row_count += 1
                final_row_count += 1

                inner_artifact_type_counts[str(row.get("artifact_type"))] += 1
                source_batch_id_counts[str(row.get("source_batch_id"))] += 1
                quote_resolution_state_counts[str(row.get("quote_resolution_state"))] += 1

                for field in V2_REQUIRED_FIELDS:
                    if present(row.get(field)):
                        field_present_counts[field] += 1

                if len(sample_rows) < 10:
                    sample_rows.append(row)

                continue

            part_envelope_count += 1

            for inner_raw_line in decoded_text.splitlines():
                inner_line = inner_raw_line.strip()
                if not inner_line:
                    continue

                try:
                    inner = json.loads(inner_line)
                except Exception:
                    bad_inner_line_count += 1
                    continue

                out.write(json.dumps(inner, sort_keys=True) + "\n")
                final_row_count += 1

                inner_artifact_type_counts[str(inner.get("artifact_type"))] += 1
                source_batch_id_counts[str(inner.get("source_batch_id"))] += 1
                quote_resolution_state_counts[str(inner.get("quote_resolution_state"))] += 1

                for field in V2_REQUIRED_FIELDS:
                    if present(inner.get(field)):
                        field_present_counts[field] += 1

                if len(sample_rows) < 10:
                    sample_rows.append(inner)

    blockers = []

    if final_row_count == 0:
        blockers.append("no_final_rows_decoded")

    for field in V2_REQUIRED_FIELDS:
        if field_present_counts.get(field, 0) == 0:
            blockers.append(f"missing_v2_field_{field}")

    summary = {
        "adapter_type": "qc_objectstore_part_payload_decoder",
        "artifact_type": "signalforge_qc_objectstore_part_payload_decode_summary",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_path": str(parts_path),
        "input_line_count": input_line_count,
        "part_envelope_count": part_envelope_count,
        "pass_through_row_count": pass_through_row_count,
        "final_row_count": final_row_count,
        "bad_input_line_count": bad_input_line_count,
        "bad_inner_line_count": bad_inner_line_count,
        "outer_artifact_type_counts": dict(outer_artifact_type_counts),
        "inner_artifact_type_counts": dict(inner_artifact_type_counts),
        "source_batch_id_counts": dict(source_batch_id_counts),
        "quote_resolution_state_counts": dict(quote_resolution_state_counts),
        "field_present_counts": dict(field_present_counts),
        "field_present_rates": {
            field: round(field_present_counts.get(field, 0) / final_row_count, 8)
            if final_row_count
            else 0
            for field in V2_REQUIRED_FIELDS
        },
        "sample_rows": sample_rows,
        "paths": {
            "output_jsonl": str(out_path),
            "summary": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
