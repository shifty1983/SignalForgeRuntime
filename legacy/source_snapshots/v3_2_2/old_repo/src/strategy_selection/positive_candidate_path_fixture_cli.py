from __future__ import annotations

import argparse
import json
from typing import Sequence

from src.strategy_selection.positive_candidate_path_fixture import (
    build_signalforge_positive_candidate_path_fixture,
)
from src.strategy_selection.positive_candidate_path_fixture_file_writer import (
    write_positive_candidate_path_fixture_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a deterministic positive-candidate Strategy Family Eligibility fixture."
    )
    parser.add_argument(
        "--symbols",
        required=False,
        default="SPY,QQQ",
        help="Comma-separated symbols to include in the positive-candidate fixture.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)
    result = build_signalforge_positive_candidate_path_fixture(
        symbols=_split_csv(args.symbols),
    )
    summary = write_positive_candidate_path_fixture_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
