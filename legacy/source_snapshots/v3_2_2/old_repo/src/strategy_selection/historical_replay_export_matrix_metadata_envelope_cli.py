"""CLI for historical replay export matrix metadata envelope generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_export_matrix_metadata_envelope import (
    build_signalforge_historical_replay_export_matrix_metadata_envelope,
)
from src.signalforge.engines.strategy_selection.historical_replay_export_matrix_metadata_envelope_file_writer import (
    write_historical_replay_export_matrix_metadata_envelope_result,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the SignalForge historical replay export matrix metadata envelope."
    )
    parser.add_argument(
        "--historical-replay-matrix-metadata-contract-source",
        required=True,
        help="Path to signalforge_historical_replay_matrix_metadata_contract.json.",
    )
    parser.add_argument(
        "--historical-replay-source-metadata-backfill-source",
        required=True,
        help="Path to signalforge_historical_replay_source_metadata_backfill.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where envelope artifacts will be written.",
    )
    args = parser.parse_args(argv)

    contract_source = _read_json(args.historical_replay_matrix_metadata_contract_source)
    source_backfill_source = _read_json(args.historical_replay_source_metadata_backfill_source)

    result = build_signalforge_historical_replay_export_matrix_metadata_envelope(
        historical_replay_matrix_metadata_contract_source=contract_source,
        historical_replay_source_metadata_backfill_source=source_backfill_source,
    )
    summary = write_historical_replay_export_matrix_metadata_envelope_result(
        result, args.output_dir
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("status") != "blocked" else 1


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
