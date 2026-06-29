from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.data_sources.quantconnect_historical_replay_scaleout_plan.file_writer import (
    write_signalforge_quantconnect_historical_replay_scaleout_plan,
)
from src.data_sources.quantconnect_historical_replay_scaleout_plan.planner import (
    build_signalforge_quantconnect_historical_replay_scaleout_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create QuantConnect historical replay scaleout batches."
    )
    parser.add_argument("--quantconnect-historical-replay-handoff-source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-symbols-per-batch", type=int, default=10)
    parser.add_argument("--max-days-per-batch", type=int, default=180)
    parser.add_argument("--object-store-budget-bytes-per-batch", type=int, default=1_600_000_000)
    parser.add_argument(
        "--object-store-prefix-root",
        default="signalforge/historical_replay_scaleout",
    )

    args = parser.parse_args()

    source = _read_json(Path(args.quantconnect_historical_replay_handoff_source))
    result = build_signalforge_quantconnect_historical_replay_scaleout_plan(
        source,
        max_symbols_per_batch=args.max_symbols_per_batch,
        max_days_per_batch=args.max_days_per_batch,
        object_store_budget_bytes_per_batch=args.object_store_budget_bytes_per_batch,
        object_store_prefix_root=args.object_store_prefix_root,
    )
    summary = write_signalforge_quantconnect_historical_replay_scaleout_plan(
        result,
        args.output_dir,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result.get("is_ready") else 1


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"handoff source does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"handoff source is not a JSON object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
