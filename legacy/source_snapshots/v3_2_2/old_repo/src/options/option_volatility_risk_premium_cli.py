from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.option_volatility_risk_premium import (
    DEFAULT_ANNUALIZATION_FACTOR,
    DEFAULT_CHEAP_RATIO_THRESHOLD,
    DEFAULT_MIN_RETURN_OBSERVATIONS,
    DEFAULT_RICH_RATIO_THRESHOLD,
    DEFAULT_WIDE_SPREAD_THRESHOLD,
    build_signalforge_option_volatility_risk_premium,
)
from src.signalforge.engines.options.option_volatility_risk_premium_file_writer import (
    write_option_volatility_risk_premium_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge option volatility risk premium classifications."
    )
    parser.add_argument(
        "--iv-history-source",
        required=True,
        help="Path to IV history snapshot JSON.",
    )
    parser.add_argument(
        "--realized-vol-source",
        required=True,
        help="Path to asset behavior, realized volatility, or market price history JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--rich-ratio-threshold",
        type=float,
        default=DEFAULT_RICH_RATIO_THRESHOLD,
        help="IV/RV ratio at or above which IV is classified as rich.",
    )
    parser.add_argument(
        "--cheap-ratio-threshold",
        type=float,
        default=DEFAULT_CHEAP_RATIO_THRESHOLD,
        help="IV/RV ratio at or below which IV is classified as cheap.",
    )
    parser.add_argument(
        "--wide-spread-threshold",
        type=float,
        default=DEFAULT_WIDE_SPREAD_THRESHOLD,
        help="Absolute IV minus RV spread that can classify IV as rich.",
    )
    parser.add_argument(
        "--annualization-factor",
        type=int,
        default=DEFAULT_ANNUALIZATION_FACTOR,
        help="Trading-day annualization factor for price-derived realized volatility.",
    )
    parser.add_argument(
        "--min-return-observations",
        type=int,
        default=DEFAULT_MIN_RETURN_OBSERVATIONS,
        help="Minimum return observations needed to compute price-derived RV.",
    )

    args = parser.parse_args(argv)

    iv_history_source = _read_json(args.iv_history_source)
    realized_vol_source = _read_json(args.realized_vol_source)
    result = build_signalforge_option_volatility_risk_premium(
        iv_history_source,
        realized_vol_source,
        rich_ratio_threshold=args.rich_ratio_threshold,
        cheap_ratio_threshold=args.cheap_ratio_threshold,
        wide_spread_threshold=args.wide_spread_threshold,
        annualization_factor=args.annualization_factor,
        min_return_observations=args.min_return_observations,
    )

    summary = write_option_volatility_risk_premium_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
