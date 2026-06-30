from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.data_sources.quantconnect_replay_evidence_to_behavior_inputs.builder import (
    build_signalforge_quantconnect_replay_evidence_to_behavior_inputs,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert decoded QuantConnect replay evidence into SignalForge behavior inputs."
    )
    parser.add_argument("--inventory-source", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args(argv)

    inventory_path = Path(args.inventory_source)
    if not inventory_path.exists():
        raise SystemExit(f"inventory source does not exist: {inventory_path}")

    inventory_source = _read_json(inventory_path)

    result = build_signalforge_quantconnect_replay_evidence_to_behavior_inputs(
        inventory_source,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))

    return 0 if result.get("is_ready") else 1


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"inventory source must be a JSON object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
