from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-json", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    batch_path = Path(args.batch_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch = read_json(batch_path)
    batch_id = str(batch.get("batch_id") or batch_path.stem)

    raw = json.dumps(batch, separators=(",", ":"), sort_keys=True).encode("utf-8")
    compressed = gzip.compress(raw)
    payload_b64 = base64.b64encode(compressed).decode("ascii")

    payload_path = output_dir / f"{batch_id}_payload.b64.txt"
    payload_path.write_text(payload_b64 + "\n", encoding="utf-8")

    summary = {
        "adapter_type": "qc_canonical_backfill_payload_builder",
        "artifact_type": "signalforge_qc_canonical_backfill_payload",
        "is_ready": True,
        "batch_id": batch_id,
        "batch_json": str(batch_path),
        "payload_b64_path": str(payload_path),
        "raw_size": len(raw),
        "compressed_size": len(compressed),
        "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
        "request_count": len(batch.get("requests") or []),
        "contract_request_count": sum(int(r.get("contract_count") or len(r.get("contracts") or [])) for r in batch.get("requests") or []),
    }

    summary_path = output_dir / f"{batch_id}_payload_summary.json"
    write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

