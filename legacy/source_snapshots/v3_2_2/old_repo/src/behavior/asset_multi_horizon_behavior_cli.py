from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.behavior.asset_multi_horizon_behavior import (
    DEFAULT_HORIZONS,
    build_signalforge_asset_multi_horizon_behavior,
)
from src.behavior.asset_multi_horizon_behavior_file_writer import (
    write_asset_multi_horizon_behavior_result,
)


DEFAULT_MARKET_PRICE_SOURCE = "artifacts/qc_replay_5y_behavior_inputs/signalforge_qc_replay_market_price_behavior_input.json"
DEFAULT_OUTPUT_DIR = "artifacts/asset_multi_horizon_behavior"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge multi-horizon asset behavior artifact."
    )

    parser.add_argument(
        "--source",
        default=DEFAULT_MARKET_PRICE_SOURCE,
        help=(
            "Path to market price input JSON. Defaults to the stable QC 5Y "
            "behavior input artifact."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--horizon",
        action="append",
        type=int,
        default=None,
        help="Lookback horizon. Can be repeated. Defaults to 20, 50, 100, 200.",
    )
    parser.add_argument(
        "--annualization-factor",
        type=int,
        default=252,
        help="Annualization factor for realized volatility.",
    )
    parser.add_argument(
        "--positive-return-threshold",
        type=float,
        default=0.02,
        help="Return threshold for positive horizon trend.",
    )
    parser.add_argument(
        "--negative-return-threshold",
        type=float,
        default=-0.02,
        help="Return threshold for negative horizon trend.",
    )

    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"source file does not exist: {source_path}")

    source = _read_json(source_path)

    result = build_signalforge_asset_multi_horizon_behavior(
        source,
        horizons=tuple(args.horizon) if args.horizon else DEFAULT_HORIZONS,
        annualization_factor=args.annualization_factor,
        positive_return_threshold=args.positive_return_threshold,
        negative_return_threshold=args.negative_return_threshold,
    )

    summary = write_asset_multi_horizon_behavior_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["asset_multi_horizon_behavior_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["asset_multi_horizon_behavior_result"] = (
        result_path.stat().st_size if result_path.exists() else 0
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0 if result.get("status") in {"ready", "needs_review"} else 1


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
