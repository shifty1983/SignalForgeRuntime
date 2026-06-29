from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.contract_selection_readiness import build_signalforge_contract_selection_readiness
from src.strategy_selection.contract_selection_readiness_file_writer import write_contract_selection_readiness_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge contract selection readiness from candidate final review export."
    )
    parser.add_argument(
        "--candidate-final-review-source",
        required=True,
        help="Path to candidate final review export JSON artifact.",
    )
    parser.add_argument(
        "--option-source",
        required=False,
        default=None,
        help="Optional path to contract-level option rows JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--min-candidate-contract-count", type=int, default=1)
    parser.add_argument("--max-spread-pct", type=float, default=0.15)
    parser.add_argument("--min-open-interest", type=int, default=100)
    parser.add_argument("--min-volume", type=int, default=1)

    args = parser.parse_args(argv)

    option_source = _read_json(args.option_source) if args.option_source else None

    result = build_signalforge_contract_selection_readiness(
        candidate_final_review_source=_read_json(args.candidate_final_review_source),
        option_source=option_source,
        min_candidate_contract_count=args.min_candidate_contract_count,
        max_spread_pct=args.max_spread_pct,
        min_open_interest=args.min_open_interest,
        min_volume=args.min_volume,
    )

    summary = write_contract_selection_readiness_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
