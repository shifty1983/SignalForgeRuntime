from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.expected_value_scoring import build_signalforge_expected_value_scoring
from src.strategy_selection.expected_value_scoring_file_writer import write_expected_value_scoring_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge risk-adjusted expected value scoring from strategy-family eligibility."
    )
    parser.add_argument(
        "--eligibility-source",
        required=True,
        help="Path to strategy-family eligibility JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_expected_value_scoring(
        eligibility_source=_read_json(args.eligibility_source),
    )

    summary = write_expected_value_scoring_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
