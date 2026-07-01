from __future__ import annotations

import argparse
import json

from signalforge.backtesting.historical_strategy_quote_outcome_rows_builder import (
    build_historical_strategy_quote_outcome_rows_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build quote-derived historical strategy outcome rows from selected option legs."
    )
    parser.add_argument("--leg-selection-rows", required=True)
    parser.add_argument("--option-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-exit-search-days", type=int, default=5)

    args = parser.parse_args()

    summary = build_historical_strategy_quote_outcome_rows_artifact(
        leg_selection_rows_path=args.leg_selection_rows,
        option_rows_path=args.option_rows,
        output_dir=args.output_dir,
        max_exit_search_days=args.max_exit_search_days,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())

