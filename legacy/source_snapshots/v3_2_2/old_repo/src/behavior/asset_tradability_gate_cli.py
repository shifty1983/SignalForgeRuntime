from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.behavior.asset_tradability_gate import (
    build_signalforge_asset_tradability_gate,
)
from src.behavior.asset_tradability_gate_file_writer import (
    write_asset_tradability_gate_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge asset tradability gate artifact."
    )

    parser.add_argument(
        "--multi-horizon-behavior",
        required=True,
        help="Path to signalforge_asset_multi_horizon_behavior.json.",
    )
    parser.add_argument(
        "--relative-rank",
        required=True,
        help="Path to signalforge_asset_relative_rank.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument("--min-observations", type=int, default=50)
    parser.add_argument("--min-price", type=float, default=5.0)
    parser.add_argument("--min-average-volume", type=float, default=250000.0)
    parser.add_argument("--min-average-dollar-volume", type=float, default=5000000.0)
    parser.add_argument("--review-realized-volatility", type=float, default=0.80)
    parser.add_argument("--block-realized-volatility", type=float, default=1.50)
    parser.add_argument("--review-max-drawdown", type=float, default=-0.40)
    parser.add_argument("--block-max-drawdown", type=float, default=-0.65)

    args = parser.parse_args(argv)

    multi_path = Path(args.multi_horizon_behavior)
    relative_path = Path(args.relative_rank)

    if not multi_path.exists():
        raise SystemExit(f"multi-horizon behavior file does not exist: {multi_path}")

    if not relative_path.exists():
        raise SystemExit(f"relative rank file does not exist: {relative_path}")

    multi_horizon_behavior = _read_json(multi_path)
    relative_rank = _read_json(relative_path)

    result = build_signalforge_asset_tradability_gate(
        multi_horizon_behavior,
        relative_rank,
        min_observations=args.min_observations,
        min_price=args.min_price,
        min_average_volume=args.min_average_volume,
        min_average_dollar_volume=args.min_average_dollar_volume,
        review_realized_volatility=args.review_realized_volatility,
        block_realized_volatility=args.block_realized_volatility,
        review_max_drawdown=args.review_max_drawdown,
        block_max_drawdown=args.block_max_drawdown,
    )

    summary = write_asset_tradability_gate_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["asset_tradability_gate_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["asset_tradability_gate_result"] = (
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
