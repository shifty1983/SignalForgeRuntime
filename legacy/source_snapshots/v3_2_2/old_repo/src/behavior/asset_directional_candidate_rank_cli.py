from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.behavior.asset_directional_candidate_rank import (
    build_signalforge_asset_directional_candidate_rank,
)
from src.signalforge.engines.behavior.asset_directional_candidate_rank_file_writer import (
    write_asset_directional_candidate_rank_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge ranked directional candidate artifact."
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to signalforge_asset_directional_stance.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of ranked candidates to include in each list.",
    )

    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"source file does not exist: {source_path}")

    source = _read_json(source_path)

    result = build_signalforge_asset_directional_candidate_rank(
        source,
        top_n=args.top_n,
    )

    summary = write_asset_directional_candidate_rank_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["asset_directional_candidate_rank_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["asset_directional_candidate_rank_result"] = (
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
