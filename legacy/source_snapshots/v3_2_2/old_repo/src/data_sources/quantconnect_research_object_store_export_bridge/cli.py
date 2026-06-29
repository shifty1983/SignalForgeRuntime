from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.data_sources.quantconnect_research_object_store_export_bridge.bridge_script_builder import (
    build_signalforge_quantconnect_research_object_store_export_bridge,
)
from src.data_sources.quantconnect_research_object_store_export_bridge.decoder import (
    decode_signalforge_research_object_store_export_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or decode a QuantConnect Research Object Store export bridge payload."
    )
    parser.add_argument(
        "--operation",
        choices=["build-script", "decode-payload"],
        required=True,
    )
    parser.add_argument("--batch-source", default="")
    parser.add_argument("--payload-source", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--chunk-size", type=int, default=30_000)

    args = parser.parse_args()

    if args.operation == "build-script":
        if not args.batch_source:
            raise SystemExit("--batch-source is required for build-script")

        batch_source = _read_json(Path(args.batch_source))
        result = build_signalforge_quantconnect_research_object_store_export_bridge(
            batch_source,
            output_dir=args.output_dir,
            batch_id=args.batch_id or None,
            chunk_size=args.chunk_size,
        )

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("is_ready") else 1

    if not args.payload_source:
        raise SystemExit("--payload-source is required for decode-payload")

    result = decode_signalforge_research_object_store_export_payload(
        payload_source=args.payload_source,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("is_ready") else 1


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"source does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"source is not a JSON object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
