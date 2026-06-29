"""CLI for historical replay export matrix metadata patch plan generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.strategy_selection.historical_replay_export_matrix_metadata_patch_plan import (
    build_signalforge_historical_replay_export_matrix_metadata_patch_plan,
)
from src.strategy_selection.historical_replay_export_matrix_metadata_patch_plan_file_writer import (
    write_historical_replay_export_matrix_metadata_patch_plan_result,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the SignalForge historical replay export matrix metadata patch plan."
    )
    parser.add_argument(
        "--historical-replay-export-matrix-metadata-envelope-source",
        required=True,
        help="Path to signalforge_historical_replay_export_matrix_metadata_envelope.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where patch plan artifacts will be written.",
    )
    args = parser.parse_args(argv)

    envelope_source = _read_json(args.historical_replay_export_matrix_metadata_envelope_source)
    result = build_signalforge_historical_replay_export_matrix_metadata_patch_plan(
        historical_replay_export_matrix_metadata_envelope_source=envelope_source,
    )
    summary = write_historical_replay_export_matrix_metadata_patch_plan_result(
        result, args.output_dir
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("status") != "blocked" else 1


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
