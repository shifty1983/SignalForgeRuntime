"""CLI for the historical replay matrix metadata rerun plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_rerun_plan_file_writer import (
    write_signalforge_historical_replay_matrix_metadata_rerun_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a historical replay matrix metadata rerun plan.")
    parser.add_argument(
        "--matrix-metadata-patch-coverage-audit-source",
        required=True,
        help="Path to signalforge_matrix_metadata_patch_coverage_audit.json.",
    )
    parser.add_argument(
        "--historical-replay-export-matrix-metadata-patch-plan-source",
        required=False,
        help="Optional path to signalforge_historical_replay_export_matrix_metadata_patch_plan.json.",
    )
    parser.add_argument(
        "--exact-matrix-edge-summary-source",
        required=False,
        help="Optional path to signalforge_exact_matrix_edge_summary.json.",
    )
    parser.add_argument(
        "--replay-window-label",
        required=False,
        default=None,
        help="Optional label for the replay window, for example 20210601_20260531.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    args = parser.parse_args()

    coverage_source = _read_json(args.matrix_metadata_patch_coverage_audit_source)
    patch_plan_source = (
        _read_json(args.historical_replay_export_matrix_metadata_patch_plan_source)
        if args.historical_replay_export_matrix_metadata_patch_plan_source
        else None
    )
    exact_summary_source = (
        _read_json(args.exact_matrix_edge_summary_source)
        if args.exact_matrix_edge_summary_source
        else None
    )

    result = write_signalforge_historical_replay_matrix_metadata_rerun_plan(
        matrix_metadata_patch_coverage_audit_source=coverage_source,
        historical_replay_export_matrix_metadata_patch_plan_source=patch_plan_source,
        exact_matrix_edge_summary_source=exact_summary_source,
        replay_window_label=args.replay_window_label,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") != "blocked" else 2


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
