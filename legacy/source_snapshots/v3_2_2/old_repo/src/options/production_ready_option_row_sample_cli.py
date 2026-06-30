from __future__ import annotations

import argparse
import json
from typing import Sequence

from src.signalforge.engines.options.production_ready_option_row_sample import (
    DEFAULT_QUOTE_DATES,
    build_signalforge_production_ready_option_row_sample,
)
from src.signalforge.engines.options.production_ready_option_row_sample_file_writer import (
    write_production_ready_option_row_sample_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a deterministic production-ready multi-date option-row sample."
    )
    parser.add_argument(
        "--symbols",
        required=False,
        default="SPY,QQQ",
        help="Comma-separated underlying symbols to include in the sample.",
    )
    parser.add_argument(
        "--quote-date",
        required=False,
        default=None,
        help="Single quote date for legacy one-date smoke fixtures in YYYY-MM-DD format. Omit to use --quote-dates/default multi-date history.",
    )
    parser.add_argument(
        "--quote-dates",
        required=False,
        default=",".join(DEFAULT_QUOTE_DATES),
        help="Comma-separated quote dates in YYYY-MM-DD format. Defaults to three dates for IV history readiness.",
    )
    parser.add_argument(
        "--expirations",
        required=False,
        default="2026-07-17,2026-08-21",
        help="Comma-separated expiration dates in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--underlying-price",
        required=False,
        type=float,
        default=100.0,
        help="Synthetic underlying price for generated rows.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)
    quote_dates = _split_csv(args.quote_dates)
    if args.quote_date and quote_dates == list(DEFAULT_QUOTE_DATES):
        # Preserve explicit legacy --quote-date behavior only when the user has
        # not also supplied a custom --quote-dates value.
        quote_dates = [args.quote_date]

    result = build_signalforge_production_ready_option_row_sample(
        symbols=_split_csv(args.symbols),
        quote_dates=quote_dates,
        expirations=_split_csv(args.expirations),
        underlying_price=args.underlying_price,
    )
    summary = write_production_ready_option_row_sample_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
