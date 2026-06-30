from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.candidate_final_review_export import build_signalforge_candidate_final_review_export
from src.signalforge.engines.strategy_selection.candidate_final_review_export_file_writer import write_candidate_final_review_export_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge candidate final review export from candidate selection review."
    )
    parser.add_argument(
        "--candidate-review-source",
        required=True,
        help="Path to candidate selection review JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument(
        "--max-final-review-items",
        type=int,
        default=25,
        help="Maximum number of ranked candidates to include in the final review export.",
    )

    args = parser.parse_args(argv)

    result = build_signalforge_candidate_final_review_export(
        candidate_review_source=_read_json(args.candidate_review_source),
        max_final_review_items=args.max_final_review_items,
    )

    summary = write_candidate_final_review_export_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
