from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.options.option_theta_sensitivity import (
    DEFAULT_ELEVATED_AVG_ABS_THETA_THRESHOLD,
    DEFAULT_HIGH_AVG_ABS_THETA_THRESHOLD,
    DEFAULT_HIGH_MAX_ABS_THETA_THRESHOLD,
    DEFAULT_LOW_AVG_ABS_THETA_THRESHOLD,
    build_signalforge_option_theta_sensitivity,
)
from src.options.option_theta_sensitivity_file_writer import (
    write_option_theta_sensitivity_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge option theta sensitivity behavior classifications."
    )
    parser.add_argument(
        "--option-source",
        required=True,
        help="Path to option rows JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--low-avg-abs-theta-threshold",
        type=float,
        default=DEFAULT_LOW_AVG_ABS_THETA_THRESHOLD,
        help="Average absolute theta at or below this threshold is low theta sensitivity.",
    )
    parser.add_argument(
        "--elevated-avg-abs-theta-threshold",
        type=float,
        default=DEFAULT_ELEVATED_AVG_ABS_THETA_THRESHOLD,
        help="Average absolute theta at or above this threshold is elevated theta sensitivity.",
    )
    parser.add_argument(
        "--high-avg-abs-theta-threshold",
        type=float,
        default=DEFAULT_HIGH_AVG_ABS_THETA_THRESHOLD,
        help="Average absolute theta at or above this threshold is high theta sensitivity.",
    )
    parser.add_argument(
        "--high-max-abs-theta-threshold",
        type=float,
        default=DEFAULT_HIGH_MAX_ABS_THETA_THRESHOLD,
        help="Single-contract absolute theta at or above this threshold is high theta sensitivity.",
    )

    args = parser.parse_args(argv)

    option_source = _read_json(args.option_source)
    result = build_signalforge_option_theta_sensitivity(
        option_source,
        low_avg_abs_theta_threshold=args.low_avg_abs_theta_threshold,
        elevated_avg_abs_theta_threshold=args.elevated_avg_abs_theta_threshold,
        high_avg_abs_theta_threshold=args.high_avg_abs_theta_threshold,
        high_max_abs_theta_threshold=args.high_max_abs_theta_threshold,
    )

    summary = write_option_theta_sensitivity_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
