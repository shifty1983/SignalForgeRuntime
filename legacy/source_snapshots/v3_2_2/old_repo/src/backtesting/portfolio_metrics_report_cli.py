from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.backtesting.portfolio_metrics_report import build_from_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build SignalForge portfolio metrics report artifact."
    )

    parser.add_argument(
        "--equity-curve-rows",
        required=True,
        help="Path to portfolio equity curve JSONL rows.",
    )

    parser.add_argument(
        "--equity-reconstruction-summary",
        required=True,
        help="Path to portfolio equity reconstruction summary JSON.",
    )

    parser.add_argument(
        "--position-sizing-rows",
        required=True,
        help="Path to portfolio position sizing replay JSONL rows.",
    )

    parser.add_argument(
        "--position-sizing-summary",
        required=True,
        help="Path to portfolio position sizing replay summary JSON.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for portfolio metrics report artifact.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    result = build_from_paths(
        equity_curve_rows_path=Path(args.equity_curve_rows),
        equity_reconstruction_summary_path=Path(args.equity_reconstruction_summary),
        position_sizing_rows_path=Path(args.position_sizing_rows),
        position_sizing_summary_path=Path(args.position_sizing_summary),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(result.report, indent=2, sort_keys=True))

    return 0 if result.report["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())