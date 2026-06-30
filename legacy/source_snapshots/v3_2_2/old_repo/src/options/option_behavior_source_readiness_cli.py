from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.option_behavior_source_readiness import (
    build_signalforge_option_behavior_source_readiness,
)
from src.signalforge.engines.options.option_behavior_source_readiness_file_writer import (
    write_option_behavior_source_readiness_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge option behavior source readiness artifact."
    )

    parser.add_argument(
        "--asset-behavior-decision-export",
        required=True,
        help="Path to signalforge_asset_behavior_decision_export.json.",
    )
    parser.add_argument(
        "--option-source",
        required=True,
        help="Path to option rows/source JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )

    args = parser.parse_args(argv)

    asset_path = Path(args.asset_behavior_decision_export)
    option_path = Path(args.option_source)

    if not asset_path.exists():
        raise SystemExit(
            f"asset behavior decision export file does not exist: {asset_path}"
        )

    if not option_path.exists():
        raise SystemExit(f"option source file does not exist: {option_path}")

    asset_behavior_decision_export = _read_json(asset_path)
    option_source = _read_json(option_path)

    result = build_signalforge_option_behavior_source_readiness(
        asset_behavior_decision_export,
        option_source,
    )

    summary = write_option_behavior_source_readiness_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["option_behavior_source_readiness_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["option_behavior_source_readiness_result"] = (
        result_path.stat().st_size if result_path.exists() else 0
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0 if result.get("status") in {"ready", "needs_review"} else 1


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
