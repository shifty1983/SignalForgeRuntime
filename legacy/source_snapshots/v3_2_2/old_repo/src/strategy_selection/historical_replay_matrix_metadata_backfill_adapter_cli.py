"""CLI for historical replay matrix metadata backfill adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_backfill_adapter import (
    build_signalforge_historical_replay_matrix_metadata_backfill_adapter,
)
from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_backfill_adapter_file_writer import (
    write_historical_replay_matrix_metadata_backfill_adapter_result,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill historical replay records with exact strategy-matrix metadata when available."
    )
    parser.add_argument(
        "--historical-replay-matrix-metadata-contract-source",
        required=True,
        help="Path to signalforge_historical_replay_matrix_metadata_contract.json.",
    )
    parser.add_argument(
        "--historical-replay-source",
        action="append",
        required=True,
        help="Path to a historical replay, edge, diagnostics, portfolio, or window-plan JSON source. Repeatable.",
    )
    parser.add_argument(
        "--strategy-matrix-edge-inventory-source",
        required=False,
        help="Optional path to signalforge_strategy_matrix_edge_inventory.json.",
    )
    parser.add_argument(
        "--mapping-overrides-source",
        required=False,
        help="Optional JSON file containing explicit mapping_overrides. Overrides are marked partial and require review.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where backfill adapter artifacts will be written.",
    )
    args = parser.parse_args(argv)

    contract_source = _read_json(args.historical_replay_matrix_metadata_contract_source)
    historical_sources = [_read_json(path) for path in args.historical_replay_source]
    inventory_source = (
        _read_json(args.strategy_matrix_edge_inventory_source)
        if args.strategy_matrix_edge_inventory_source
        else {}
    )
    overrides_source = _read_json(args.mapping_overrides_source) if args.mapping_overrides_source else {}

    result = build_signalforge_historical_replay_matrix_metadata_backfill_adapter(
        historical_replay_matrix_metadata_contract_source=contract_source,
        historical_replay_sources=historical_sources,
        strategy_matrix_edge_inventory_source=inventory_source,
        mapping_overrides_source=overrides_source,
    )
    summary = write_historical_replay_matrix_metadata_backfill_adapter_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("status") != "blocked" else 1


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
