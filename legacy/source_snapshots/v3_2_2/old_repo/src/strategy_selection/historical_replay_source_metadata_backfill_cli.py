"""CLI for historical replay source metadata backfill requirements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.strategy_selection.historical_replay_source_metadata_backfill import (
    build_signalforge_historical_replay_source_metadata_backfill,
)
from src.strategy_selection.historical_replay_source_metadata_backfill_file_writer import (
    write_historical_replay_source_metadata_backfill_result,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build source-level metadata backfill requirements for exact matrix edge attribution."
    )
    parser.add_argument(
        "--historical-replay-matrix-metadata-contract-source",
        required=True,
        help="Path to signalforge_historical_replay_matrix_metadata_contract.json.",
    )
    parser.add_argument(
        "--historical-replay-matrix-metadata-backfill-adapter-source",
        required=True,
        help="Path to signalforge_historical_replay_matrix_metadata_backfill_adapter.json.",
    )
    parser.add_argument(
        "--historical-edge-matrix-backfill-plan-source",
        required=False,
        help="Optional path to signalforge_historical_edge_matrix_backfill_plan.json.",
    )
    parser.add_argument(
        "--strategy-matrix-edge-inventory-source",
        required=False,
        help="Optional path to signalforge_strategy_matrix_edge_inventory.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where source metadata backfill artifacts will be written.",
    )
    args = parser.parse_args(argv)

    contract_source = _read_json(args.historical_replay_matrix_metadata_contract_source)
    adapter_source = _read_json(args.historical_replay_matrix_metadata_backfill_adapter_source)
    plan_source = (
        _read_json(args.historical_edge_matrix_backfill_plan_source)
        if args.historical_edge_matrix_backfill_plan_source
        else {}
    )
    inventory_source = (
        _read_json(args.strategy_matrix_edge_inventory_source)
        if args.strategy_matrix_edge_inventory_source
        else {}
    )

    result = build_signalforge_historical_replay_source_metadata_backfill(
        historical_replay_matrix_metadata_contract_source=contract_source,
        historical_replay_matrix_metadata_backfill_adapter_source=adapter_source,
        historical_edge_matrix_backfill_plan_source=plan_source,
        strategy_matrix_edge_inventory_source=inventory_source,
    )
    summary = write_historical_replay_source_metadata_backfill_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("status") != "blocked" else 1


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
