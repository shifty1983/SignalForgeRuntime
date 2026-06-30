from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.behavior.asset_behavior_decision_export import (
    build_signalforge_asset_behavior_decision_export,
)
from src.signalforge.engines.behavior.asset_behavior_decision_export_file_writer import (
    write_asset_behavior_decision_export_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge asset behavior decision export artifact."
    )

    parser.add_argument(
        "--asset-directional-stance",
        required=True,
        help="Path to signalforge_asset_directional_stance.json.",
    )
    parser.add_argument(
        "--relative-rank",
        required=True,
        help="Path to signalforge_asset_relative_rank.json.",
    )
    parser.add_argument(
        "--tradability-gate",
        required=True,
        help="Path to signalforge_asset_tradability_gate.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )

    args = parser.parse_args(argv)

    stance_path = Path(args.asset_directional_stance)
    relative_path = Path(args.relative_rank)
    tradability_path = Path(args.tradability_gate)

    if not stance_path.exists():
        raise SystemExit(f"asset directional stance file does not exist: {stance_path}")

    if not relative_path.exists():
        raise SystemExit(f"relative rank file does not exist: {relative_path}")

    if not tradability_path.exists():
        raise SystemExit(f"tradability gate file does not exist: {tradability_path}")

    asset_directional_stance = _read_json(stance_path)
    relative_rank = _read_json(relative_path)
    tradability_gate = _read_json(tradability_path)

    result = build_signalforge_asset_behavior_decision_export(
        asset_directional_stance,
        relative_rank,
        tradability_gate,
    )

    summary = write_asset_behavior_decision_export_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["asset_behavior_decision_export_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["asset_behavior_decision_export_result"] = (
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


