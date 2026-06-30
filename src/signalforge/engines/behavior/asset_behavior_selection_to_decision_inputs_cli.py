from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from signalforge.engines.behavior.asset_behavior_selection_to_decision_inputs import (
    build_signalforge_asset_behavior_selection_to_decision_inputs,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Split asset behavior selection into decision-export input artifacts."
    )

    parser.add_argument("--source", required=True, help="Path to asset behavior selection JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"source file does not exist: {source_path}")

    source = _read_json(source_path)

    result = build_signalforge_asset_behavior_selection_to_decision_inputs(
        source,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True, default=str))

    return 0 if result.get("status") in {"ready", "needs_review"} else 1


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"source JSON must be an object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())




