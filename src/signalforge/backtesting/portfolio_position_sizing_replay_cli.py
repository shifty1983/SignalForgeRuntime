from __future__ import annotations

import argparse
import json
from pathlib import Path

from signalforge.backtesting.portfolio_position_sizing_replay import build_from_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build SignalForge portfolio position sizing replay artifact."
    )

    parser.add_argument(
        "--selected-trade-sequence-rows",
        required=True,
        help="Path to portfolio selected trade sequence JSONL rows.",
    )

    parser.add_argument(
        "--selected-trade-sequence-summary",
        required=True,
        help="Path to portfolio selected trade sequence summary JSON.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for portfolio position sizing replay artifacts.",
    )

    parser.add_argument(
        "--starting-equity",
        type=float,
        default=100000.0,
        help="Starting portfolio equity. Default: 100000.",
    )

    parser.add_argument(
        "--risk-per-trade-pct",
        type=float,
        default=0.01,
        help="Risk fraction of current equity per trade. Default: 0.01.",
    )

    parser.add_argument(
        "--max-trade-risk-dollars",
        type=float,
        default=1000.0,
        help="Maximum risk dollars per trade. Default: 1000.",
    )

    parser.add_argument(
        "--min-realized-return",
        type=float,
        default=-1.0,
        help="Minimum allowed realized return multiple. Default: -1.0.",
    )

    parser.add_argument(
        "--max-realized-return",
        type=float,
        default=10.0,
        help="Maximum allowed realized return multiple. Default: 10.0.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    result = build_from_paths(
        selected_trade_sequence_rows_path=Path(args.selected_trade_sequence_rows),
        selected_trade_sequence_summary_path=Path(args.selected_trade_sequence_summary),
        output_dir=Path(args.output_dir),
        starting_equity=args.starting_equity,
        risk_per_trade_pct=args.risk_per_trade_pct,
        max_trade_risk_dollars=args.max_trade_risk_dollars,
        min_realized_return=args.min_realized_return,
        max_realized_return=args.max_realized_return,
    )

    print(json.dumps(result.summary, indent=2, sort_keys=True))

    return 0 if result.summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
