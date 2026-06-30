from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.option_iv_history_snapshot import (
    DEFAULT_MIN_HISTORY_POINTS,
    build_signalforge_option_iv_history_snapshot,
)
from src.signalforge.engines.options.option_iv_history_snapshot_file_writer import (
    write_option_iv_history_snapshot_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge option IV history snapshot and IV rank/percentile classifications."
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
    parser.add_argument(
        "--min-history-points",
        type=int,
        default=DEFAULT_MIN_HISTORY_POINTS,
        help="Minimum quote-date observations per symbol before IV rank/percentile is ready.",
    )

    args = parser.parse_args(argv)

    option_source = _read_json(args.option_source)
    result = build_signalforge_option_iv_history_snapshot(
        option_source,
        min_history_points=args.min_history_points,
    )

    summary = write_option_iv_history_snapshot_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
