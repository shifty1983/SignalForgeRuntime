from __future__ import annotations

import argparse
import json

from src.backtesting.phase4_strategy_selection_replay_qc_manifest_builder import (
    build_phase4_strategy_selection_replay_qc_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Phase 4 strategy selection replay QC manifest."
    )
    parser.add_argument("--strategy-selection-rows", required=True)
    parser.add_argument("--strategy-selection-summary", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    manifest = build_phase4_strategy_selection_replay_qc_manifest(
        strategy_selection_rows_path=args.strategy_selection_rows,
        strategy_selection_summary_path=args.strategy_selection_summary,
        output_dir=args.output_dir,
    )

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
