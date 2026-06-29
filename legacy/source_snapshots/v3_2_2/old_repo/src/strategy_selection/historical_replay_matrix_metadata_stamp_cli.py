"""CLI for historical replay matrix metadata stamping helper artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.strategy_selection.historical_replay_matrix_metadata_stamp_file_writer import (
    write_signalforge_historical_replay_matrix_metadata_stamping_helpers,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the historical replay matrix metadata stamping helper artifact."
    )
    parser.add_argument(
        "--historical-replay-export-matrix-metadata-patch-plan-source",
        required=True,
        help="Path to signalforge_historical_replay_export_matrix_metadata_patch_plan.json.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    args = parser.parse_args(argv)

    patch_plan_source = _read_json(args.historical_replay_export_matrix_metadata_patch_plan_source)
    result = write_signalforge_historical_replay_matrix_metadata_stamping_helpers(
        historical_replay_export_matrix_metadata_patch_plan_source=patch_plan_source,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
