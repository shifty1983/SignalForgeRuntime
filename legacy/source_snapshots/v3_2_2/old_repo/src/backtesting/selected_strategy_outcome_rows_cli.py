from __future__ import annotations

import argparse
import json

from src.backtesting.selected_strategy_outcome_rows_builder import (
    build_selected_strategy_outcome_rows_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build selected strategy outcome rows from strategy selection rows."
    )
    parser.add_argument("--strategy-selection-rows", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    summary = build_selected_strategy_outcome_rows_artifact(
        strategy_selection_rows_path=args.strategy_selection_rows,
        output_dir=args.output_dir,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
