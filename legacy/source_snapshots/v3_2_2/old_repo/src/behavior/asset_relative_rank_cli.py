from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.behavior.asset_relative_rank import build_signalforge_asset_relative_rank
from src.behavior.asset_relative_rank_file_writer import (
    write_asset_relative_rank_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge asset relative rank artifact."
    )

    parser.add_argument(
        "--multi-horizon-behavior",
        required=True,
        help="Path to signalforge_asset_multi_horizon_behavior.json.",
    )
    parser.add_argument(
        "--asset-directional-stance",
        required=True,
        help="Path to signalforge_asset_directional_stance.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )

    args = parser.parse_args(argv)

    multi_path = Path(args.multi_horizon_behavior)
    stance_path = Path(args.asset_directional_stance)

    if not multi_path.exists():
        raise SystemExit(f"multi-horizon behavior file does not exist: {multi_path}")

    if not stance_path.exists():
        raise SystemExit(f"asset directional stance file does not exist: {stance_path}")

    multi_horizon_behavior = _read_json(multi_path)
    asset_directional_stance = _read_json(stance_path)

    result = build_signalforge_asset_relative_rank(
        multi_horizon_behavior,
        asset_directional_stance,
    )

    summary = write_asset_relative_rank_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["asset_relative_rank_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["asset_relative_rank_result"] = (
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
