"""CLI for matrix metadata patch coverage audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.engines.strategy_selection.matrix_metadata_patch_coverage_audit import (
    build_signalforge_matrix_metadata_patch_coverage_audit,
)
from src.signalforge.engines.strategy_selection.matrix_metadata_patch_coverage_audit_file_writer import (
    write_signalforge_matrix_metadata_patch_coverage_audit,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a SignalForge matrix metadata patch coverage audit.")
    parser.add_argument(
        "--historical-replay-export-matrix-metadata-patch-plan-source",
        required=True,
        help="Path to signalforge_historical_replay_export_matrix_metadata_patch_plan.json.",
    )
    parser.add_argument(
        "--exact-matrix-edge-summary-source",
        required=False,
        help="Optional path to signalforge_exact_matrix_edge_summary.json or summary.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to inspect for patched source files. Defaults to current directory.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory to write audit artifacts.")

    args = parser.parse_args(argv)

    patch_plan_source = _load_json(Path(args.historical_replay_export_matrix_metadata_patch_plan_source))
    exact_source = _load_json(Path(args.exact_matrix_edge_summary_source)) if args.exact_matrix_edge_summary_source else None

    result = build_signalforge_matrix_metadata_patch_coverage_audit(
        historical_replay_export_matrix_metadata_patch_plan_source=patch_plan_source,
        repo_root=args.repo_root,
        exact_matrix_edge_summary_source=exact_source,
    )
    write_result = write_signalforge_matrix_metadata_patch_coverage_audit(
        result=result,
        output_dir=args.output_dir,
    )
    print(json.dumps(write_result, indent=2, sort_keys=True))
    return 0 if not write_result.get("blocked_reasons") else 1


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
