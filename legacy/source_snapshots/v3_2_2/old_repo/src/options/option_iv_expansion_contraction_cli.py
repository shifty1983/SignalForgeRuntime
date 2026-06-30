from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.option_iv_expansion_contraction import (
    DEFAULT_EXPANSION_ABS_THRESHOLD,
    DEFAULT_EXPANSION_PCT_THRESHOLD,
    DEFAULT_SPIKE_ABS_THRESHOLD,
    DEFAULT_SPIKE_PCT_THRESHOLD,
    build_signalforge_option_iv_expansion_contraction,
)
from src.signalforge.engines.options.option_iv_expansion_contraction_file_writer import (
    write_option_iv_expansion_contraction_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge option IV expansion/contraction behavior classifications."
    )
    parser.add_argument(
        "--iv-history-source",
        required=True,
        help="Path to option IV history snapshot JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--expansion-abs-threshold",
        type=float,
        default=DEFAULT_EXPANSION_ABS_THRESHOLD,
        help="Minimum absolute IV change for expansion/contraction classification.",
    )
    parser.add_argument(
        "--expansion-pct-threshold",
        type=float,
        default=DEFAULT_EXPANSION_PCT_THRESHOLD,
        help="Minimum percent IV change for expansion/contraction classification.",
    )
    parser.add_argument(
        "--spike-abs-threshold",
        type=float,
        default=DEFAULT_SPIKE_ABS_THRESHOLD,
        help="Minimum absolute IV change for spike/crush classification.",
    )
    parser.add_argument(
        "--spike-pct-threshold",
        type=float,
        default=DEFAULT_SPIKE_PCT_THRESHOLD,
        help="Minimum percent IV change for spike/crush classification.",
    )

    args = parser.parse_args(argv)

    iv_history_source = _read_json(args.iv_history_source)
    result = build_signalforge_option_iv_expansion_contraction(
        iv_history_source,
        expansion_abs_threshold=args.expansion_abs_threshold,
        expansion_pct_threshold=args.expansion_pct_threshold,
        spike_abs_threshold=args.spike_abs_threshold,
        spike_pct_threshold=args.spike_pct_threshold,
    )

    summary = write_option_iv_expansion_contraction_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
