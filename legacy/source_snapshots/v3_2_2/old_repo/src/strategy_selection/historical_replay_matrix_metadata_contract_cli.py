"""CLI for historical replay matrix metadata contract generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_contract import (
    build_signalforge_historical_replay_matrix_metadata_contract,
)
from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_contract_file_writer import (
    write_historical_replay_matrix_metadata_contract_result,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the SignalForge historical replay matrix metadata contract."
    )
    parser.add_argument(
        "--historical-edge-matrix-backfill-plan-source",
        required=True,
        help="Path to signalforge_historical_edge_matrix_backfill_plan.json or summary-shaped write result.",
    )
    parser.add_argument(
        "--strategy-matrix-edge-inventory-source",
        required=False,
        help="Optional path to signalforge_strategy_matrix_edge_inventory.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where contract artifacts will be written.",
    )
    args = parser.parse_args(argv)

    plan_source = _read_json(args.historical_edge_matrix_backfill_plan_source)
    inventory_source = (
        _read_json(args.strategy_matrix_edge_inventory_source)
        if args.strategy_matrix_edge_inventory_source
        else {}
    )

    result = build_signalforge_historical_replay_matrix_metadata_contract(
        historical_edge_matrix_backfill_plan_source=plan_source,
        strategy_matrix_edge_inventory_source=inventory_source,
    )
    summary = write_historical_replay_matrix_metadata_contract_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("status") != "blocked" else 1


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
