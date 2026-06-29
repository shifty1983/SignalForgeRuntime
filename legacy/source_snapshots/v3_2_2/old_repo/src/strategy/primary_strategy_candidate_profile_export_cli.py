from __future__ import annotations

import argparse
import json

from src.strategy.primary_strategy_candidate_profile_export import (
    export_primary_strategy_candidate_profile,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the primary strategy candidate profile for a selected window."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the portfolio candidate selection JSON source artifact.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the primary strategy candidate profile export should be written.",
    )
    parser.add_argument(
        "--selected-window-days",
        type=int,
        default=21,
        help="Selected candidate/profile window in days. Defaults to 21.",
    )

    args = parser.parse_args()

    result = export_primary_strategy_candidate_profile(
        source_path=args.source,
        output_dir=args.output_dir,
        selected_window_days=args.selected_window_days,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())