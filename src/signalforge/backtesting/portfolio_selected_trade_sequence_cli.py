from __future__ import annotations

import argparse
import json
from pathlib import Path

from signalforge.backtesting.portfolio_selected_trade_sequence import build_from_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build SignalForge portfolio selected trade sequence artifact."
    )

    parser.add_argument(
        "--selected-strategy-outcome-rows",
        dest="selected_strategy_outcome_rows",
        help="Path to selected strategy outcome JSONL rows.",
    )
    parser.add_argument(
        "--selected-strategy-outcome-summary",
        dest="selected_strategy_outcome_summary",
        help="Path to selected strategy outcome summary JSON.",
    )

    # Backward-compatible aliases from the previous backtest.
    parser.add_argument(
        "--strategy-selection-rows",
        dest="strategy_selection_rows",
        help="Backward-compatible alias for --selected-strategy-outcome-rows.",
    )
    parser.add_argument(
        "--strategy-selection-summary",
        dest="strategy_selection_summary",
        help="Backward-compatible alias for --selected-strategy-outcome-summary.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for portfolio selected trade sequence artifacts.",
    )

    args = parser.parse_args()

    args.rows_path = args.selected_strategy_outcome_rows or args.strategy_selection_rows
    args.summary_path = args.selected_strategy_outcome_summary or args.strategy_selection_summary

    if not args.rows_path:
        parser.error("Provide --selected-strategy-outcome-rows or --strategy-selection-rows.")

    if not args.summary_path:
        parser.error("Provide --selected-strategy-outcome-summary or --strategy-selection-summary.")

    return args


def main() -> int:
    args = parse_args()

    result = build_from_paths(
        strategy_selection_rows_path=Path(args.rows_path),
        strategy_selection_summary_path=Path(args.summary_path),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(result.summary, indent=2, sort_keys=True))

    return 0 if result.summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


