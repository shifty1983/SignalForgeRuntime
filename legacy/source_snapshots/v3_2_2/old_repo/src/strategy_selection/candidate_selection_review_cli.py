from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.candidate_selection_review import build_signalforge_candidate_selection_review
from src.signalforge.engines.strategy_selection.candidate_selection_review_file_writer import write_candidate_selection_review_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge candidate selection review from expected value scoring."
    )
    parser.add_argument(
        "--expected-value-source",
        required=True,
        help="Path to expected value scoring JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=25,
        help="Maximum number of positive/marginal EV candidates to rank for final review.",
    )

    args = parser.parse_args(argv)

    result = build_signalforge_candidate_selection_review(
        expected_value_source=_read_json(args.expected_value_source),
        max_candidates=args.max_candidates,
    )

    summary = write_candidate_selection_review_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
