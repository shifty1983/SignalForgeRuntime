from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.options.partitioned_option_behavior_classifier.builder import (
    build_signalforge_partitioned_option_behavior_classifier,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify option behavior by decoded QuantConnect replay partition."
    )

    parser.add_argument("--asset-behavior-decision-export", required=True)
    parser.add_argument("--option-source-symbol-readiness", required=True)
    parser.add_argument("--inventory-source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-limit", type=int, default=None)

    args = parser.parse_args(argv)

    asset_source = _read_json(Path(args.asset_behavior_decision_export), "asset behavior decision export")
    readiness_source = _read_json(Path(args.option_source_symbol_readiness), "option source symbol readiness")
    inventory_source = _read_json(Path(args.inventory_source), "inventory source")

    result = build_signalforge_partitioned_option_behavior_classifier(
        asset_behavior_decision_export=asset_source,
        option_source_symbol_readiness=readiness_source,
        inventory_source=inventory_source,
        output_dir=args.output_dir,
        batch_limit=args.batch_limit,
    )

    print(json.dumps(result, indent=2, sort_keys=True, default=str))

    return 0 if result.get("status") in {"ready", "needs_review"} else 1


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{label} file does not exist: {path}")

    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object: {path}")

    return value


if __name__ == "__main__":
    raise SystemExit(main())
