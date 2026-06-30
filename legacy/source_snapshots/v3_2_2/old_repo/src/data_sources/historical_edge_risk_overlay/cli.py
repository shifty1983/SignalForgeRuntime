from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.historical_edge_risk_overlay.file_writer import (
    write_signalforge_historical_edge_risk_overlay_result,
)
from src.signalforge.data_sources.historical_edge_risk_overlay.overlay import (
    build_signalforge_historical_edge_risk_overlay,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply a risk overlay to strategy-adjusted historical edge validation output."
    )
    parser.add_argument(
        "--historical-edge-validation-source",
        required=True,
        help="Path to signalforge_historical_edge_validation.json.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args()

    source = _read_json(Path(args.historical_edge_validation_source))
    result = build_signalforge_historical_edge_risk_overlay(source)
    summary = write_signalforge_historical_edge_risk_overlay_result(result, args.output_dir)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result.get("is_ready") else 1


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"historical edge validation source does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"historical edge validation source is not a JSON object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
