from __future__ import annotations

import argparse
import json
from pathlib import Path

from signalforge.backtesting.portfolio_equity_reconstruction import build_from_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build SignalForge portfolio equity reconstruction artifact."
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
        help="Output directory for portfolio equity reconstruction artifacts.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    result = build_from_paths(
        position_sizing_rows_path=Path(args.position_sizing_rows),
        position_sizing_summary_path=Path(args.position_sizing_summary),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(result.summary, indent=2, sort_keys=True))

    return 0 if result.summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
