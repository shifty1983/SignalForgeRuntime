from __future__ import annotations

import argparse
import json
from pathlib import Path

from .portfolio_exit_path_enrichment import build_portfolio_exit_path_enrichment_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SignalForge portfolio exit path enrichment artifact.")
    parser.add_argument("--position-sizing-rows", required=True)
    parser.add_argument("--selected-strategy-outcome-rows", required=False, default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--scope", choices=("sized", "all"), default="sized")
    parser.add_argument("--minimum-final-outcome-path-coverage", type=float, default=0.95)
    args = parser.parse_args()

    summary = build_portfolio_exit_path_enrichment_artifact(
        position_sizing_rows_path=args.position_sizing_rows,
        selected_strategy_outcome_rows_path=args.selected_strategy_outcome_rows,
        output_dir=Path(args.output_dir),
        scope=args.scope,
        minimum_final_outcome_path_coverage=args.minimum_final_outcome_path_coverage,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
