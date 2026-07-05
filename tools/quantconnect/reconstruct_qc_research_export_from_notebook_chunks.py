from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks-text", required=True)
    parser.add_argument("--output-export", required=True)
    args = parser.parse_args()

    chunks_path = Path(args.chunks_text)
    output_path = Path(args.output_export)

    chunks = {}
    chunk_count = None
    export_sha256 = None
    compressed_sha256 = None
    export_filename = None

    for raw_line in chunks_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if not line.startswith("{"):
            continue

        try:
            row = json.loads(line)
        except Exception:
            continue

        if row.get("artifact_type") != "signalforge_qc_research_export_copy_chunk":
            continue

        idx = int(row["chunk_index"])
        total = int(row["chunk_count"])

        if chunk_count is None:
            chunk_count = total
        elif chunk_count != total:
            raise RuntimeError(f"Inconsistent chunk_count: {chunk_count} vs {total}")

        if export_sha256 is None:
            export_sha256 = row.get("export_sha256")
        elif export_sha256 != row.get("export_sha256"):
            raise RuntimeError("Inconsistent export_sha256 across chunks")

        if compressed_sha256 is None:
            compressed_sha256 = row.get("compressed_sha256")
        elif compressed_sha256 != row.get("compressed_sha256"):
            raise RuntimeError("Inconsistent compressed_sha256 across chunks")

        export_filename = export_filename or row.get("export_filename")

        chunks[idx] = row["payload_b64_chunk"]

    if chunk_count is None:
        raise RuntimeError("No chunk JSON rows found in chunks text file")

    missing = [idx for idx in range(chunk_count) if idx not in chunks]
    if missing:
        raise RuntimeError(f"Missing chunks: {missing[:50]} total_missing={len(missing)}")

    combined_b64 = "".join(chunks[idx] for idx in range(chunk_count))
    compressed = base64.b64decode(combined_b64)

    actual_compressed_sha256 = hashlib.sha256(compressed).hexdigest()
    if compressed_sha256 and actual_compressed_sha256 != compressed_sha256:
        raise RuntimeError(
            f"Compressed sha256 mismatch: expected={compressed_sha256} actual={actual_compressed_sha256}"
        )

    export_bytes = gzip.decompress(compressed)

    actual_export_sha256 = hashlib.sha256(export_bytes).hexdigest()
    if export_sha256 and actual_export_sha256 != export_sha256:
        raise RuntimeError(
            f"Export sha256 mismatch: expected={export_sha256} actual={actual_export_sha256}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(export_bytes)

    summary = {
        "adapter_type": "qc_research_export_chunk_reconstructor",
        "artifact_type": "signalforge_qc_research_export_reconstruction",
        "is_ready": True,
        "blocker_count": 0,
        "blockers": [],
        "input_chunks_text": str(chunks_path),
        "output_export": str(output_path),
        "export_filename_from_research": export_filename,
        "chunk_count": chunk_count,
        "export_byte_count": len(export_bytes),
        "export_sha256": actual_export_sha256,
        "compressed_sha256": actual_compressed_sha256,
    }

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
