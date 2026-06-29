from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.backtesting.phase6_portfolio_reconstruction_qc_manifest import build_from_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build SignalForge Phase 6 portfolio reconstruction QC manifest."
    )

    parser.add_argument(
        "--selected-trade-sequence-summary",
        required=True,
        help="Path to Phase 6.1 selected trade sequence summary JSON.",
    )

    parser.add_argument(
        "--position-sizing-summary",
        required=True,
        help="Path to Phase 6.2 position sizing summary JSON.",
    )

    parser.add_argument(
        "--equity-reconstruction-summary",
        required=True,
        help="Path to Phase 6.3 equity reconstruction summary JSON.",
    )

    parser.add_argument(
        "--metrics-report",
        required=True,
        help="Path to Phase 6.4 portfolio metrics report JSON.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for Phase 6 QC manifest.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    result = build_from_paths(
        selected_trade_sequence_summary_path=Path(
            args.selected_trade_sequence_summary
        ),
        position_sizing_summary_path=Path(args.position_sizing_summary),
        equity_reconstruction_summary_path=Path(
            args.equity_reconstruction_summary
        ),
        metrics_report_path=Path(args.metrics_report),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(result.manifest, indent=2, sort_keys=True))

    return 0 if result.manifest["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())