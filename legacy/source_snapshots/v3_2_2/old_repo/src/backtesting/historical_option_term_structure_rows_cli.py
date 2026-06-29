from __future__ import annotations

import argparse
import json

from src.backtesting.historical_option_term_structure_rows_builder import (
    build_historical_option_term_structure_rows_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build historical option term-structure rows from QC option behavior input rows."
    )
    parser.add_argument("--option-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-dte", type=int, default=7)
    parser.add_argument("--max-dte", type=int, default=90)
    parser.add_argument("--max-abs-moneyness-diff", type=float, default=0.15)
    parser.add_argument("--min-contracts-per-expiration", type=int, default=1)
    parser.add_argument("--min-expiration-gap-days", type=int, default=7)
    parser.add_argument("--flat-threshold", type=float, default=0.02)

    args = parser.parse_args()

    summary = build_historical_option_term_structure_rows_artifact(
        option_rows_path=args.option_rows,
        output_dir=args.output_dir,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        max_abs_moneyness_diff=args.max_abs_moneyness_diff,
        min_contracts_per_expiration=args.min_contracts_per_expiration,
        min_expiration_gap_days=args.min_expiration_gap_days,
        flat_threshold=args.flat_threshold,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
