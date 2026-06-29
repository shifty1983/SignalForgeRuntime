from __future__ import annotations

import argparse
import json

from src.backtesting.phase5_trade_scoring_qc_manifest_builder import (
    build_phase5_trade_scoring_qc_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Phase 5 trade scoring QC manifest."
    )
    parser.add_argument("--selected-strategy-outcome-rows", required=True)
    parser.add_argument("--selected-strategy-outcome-summary", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    manifest = build_phase5_trade_scoring_qc_manifest(
        selected_strategy_outcome_rows_path=args.selected_strategy_outcome_rows,
        selected_strategy_outcome_summary_path=args.selected_strategy_outcome_summary,
        output_dir=args.output_dir,
    )

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
