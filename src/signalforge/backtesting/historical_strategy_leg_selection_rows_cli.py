from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from signalforge.backtesting.historical_strategy_leg_selection_rows_builder import (
    build_historical_strategy_leg_selection_rows_artifact,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build historical strategy leg-selection rows from candidate rows and raw QC option chains."
    )
    parser.add_argument("--candidate-rows", required=True)
    parser.add_argument("--raw-option-input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-spread-pct", type=float, default=0.50)
    parser.add_argument("--min-open-interest", type=int, default=0)
    parser.add_argument("--min-volume", type=int, default=0)
    parser.add_argument("--primary-delta-deviation", type=float, default=0.15)
    parser.add_argument("--secondary-delta-deviation", type=float, default=0.30)
    parser.add_argument("--progress-every", type=int, default=10000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    summary = build_historical_strategy_leg_selection_rows_artifact(
        strategy_candidate_rows_path=Path(args.candidate_rows),
        option_rows_path=Path(args.raw_option_input),
        output_dir=Path(args.output_dir),
        max_spread_pct=args.max_spread_pct,
        emit_blocked_rows=False,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())


